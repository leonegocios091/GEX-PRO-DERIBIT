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

        # Proteção contra colunas ausentes
        required_cols = ['instrument_name', 'open_interest', 'mark_iv']
        for col in required_cols:
            if col not in df.columns:
                return None

        parts = df['instrument_name'].str.split('-')

        df['strike'] = pd.to_numeric(parts.str[2], errors='coerce')
        df['data_exp'] = parts.str[1]
        df['tipo'] = parts.str[3]

        # Limpeza crítica
        df = df.dropna(subset=['strike'])
        df['open_interest'] = pd.to_numeric(df['open_interest'], errors='coerce').fillna(0)

        return df

    except:
        return None

# =========================================
# 4. GEX REAL (BLINDADO)
# =========================================
def calcular_gex_real(df, S):
    df = df.copy()

    # --- DATA ---
    df['exp_datetime'] = pd.to_datetime(
        df['data_exp'],
        format='%d%b%y',
        errors='coerce',
        utc=True
    )

    now = datetime.now(timezone.utc)
    df['T'] = (df['exp_datetime'] - now).dt.total_seconds() / (365 * 24 * 3600)
    df['T'] = df['T'].fillna(0).clip(lower=1e-6)

    # --- IV ---
    df['iv'] = pd.to_numeric(df['mark_iv'], errors='coerce') / 100
    df['iv'] = df['iv'].replace(0, np.nan)
    df['iv'] = df['iv'].fillna(df['iv'].median())
    df['iv'] = df['iv'].clip(lower=0.01)

    # --- STRIKE ---
    K = df['strike'].replace(0, np.nan)
    K = K.fillna(method='ffill')

    sigma = df['iv']
    T = df['T']

    # --- d1 protegido ---
    with np.errstate(divide='ignore', invalid='ignore'):
        d1 = (np.log(S / K) + (0.5 * sigma**2) * T) / (sigma * np.sqrt(T))

    d1 = d1.replace([np.inf, -np.inf], 0).fillna(0)

    # --- gamma ---
    gamma = normal_pdf(d1) / (S * sigma * np.sqrt(T))
    gamma = gamma.replace([np.inf, -np.inf], 0).fillna(0)

    # --- GEX ---
    df['gex'] = gamma * df['open_interest'] * (S**2)

    # Convenção dealer
    df.loc[df['tipo'] == 'P', 'gex'] *= -1

    # Limpeza final
    df['gex'] = df['gex'].replace([np.inf, -np.inf], 0).fillna(0)

    return df

# =========================================
# 5. UI
# =========================================
st.sidebar.header("🕹️ Real-Time Engine")
moeda = st.sidebar.selectbox("Ativo", ["BTC", "ETH"])
opacidade_abs = st.sidebar.slider("Opacidade Abs GEX", 0.0, 1.0, 0.15)

df_raw = carregar_deribit(moeda)

# =========================================
# 6. PROCESSAMENTO
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

        df = calcular_gex_real(df, preco_spot)

        res = df.groupby('strike').agg({
            'gex': 'sum',
            'open_interest': 'sum'
        }).reset_index()

        if res.empty:
            st.warning("Falha na agregação.")
            st.stop()

        res = res.sort_values('strike')

        res['Net GEX'] = res['gex'] / 1e9
        res['abs_gex'] = res['Net GEX'].abs()
        res['flow'] = res['Net GEX'].cumsum()

        # --- G-FLIP ---
        sign_change = np.where(np.sign(res['Net GEX']).diff() != 0)[0]
        g_flip = res.iloc[sign_change[0]]['strike'] if len(sign_change) > 0 else None

        # =========================================
        # GRÁFICO
        # =========================================
        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=res['strike'],
            y=res['abs_gex'],
            fill='tozeroy',
            mode='none',
            fillcolor=f'rgba(255,255,0,{opacidade_abs})'
        ))

        cores = ['#00ffbb' if v > 0 else '#ff4444' for v in res['Net GEX']]

        fig.add_trace(go.Bar(
            x=res['strike'],
            y=res['Net GEX'],
            marker_color=cores
        ))

        fig.add_vline(x=preco_spot, line_color="orange")

        if g_flip:
            fig.add_vline(x=g_flip, line_color="white", line_dash="dot")

        fig.update_layout(
            template="plotly_dark",
            height=500
        )

        st.plotly_chart(fig, use_container_width=True)

        # =========================================
        # FLOW
        # =========================================
        fig_h = go.Figure()

        fig_h.add_trace(go.Scatter(
            x=res['strike'],
            y=res['flow'],
            line=dict(color='#00d4ff', width=3)
        ))

        fig_h.update_layout(template="plotly_dark", height=250)

        st.plotly_chart(fig_h, use_container_width=True)

        st.caption(f"Atualizado {datetime.now().strftime('%H:%M:%S')} UTC")

else:
    st.info("Sincronizando com Deribit...")
