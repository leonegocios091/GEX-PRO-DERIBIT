import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.graph_objects as go
from datetime import datetime, timezone
import os

# =========================================
# CONFIG
# =========================================
st.set_page_config(page_title="GEX Collector", layout="wide")

FILE_NAME = "gex_history.csv"
TICKER = "BTC"

# =========================================
# MATH
# =========================================
def normal_pdf(x):
    return np.exp(-0.5 * x**2) / np.sqrt(2*np.pi)

# =========================================
# LOAD DERIBIT
# =========================================
@st.cache_data(ttl=20)
def load_deribit():
    try:
        url = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={TICKER}&kind=option"
        res = requests.get(url).json().get("result", [])

        if not res:
            return None

        df = pd.DataFrame(res)

        parts = df['instrument_name'].str.split('-')
        df['strike'] = pd.to_numeric(parts.str[2], errors='coerce')
        df['exp'] = parts.str[1]
        df['tipo'] = parts.str[3]

        df = df.dropna(subset=['strike'])
        df['open_interest'] = pd.to_numeric(df['open_interest'], errors='coerce').fillna(0)

        return df

    except:
        return None

# =========================================
# CALC GEX
# =========================================
def calc_gex(df, S):

    df = df.copy()

    df['exp_datetime'] = pd.to_datetime(df['exp'], format='%d%b%y', errors='coerce', utc=True)
    now = datetime.now(timezone.utc)

    df['T'] = (df['exp_datetime'] - now).dt.total_seconds() / (365*24*3600)
    df['T'] = df['T'].clip(lower=1e-6)

    df['iv'] = pd.to_numeric(df['mark_iv'], errors='coerce')/100
    df['iv'] = df['iv'].replace(0, np.nan).fillna(df['iv'].median()).clip(lower=0.01)

    K = df['strike']
    sigma = df['iv']
    T = df['T']

    d1 = (np.log(S/K) + 0.5*sigma**2*T)/(sigma*np.sqrt(T))
    pdf = normal_pdf(d1)

    gamma = pdf/(S*sigma*np.sqrt(T))

    df['gex'] = gamma * df['open_interest'] * S**2

    df.loc[df['tipo']=='P', 'gex'] *= -1

    return df['gex'].sum() / 1e9

# =========================================
# SAVE
# =========================================
def save_row(timestamp, price, gex):

    new = pd.DataFrame([{
        "time": timestamp,
        "price": price,
        "gex": gex
    }])

    if os.path.exists(FILE_NAME):
        old = pd.read_csv(FILE_NAME)
        df = pd.concat([old, new], ignore_index=True)
    else:
        df = new

    df.to_csv(FILE_NAME, index=False)

# =========================================
# LOAD HISTORY
# =========================================
def load_history():
    if os.path.exists(FILE_NAME):
        df = pd.read_csv(FILE_NAME)
        df["time"] = pd.to_datetime(df["time"])
        return df
    return pd.DataFrame()

# =========================================
# MAIN
# =========================================
st.title("📊 GEX Histórico (Coletor + Visualização)")

df_raw = load_deribit()

if df_raw is not None and not df_raw.empty:

    price = df_raw['estimated_delivery_price'].iloc[0]
    gex = calc_gex(df_raw, price)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # botão manual
    if st.button("Coletar agora"):
        save_row(now, price, gex)
        st.success("Dado salvo!")

    # coleta automática simples
    if st.checkbox("Auto coletar ao atualizar"):
        save_row(now, price, gex)

    st.metric("Preço atual", round(price,2))
    st.metric("GEX atual", round(gex,4))

    # carregar histórico
    hist = load_history()

    if not hist.empty:

        st.subheader("📈 Evolução")

        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=hist["time"],
            y=hist["price"],
            name="Preço",
            yaxis="y1"
        ))

        fig.add_trace(go.Scatter(
            x=hist["time"],
            y=hist["gex"],
            name="GEX",
            yaxis="y2"
        ))

        fig.update_layout(
            template="plotly_dark",
            height=400,
            yaxis=dict(title="Preço"),
            yaxis2=dict(title="GEX", overlaying='y', side='right')
        )

        st.plotly_chart(fig, use_container_width=True)

        st.subheader("📜 Dados")
        st.dataframe(hist.tail(50))

    else:
        st.info("Ainda sem dados históricos. Clique em 'Coletar agora'.")

else:
    st.warning("Erro ao carregar dados da Deribit")
