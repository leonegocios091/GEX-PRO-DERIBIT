import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timezone

# =========================================
# SETUP
# =========================================
st.set_page_config(page_title="GEX Pro Engine", layout="wide")
st_autorefresh(interval=15000, key="refresh")

# =========================================
# FUNÇÕES MATEMÁTICAS
# =========================================
def normal_pdf(x):
    return np.exp(-0.5 * x**2) / np.sqrt(2 * np.pi)

# =========================================
# DATA LOADER
# =========================================
@st.cache_data(ttl=10)
def carregar_deribit(ticker):
    try:
        url = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={ticker}&kind=option"
        res = requests.get(url, timeout=10).json().get("result", [])

        if not res:
            return None

        df = pd.DataFrame(res)

        parts = df['instrument_name'].str.split('-')

        df['strike'] = pd.to_numeric(parts.str[2], errors='coerce')
        df['data_exp'] = parts.str[1]
        df['tipo'] = parts.str[3]

        df = df.dropna(subset=['strike'])

        df['open_interest'] = pd.to_numeric(df['open_interest'], errors='coerce').fillna(0)

        return df

    except:
        return None

# =========================================
# EXPOSURES (GEX + VEX + CHARM)
# =========================================
def calcular_exposures(df, S):
    df = df.copy()

    df['exp_datetime'] = pd.to_datetime(df['data_exp'], format='%d%b%y', errors='coerce', utc=True)
    now = datetime.now(timezone.utc)

    df['T'] = (df['exp_datetime'] - now).dt.total_seconds() / (365 * 24 * 3600)
    df['T'] = df['T'].fillna(0).clip(lower=1e-6)

    df['iv'] = pd.to_numeric(df['mark_iv'], errors='coerce') / 100
    df['iv'] = df['iv'].replace(0, np.nan).fillna(df['iv'].median()).clip(lower=0.01)

    K = df['strike']
    sigma = df['iv']
    T = df['T']

    with np.errstate(divide='ignore', invalid='ignore'):
        d1 = (np.log(S / K) + 0.5 * sigma**2 * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)

    d1 = d1.replace([np.inf, -np.inf], 0).fillna(0)
    d2 = d2.replace([np.inf, -np.inf], 0).fillna(0)

    pdf = normal_pdf(d1)

    gamma = pdf / (S * sigma * np.sqrt(T))
    vanna = -pdf * d2 / sigma

    # Charm (aproximação robusta)
    charm = -pdf * (2 * (0.5 * sigma**2 * T - np.log(S / K)) / (2 * T * sigma * np.sqrt(T)))

    df['gex'] = gamma * df['open_interest'] * (S**2)
    df['vex'] = vanna * df['open_interest'] * S
    df['charm'] = charm * df['open_interest'] * S

    df.loc[df['tipo'] == 'P', ['gex', 'vex', 'charm']] *= -1

    df[['gex','vex','charm']] = df[['gex','vex','charm']].replace([np.inf, -np.inf], 0).fillna(0)

    return df

# =========================================
# G-FLIP
# =========================================
def calcular_gflip(res):
    x = res['strike'].values
    y = res['Net GEX'].values

    for i in range(len(y)-1):
        if y[i] * y[i+1] < 0:
            return x[i] - y[i] * (x[i+1] - x[i]) / (y[i+1] - y[i])

    return None

# =========================================
# GAMMA PROFILE
# =========================================
def gamma_profile(df, spot_range):
    profile = []

    for S in spot_range:
        temp = calcular_exposures(df, S)
        profile.append(temp['gex'].sum() / 1e9)

    return np.array(profile)

# =========================================
# SIGNAL ENGINE
# =========================================
def gerar_sinal(res, gex_profile, spot_range):
    gex = res['Net GEX'].sum()
    vex = res['Net VEX'].sum()
    charm = res['Net Charm'].sum()

    slope = (gex_profile[-1] - gex_profile[0]) / (spot_range[-1] - spot_range[0])

    if gex > 0 and slope < 0:
        regime = "Range (Mean Reversion)"
        bias = "Vender extremos"

    elif gex < 0 and slope > 0:
        regime = "Tendência (Vol Expansion)"
        bias = "Seguir movimento"

    else:
        regime = "Transição"
        bias = "Neutro / Cautela"

    if abs(vex) > abs(gex):
        bias += " | Sensível à volatilidade"

    if charm < 0:
        bias += " | Pressão vendedora"

    return regime, bias

# =========================================
# UI
# =========================================
st.sidebar.header("Configuração")
moeda = st.sidebar.selectbox("Ativo", ["BTC", "ETH"])

df_raw = carregar_deribit(moeda)

# =========================================
# EXECUÇÃO
# =========================================
if df_raw is not None and not df_raw.empty:

    preco_spot = df_raw['estimated_delivery_price'].iloc[0]

    df = calcular_exposures(df_raw, preco_spot)

    res = df.groupby('strike').agg({
        'gex': 'sum',
        'vex': 'sum',
        'charm': 'sum'
    }).reset_index().sort_values('strike')

    res['Net GEX'] = res['gex'] / 1e9
    res['Net VEX'] = res['vex'] / 1e9
    res['Net Charm'] = res['charm'] / 1e9
    res['flow'] = res['Net GEX'].cumsum()

    g_flip = calcular_gflip(res)

    # =========================================
    # GAMMA PROFILE
    # =========================================
    spot_range = np.linspace(preco_spot * 0.9, preco_spot * 1.1, 40)
    gex_profile = gamma_profile(df_raw, spot_range)

    # =========================================
    # SIGNAL
    # =========================================
    regime, bias = gerar_sinal(res, gex_profile, spot_range)

    st.subheader("🎯 Regime de Mercado")
    st.metric("Regime", regime)
    st.metric("Bias", bias)

    # =========================================
    # GEX
    # =========================================
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=res['strike'],
        y=res['Net GEX'],
        marker_color=['green' if v>0 else 'red' for v in res['Net GEX']]
    ))

    fig.add_vline(x=preco_spot)
    if g_flip:
        fig.add_vline(x=g_flip, line_dash="dot")

    fig.update_layout(template="plotly_dark", height=400)
    st.plotly_chart(fig, use_container_width=True)

    # =========================================
    # FLOW
    # =========================================
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=res['strike'], y=res['flow']))
    fig2.update_layout(template="plotly_dark", height=300)
    st.plotly_chart(fig2, use_container_width=True)

    # =========================================
    # VEX
    # =========================================
    fig3 = go.Figure()
    fig3.add_trace(go.Bar(x=res['strike'], y=res['Net VEX']))
    fig3.update_layout(template="plotly_dark", height=300)
    st.plotly_chart(fig3, use_container_width=True)

    # =========================================
    # CHARM
    # =========================================
    fig4 = go.Figure()
    fig4.add_trace(go.Bar(x=res['strike'], y=res['Net Charm']))
    fig4.update_layout(template="plotly_dark", height=300)
    st.plotly_chart(fig4, use_container_width=True)

    # =========================================
    # GAMMA PROFILE
    # =========================================
    fig5 = go.Figure()
    fig5.add_trace(go.Scatter(x=spot_range, y=gex_profile))
    fig5.add_vline(x=preco_spot)
    fig5.update_layout(template="plotly_dark", height=300)
    st.plotly_chart(fig5, use_container_width=True)

else:
    st.info("Carregando dados...")
