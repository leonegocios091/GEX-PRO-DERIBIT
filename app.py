import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timezone
import ccxt

# =========================================
# CONFIG
# =========================================
st.set_page_config(page_title="GEX Auto Trader", layout="wide")
st_autorefresh(interval=20000, key="refresh")

# =========================================
# MATH
# =========================================
def normal_pdf(x):
    return np.exp(-0.5 * x**2) / np.sqrt(2*np.pi)

# =========================================
# DATA
# =========================================
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

# =========================================
# EXPOSURE ENGINE
# =========================================
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

# =========================================
# PROFILE
# =========================================
def gamma_profile(df, spot_range):
    out = []
    for s in spot_range:
        out.append(calc_exposure(df, s)['gex'].sum())
    return np.array(out)/1e9

# =========================================
# SCORE
# =========================================
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

# =========================================
# SIGNAL
# =========================================
def get_signal(score):
    if score > 70:
        return "LONG"
    elif score < 30:
        return "SHORT"
    return "NEUTRO"

# =========================================
# EXCHANGE
# =========================================
def conectar():
    return ccxt.binance({
        "apiKey": st.secrets["API_KEY"],
        "secret": st.secrets["API_SECRET"],
        "enableRateLimit": True
    })

# =========================================
# TRADE EXECUTION
# =========================================
def executar_trade(signal, price):

    exchange = conectar()
    symbol = "BTC/USDT"
    size = 0.001

    try:
        if signal == "LONG":
            order = exchange.create_market_buy_order(symbol, size)
            return f"LONG executado @ {price}"

        elif signal == "SHORT":
            order = exchange.create_market_sell_order(symbol, size)
            return f"SHORT executado @ {price}"

        return "Sem trade"

    except Exception as e:
        return f"Erro: {str(e)}"

# =========================================
# UI
# =========================================
st.sidebar.header("Configuração")
ticker = st.sidebar.selectbox("Ativo", ["BTC","ETH"])
auto_mode = st.sidebar.toggle("Auto Trade")

df_raw = load_data(ticker)

# =========================================
# MAIN
# =========================================
if df_raw is not None and not df_raw.empty:

    spot = df_raw['estimated_delivery_price'].iloc[0]

    df = calc_exposure(df_raw, spot)

    res = df.groupby('strike').agg({
        'gex':'sum',
        'vex':'sum',
        'charm':'sum'
    }).reset_index().sort_values('strike')

    res['Net GEX'] = res['gex']/1e9
    res['Net VEX'] = res['vex']/1e9
    res['Net Charm'] = res['charm']/1e9

    # PROFILE
    spot_range = np.linspace(spot*0.9, spot*1.1, 30)
    profile = gamma_profile(df_raw, spot_range)

    # SCORE + SIGNAL
    score = calc_score(res, profile, spot_range)
    signal = get_signal(score)

    # =========================================
    # DASHBOARD
    # =========================================
    st.title("🤖 GEX Auto Trading Engine")

    col1, col2, col3 = st.columns(3)
    col1.metric("Score", round(score,1))
    col2.metric("Sinal", signal)
    col3.metric("Preço", round(spot,2))

    # ALERTAS
    if score > 70:
        st.warning("🚀 Possível tendência de alta")
    elif score < 30:
        st.warning("🔻 Possível queda forte")

    # =========================================
    # CONTROLE DE TRADE
    # =========================================
    if "last_signal" not in st.session_state:
        st.session_state["last_signal"] = None

    if auto_mode and signal != "NEUTRO":

        if signal != st.session_state["last_signal"]:
            result = executar_trade(signal, spot)
            st.session_state["last_signal"] = signal
            st.success(result)
        else:
            st.info("Aguardando novo sinal...")

    # =========================================
    # GRÁFICOS
    # =========================================
    fig = go.Figure()
    fig.add_trace(go.Bar(x=res['strike'], y=res['Net GEX']))
    fig.add_vline(x=spot)
    fig.update_layout(template="plotly_dark", height=300)
    st.plotly_chart(fig, use_container_width=True)

    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=spot_range, y=profile))
    fig2.add_vline(x=spot)
    fig2.update_layout(template="plotly_dark", height=300)
    st.plotly_chart(fig2, use_container_width=True)

else:
    st.info("Carregando dados...")
