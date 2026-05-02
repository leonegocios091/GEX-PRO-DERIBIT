import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.graph_objects as go
from datetime import datetime, timezone

st.set_page_config(layout="wide")

# =============================
# DATA
# =============================
@st.cache_data(ttl=20)
def load_data():
    url = "https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency=BTC&kind=option"
    res = requests.get(url).json().get("result", [])
    df = pd.DataFrame(res)

    parts = df['instrument_name'].str.split('-')
    df['strike'] = pd.to_numeric(parts.str[2], errors='coerce')
    df['tipo'] = parts.str[3]

    df['open_interest'] = pd.to_numeric(df['open_interest'], errors='coerce').fillna(0)

    return df.dropna(subset=['strike'])

# =============================
# GEX SIMPLES (rápido)
# =============================
def calc_levels(df):
    df['call_oi'] = np.where(df['tipo']=="C", df['open_interest'], 0)
    df['put_oi'] = np.where(df['tipo']=="P", df['open_interest'], 0)

    res = df.groupby('strike').agg({
        'call_oi':'sum',
        'put_oi':'sum'
    }).reset_index()

    res['net'] = res['call_oi'] - res['put_oi']
    res['total'] = res['call_oi'] + res['put_oi']

    # níveis principais
    call_wall = res.sort_values('call_oi', ascending=False).iloc[0]['strike']
    put_wall = res.sort_values('put_oi', ascending=False).iloc[0]['strike']
    max_pain = res.sort_values('total').iloc[0]['strike']

    # gamma flip (aproximação)
    res['cum'] = res['net'].cumsum()
    flip = res.iloc[(res['cum']).abs().argsort()[:1]]['strike'].values[0]

    return res, call_wall, put_wall, max_pain, flip

# =============================
# MAIN
# =============================
st.title("🔥 GEX Institutional Dashboard")

df = load_data()

if df is not None and not df.empty:

    price = df['estimated_delivery_price'].iloc[0]

    res, call_wall, put_wall, max_pain, flip = calc_levels(df)

    # =============================
    # LAYOUT
    # =============================
    col1, col2 = st.columns([4,1])

    # =============================
    # GRÁFICO PRINCIPAL
    # =============================
    with col1:

        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=res['strike'],
            y=res['net'],
            mode='lines',
            name="Net Flow"
        ))

        # linhas institucionais
        fig.add_vline(x=price, line_color="white")
        fig.add_vline(x=flip, line_color="yellow", line_dash="dash", annotation_text="Gamma Flip")
        fig.add_vline(x=call_wall, line_color="green", annotation_text="Call Wall")
        fig.add_vline(x=put_wall, line_color="red", annotation_text="Put Wall")

        fig.update_layout(template="plotly_dark", height=500)

        st.plotly_chart(fig, use_container_width=True)

    # =============================
    # PERFIL LATERAL
    # =============================
    with col2:

        st.subheader("📊 Liquidity Map")

        fig2 = go.Figure()

        fig2.add_trace(go.Bar(
            y=res['strike'],
            x=res['call_oi'],
            orientation='h',
            name="Calls"
        ))

        fig2.add_trace(go.Bar(
            y=res['strike'],
            x=-res['put_oi'],
            orientation='h',
            name="Puts"
        ))

        fig2.update_layout(
            template="plotly_dark",
            height=500,
            barmode='overlay'
        )

        st.plotly_chart(fig2, use_container_width=True)

    # =============================
    # NÍVEIS
    # =============================
    st.subheader("📌 Níveis Institucionais")

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Preço", round(price,2))
    c2.metric("Gamma Flip", flip)
    c3.metric("Call Wall", call_wall)
    c4.metric("Put Wall", put_wall)

else:
    st.warning("Erro ao carregar dados")
