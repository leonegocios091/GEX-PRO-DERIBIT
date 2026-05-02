import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.graph_objects as go
from datetime import datetime, timezone
import os

st.set_page_config(layout="wide")

FILE = "gex_surface.csv"

# =========================
# MATH
# =========================
def normal_pdf(x):
    return np.exp(-0.5 * x**2) / np.sqrt(2*np.pi)

# =========================
# LOAD DATA
# =========================
@st.cache_data(ttl=15)
def load_deribit():
    try:
        url = "https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency=BTC&kind=option"
        res = requests.get(url).json().get("result", [])
        df = pd.DataFrame(res)

        parts = df['instrument_name'].str.split('-')
        df['strike'] = pd.to_numeric(parts.str[2], errors='coerce')
        df['tipo'] = parts.str[3]

        df['open_interest'] = pd.to_numeric(df['open_interest'], errors='coerce').fillna(0)

        return df.dropna(subset=['strike'])
    except:
        return None

# =========================
# CALC GEX POR STRIKE
# =========================
def calc_gex(df, S):

    df = df.copy()

    df['iv'] = pd.to_numeric(df['mark_iv'], errors='coerce')/100
    df['iv'] = df['iv'].replace(0, np.nan).fillna(0.5)

    K = df['strike']
    sigma = df['iv']
    T = 0.01

    d1 = (np.log(S/K) + 0.5*sigma**2*T)/(sigma*np.sqrt(T))
    pdf = normal_pdf(d1)

    gamma = pdf/(S*sigma*np.sqrt(T))

    df['gex'] = gamma * df['open_interest'] * S**2

    df.loc[df['tipo']=="P", 'gex'] *= -1

    return df[['strike','gex']]

# =========================
# SAVE SURFACE
# =========================
def save_surface(df, price):

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    df['time'] = now
    df['price'] = price

    if os.path.exists(FILE):
        old = pd.read_csv(FILE)
        df = pd.concat([old, df], ignore_index=True)

    df.to_csv(FILE, index=False)

# =========================
# LOAD HISTORY
# =========================
def load_surface():
    if os.path.exists(FILE):
        df = pd.read_csv(FILE)
        df['time'] = pd.to_datetime(df['time'])
        return df
    return pd.DataFrame()

# =========================
# UI
# =========================
st.title("🔥 GEX HEATMAP INSTITUCIONAL")

df_raw = load_deribit()

if df_raw is not None and not df_raw.empty:

    price = df_raw['estimated_delivery_price'].iloc[0]

    gex_df = calc_gex(df_raw, price)

    # botão coleta
    if st.button("📥 Coletar Snapshot"):
        save_surface(gex_df, price)
        st.success("Snapshot salvo")

    # auto coleta
    if st.checkbox("Auto coletar"):
        save_surface(gex_df, price)

    st.metric("Preço", round(price,2))

    # =========================
    # LOAD HISTÓRICO
    # =========================
    hist = load_surface()

    if not hist.empty:

        st.subheader("📊 Heatmap GEX")

        # pivot para heatmap
        pivot = hist.pivot_table(
            index='strike',
            columns='time',
            values='gex',
            aggfunc='sum'
        )

        pivot = pivot.fillna(0)

        fig = go.Figure(data=go.Heatmap(
            z=pivot.values,
            x=pivot.columns,
            y=pivot.index,
            colorscale='RdBu',
            zmid=0
        ))

        fig.update_layout(
            template="plotly_dark",
            height=600,
            xaxis_title="Tempo",
            yaxis_title="Strike"
        )

        st.plotly_chart(fig, use_container_width=True)

    else:
        st.info("Sem histórico ainda. Clique em coletar.")

else:
    st.warning("Erro ao carregar dados")
