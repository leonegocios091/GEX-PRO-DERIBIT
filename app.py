import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timezone
from scipy.stats import norm

# =========================================
# 1. SETUP
# =========================================
st.set_page_config(page_title="GEX Master Engine Pro", layout="wide")
st_autorefresh(interval=15000, key="hiro_sync_refresh")

# =========================================
# 2. DATA LOADER (COM CACHE)
# =========================================
@st.cache_data(ttl=10)
def carregar_deribit(ticker):
    url = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={ticker}&kind=option"
    try:
        res = requests.get(url, timeout=10).json()['result']
        df = pd.DataFrame(res)

        parts = df['instrument_name'].str.split('-')
        df['strike'] = parts.str[2].astype(float)
        df['data_exp'] = parts.str[1]
        df['tipo'] = parts.str[3]

        return df
    except:
        return None

# =========================================
# 3. BLACK-SCHOLES GEX
# =========================================
def calcular_gex_real(df, S):
    df = df.copy()

    # Tempo até expiração
    df['exp_datetime'] = pd.to_datetime(df['data_exp'], format='%d%b%y', utc=True)
    now = datetime.now(timezone.utc)
    df['T'] = (df['exp_datetime'] - now).dt.total_seconds() / (365 * 24 * 3600)
    df['T'] = df['T'].clip(lower=1e-6)

    # Volatilidade implícita
    df['iv'] = df['mark_iv'] / 100
    df['iv'] = df['iv'].clip(lower=0.01)

    K = df['strike']
    T = df['T']
    sigma = df['iv']

    # d1
    d1 = (np.log(S / K) + (0.5 * sigma**2) * T) / (sigma * np.sqrt(T))

    # Gamma
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))

    # GEX
    df['gex'] = gamma * df['open_interest'] * (S**2)

    # Convenção dealer
    df.loc[df['tipo'] == 'P', 'gex'] *= -1

    return df

# =========================================
# 4. UI
# =========================================
st.sidebar.header("🕹️ Real-Time Engine")
moeda = st.sidebar.selectbox("Ativo", ["BTC", "ETH"])
opacidade_abs = st.sidebar.slider("Opacidade Abs GEX", 0.0, 1.0, 0.15)

df_raw = carregar_deribit(moeda)

# =========================================
# 5. PROCESSAMENTO
# =========================================
if df_raw is not None and not df_raw.empty:

    preco_spot = df_raw['estimated_delivery_price'].iloc[0]

    hoje_utc = datetime.now(timezone.utc).strftime("%d%b%y").upper()
    exp_list = sorted(df_raw['data_exp'].unique())

    selecao_exp = st.sidebar.multiselect(
        "Vencimentos",
        options=exp_list,
        default=[hoje_utc] if hoje_utc in exp_list else [exp_list[0]]
    )

    if selecao_exp:
        df = df_raw[df_raw['data_exp'].isin(selecao_exp)].copy()

        # === GEX REAL ===
        df = calcular_gex_real(df, preco_spot)

        # === AGREGAÇÃO ===
        res = df.groupby('strike').agg({
            'gex': 'sum',
            'open_interest': 'sum'
        }).reset_index()

        res = res.sort_values('strike')

        # === MÉTRICAS ===
        res['Net GEX'] = res['gex'] / 1e9
        res['abs_gex'] = res['Net GEX'].abs()
        res['Net OI'] = (res['open_interest'] * res['strike']) / 1e6

        # === G-FLIP ===
        sign_change = np.where(np.sign(res['Net GEX']).diff() != 0)[0]
        g_flip = res.iloc[sign_change[0]]['strike'] if len(sign_change) > 0 else None

        # === FLOW ===
        res['flow'] = res['Net GEX'].cumsum()

        # =========================================
        # 6. GRÁFICO GEX
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
            width=300,
            name='Net GEX'
        ))

        fig.add_vline(x=preco_spot, line_color="orange",
                      annotation_text=f"SPOT {preco_spot:.0f}")

        if g_flip:
            fig.add_vline(x=g_flip, line_color="white",
                          line_dash="dot", annotation_text="G-FLIP")

        fig.update_layout(
            template="plotly_dark",
            height=500,
            margin=dict(t=30, b=10),
            xaxis=dict(range=[preco_spot * 0.88, preco_spot * 1.12])
        )

        st.plotly_chart(fig, use_container_width=True)

        # =========================================
        # 7. DEALER FLOW
        # =========================================
        st.subheader("🌊 Dealer Hedge Flow")

        fig_h = go.Figure()

        fig_h.add_trace(go.Scatter(
            x=res['strike'],
            y=res['flow'],
            name="Net Hedge Flow",
            line=dict(color='#00d4ff', width=3),
            fill='tozeroy',
            fillcolor='rgba(0,212,255,0.05)'
        ))

        fig_h.update_layout(
            template="plotly_dark",
            height=250,
            margin=dict(t=10, b=10),
            xaxis=dict(range=[preco_spot * 0.9, preco_spot * 1.1])
        )

        st.plotly_chart(fig_h, use_container_width=True)

        # =========================================
        # 8. INFO
        # =========================================
        st.divider()

        st.caption(
            f"Dealer Gamma Engine | Atualizado {datetime.now().strftime('%H:%M:%S')} UTC"
        )

else:
    st.info("Sincronizando com Deribit...")
