import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timezone

st.set_page_config(page_title="GEX Trading Engine", layout="wide")
st_autorefresh(interval=15000, key="refresh")

# ==============================
# MATH
# ==============================
def normal_pdf(x):
    return np.exp(-0.5 * x**2) / np.sqrt(2*np.pi)

# ==============================
# DATA
# ==============================
@st.cache_data(ttl=10)
def load_data(ticker):
    try:
        url = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={ticker}&kind=option"
        res = requests.get(url).json().get("result", [])
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

# ==============================
# EXPOSURES
# ==============================
def calc_exposure(df, S):
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
    d2 = d1 - sigma*np.sqrt(T)

    pdf = normal_pdf(d1)

    gamma = pdf/(S*sigma*np.sqrt(T))
    vanna = -pdf*d2/sigma
    charm = -pdf*(np.log(S/K)/(T*sigma*np.sqrt(T)))

    df['gex'] = gamma * df['open_interest'] * S**2
    df['vex'] = vanna * df['open_interest'] * S
    df['charm'] = charm * df['open_interest'] * S

    df.loc[df['tipo']=='P', ['gex','vex','charm']] *= -1

    return df.fillna(0)

# ==============================
# PROFILE
# ==============================
def gamma_profile(df, spot_range):
    out = []
    for s in spot_range:
        out.append(calc_exposure(df, s)['gex'].sum())
    return np.array(out)/1e9

# ==============================
# SCORE ENGINE
# ==============================
def calc_score(res, profile, spot_range):
    gex = res['Net GEX'].sum()
    vex = res['Net VEX'].sum()
    charm = res['Net Charm'].sum()

    slope = (profile[-1] - profile[0])/(spot_range[-1]-spot_range[0])

    score = 50

    score += np.tanh(gex)*20
    score += np.tanh(slope)*20
    score += np.tanh(vex)*10
    score += np.tanh(charm)*10

    return np.clip(score, 0, 100)

# ==============================
# SIGNAL
# ==============================
def get_signal(score):
    if score > 65:
        return "LONG", "Alta confiança"
    elif score < 35:
        return "SHORT", "Alta confiança"
    else:
        return "NEUTRO", "Baixa confiança"

# ==============================
# UI
# ==============================
st.sidebar.header("Config")
ticker = st.sidebar.selectbox("Ativo", ["BTC","ETH"])

df_raw = load_data(ticker)

if df_raw is not None and not df_raw.empty:

    spot = df_raw['estimated_delivery_price'].iloc[0]

    df = calc_exposure(df_raw, spot)

    res = df.groupby('strike').agg({'gex':'sum','vex':'sum','charm':'sum'}).reset_index()
    res = res.sort_values('strike')

    res['Net GEX'] = res['gex']/1e9
    res['Net VEX'] = res['vex']/1e9
    res['Net Charm'] = res['charm']/1e9

    # PROFILE
    spot_range = np.linspace(spot*0.9, spot*1.1, 30)
    profile = gamma_profile(df_raw, spot_range)

    # SCORE
    score = calc_score(res, profile, spot_range)
    signal, conf = get_signal(score)

    # ==============================
    # DASHBOARD
    # ==============================
    st.subheader("📊 Trading Engine")

    col1, col2, col3 = st.columns(3)
    col1.metric("Score", round(score,1))
    col2.metric("Sinal", signal)
    col3.metric("Confiança", conf)

    # ALERTA
    if score > 70:
        st.warning("🚨 Mercado pode entrar em tendência forte")
    elif score < 30:
        st.warning("🚨 Mercado pode cair com força")

    # ==============================
    # GEX
    # ==============================
    fig = go.Figure()
    fig.add_trace(go.Bar(x=res['strike'], y=res['Net GEX']))
    fig.add_vline(x=spot)
    fig.update_layout(template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)

    # PROFILE
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=spot_range, y=profile))
    fig2.add_vline(x=spot)
    fig2.update_layout(template="plotly_dark")
    st.plotly_chart(fig2, use_container_width=True)

else:
    st.info("Carregando...")
