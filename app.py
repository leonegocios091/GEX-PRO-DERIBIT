import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timezone

# =========================================
# 1. SETUP
# =========================================
st.set_page_config(page_title="GEX Master Engine Pro", layout="wide")
st_autorefresh(interval=15000, key="hiro_sync_refresh")

# =========================================
# 2. NORMAL PDF (sem scipy)
# =========================================
def normal_pdf(x):
    return np.exp(-0.5 * x**2) / np.sqrt(2 * np.pi)

# =========================================
# 3. DATA LOADER (ROBUSTO)
# =========================================
@st.cache_data(ttl=10)
def carregar_deribit(ticker):
    url = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={ticker}&kind=option"
    try:
        res = requests.get(url, timeout=10).json().get('result', [])
        if not res:
            return None

        df = pd.DataFrame(res)

        required_cols = ['instrument_name', 'open_interest', 'mark_iv']
        for col in required_cols:
            if col not in df.columns:
                return None

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
# 4. EXPOSURES (GEX + VEX)
# =========================================
def calcular_exposures(df, S):
    df = df.copy()

    df['exp_datetime'] = pd.to_datetime(df['data_exp'], format='%d%b%y', errors='coerce', utc=True)
    now = datetime.now(timezone.utc)

    df['T'] = (df['exp_datetime'] - now).dt.total_seconds() / (365*24*3600)
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

    df['gex'] = gamma * df['open_interest'] * (S**2)
    df['vex'] = vanna * df['open_interest'] * S

    df.loc[df['tipo'] == 'P', ['gex', 'vex']] *= -1

    df[['gex','vex']] = df[['gex','vex']].replace([np.inf, -np.inf], 0).fillna(0)

    return df

# =========================================
# 5. G-FLIP INTERPOLADO
# =========================================
def calcular_gflip_interpolado(res):
    x = res['strike'].values
    y = res['Net GEX'].values

    for i in range(len(y) - 1):
        if y[i] == 0:
            return x[i]
        if y[i] * y[i+1] < 0:
            return x[i] - y[i] * (x[i+1] - x[i]) / (y[i+1] - y[i])

    return None

# =========================================
# 6. UI
# =========================================
st.sidebar.header("🕹️ Real-Time Engine")
moeda = st.sidebar.selectbox("Ativo", ["BTC", "ETH"])
opacidade_abs = st.sidebar.slider("Opacidade Abs GEX", 0.0, 1.0, 0.15)

df_raw = carregar_deribit(moeda)

# =========================================
# 7. PROCESSAMENTO
# =========================================
if df_raw is not None and not df_raw.empty:

    preco_spot = df_raw.get('estimated_delivery_price', pd.Series([None])).iloc[0]

    if preco_spot is None or preco_spot == 0:
        st.warning("Preço spot indisponível.")
        st.stop()

    hoje_utc = datetime.now(timezone.utc).strftime("%d%b%y").upper()
    exp_list = sorted(df_raw['data_exp'].dropna().unique())

    if not exp_list:
        st.warning("Nenhum vencimento disponível.")
        st.stop()

    selecao_exp = st.sidebar.multiselect(
        "Vencimentos",
        options=exp_list,
        default=[hoje_utc] if hoje_utc in exp_list else [exp_list[0]]
    )

    if selecao_exp:
        df = df_raw[df_raw['data_exp'].isin(selecao_exp)].copy()

        if df.empty:
            st.warning("Sem dados para os vencimentos selecionados.")
            st.stop()

        df = calcular_exposures(df, preco_spot)

        res = df.groupby('strike').agg({
            'gex': 'sum',
            'vex': 'sum',
            'open_interest': 'sum'
        }).reset_index()

        if res.empty:
            st.warning("Falha na agregação.")
            st.stop()

        res = res.sort_values('strike')

        res['Net GEX'] = res['gex'] / 1e9
        res['Net VEX'] = res['vex'] / 1e9
        res['abs_gex'] = res['Net GEX'].abs()
        res['flow'] = res['Net GEX'].cumsum()

        g_flip = calcular_gflip_interpolado(res)

        # =========================================
        # TERM STRUCTURE
        # =========================================
        term = df.groupby('data_exp')['gex'].sum().reset_index()
        term['gex'] = term['gex'] / 1e9
        term = term.sort_values('data_exp')

        # =========================================
        # GRÁFICO GEX
        # =========================================
        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=res['strike'],
            y=res['abs_gex'],
            fill='tozeroy',
            mode='none',
            fillcolor=f'rgba(255,255,0,{opacidade_abs})',
            name='Abs GEX'
        ))

        cores = ['#00ffbb' if v > 0 else '#ff4444' for v in res['Net GEX']]

        fig.add_trace(go.Bar(
            x=res['strike'],
            y=res['Net GEX'],
            marker_color=cores,
            name='Net GEX'
        ))

        fig.add_vline(x=preco_spot, line_color="orange",
                      annotation_text=f"SPOT {preco_spot:.0f}")

        if g_flip:
            fig.add_vline(x=g_flip, line_color="white",
                          line_dash="dot", annotation_text="G-FLIP")

        fig.update_layout(template="plotly_dark", height=500)

        st.plotly_chart(fig, use_container_width=True)

        # =========================================
        # DEALER FLOW
        # =========================================
        st.subheader("🌊 Dealer Hedge Flow")

        fig_h = go.Figure()

        fig_h.add_trace(go.Scatter(
            x=res['strike'],
            y=res['flow'],
            line=dict(color='#00d4ff', width=3),
            fill='tozeroy',
            fillcolor='rgba(0,212,255,0.05)'
        ))

        fig_h.update_layout(template="plotly_dark", height=250)

        st.plotly_chart(fig_h, use_container_width=True)

        # =========================================
        # VEX
        # =========================================
        st.subheader("⚡ Vanna Exposure (VEX)")

        fig_v = go.Figure()

        fig_v.add_trace(go.Bar(
            x=res['strike'],
            y=res['Net VEX'],
            marker_color=['#ffaa00' if v > 0 else '#8844ff' for v in res['Net VEX']]
        ))

        fig_v.update_layout(template="plotly_dark", height=250)

        st.plotly_chart(fig_v, use_container_width=True)

        # =========================================
        # TERM STRUCTURE
        # =========================================
        st.subheader("⏳ Gamma Term Structure")

        fig_t = go.Figure()

        fig_t.add_trace(go.Bar(
            x=term['data_exp'],
            y=term['gex'],
            marker_color=['#00ffbb' if v > 0 else '#ff4444' for v in term['gex']]
        ))

        fig_t.update_layout(template="plotly_dark", height=250)

        st.plotly_chart(fig_t, use_container_width=True)

        # =========================================
        # FOOTER
        # =========================================
        st.divider()
        st.caption(f"Dealer Gamma Engine | {datetime.now().strftime('%H:%M:%S')} UTC")

else:
    st.info("Sincronizando com Deribit...")
