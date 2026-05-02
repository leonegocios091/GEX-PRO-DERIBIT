import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timezone

# =========================================
# CONFIG
# =========================================
st.set_page_config(page_title="GEX Trading Engine", layout="wide")
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

    with np.errstate(divide='ignore', invalid='ignore'):
        d1 = (np.log(S/K) + 0.5*sigma**2*T)/(sigma*np.sqrt(T))
        d2 = d1 - sigma*np.sqrt(T)

    d1 = d1.replace([np.inf, -np.inf], 0).fillna(0)
    d2 = d2.replace([np.inf, -np.inf], 0).fillna(0)

    pdf = normal_pdf(d1)

    gamma = pdf/(S*sigma*np.sqrt(T))
    vanna = -pdf*d2/sigma
    charm = -pdf*(np.log(S/K)/(T*sigma*np.sqrt(T)))

    df['gex'] = gamma * df['open_interest'] * S**2
    df['vex'] = vanna * df['open_interest'] * S
    df['charm'] = charm * df['open_interest'] * S

    df.loc[df['tipo']=='P', ['gex','vex','charm']] *= -1

    df[['gex','vex','charm']] = df[['gex','vex','charm']].replace([np.inf, -np.inf], 0).fillna(0)

    return df

# =========================================
# PROFILE
# =========================================
def gamma_profile(df, spot_range):
    return np.array([calc_exposure(df, s)['gex'].sum() for s in spot_range]) / 1e9

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
# ESTADO INICIAL
# =========================================
if "trades" not in st.session_state:
    st.session_state["trades"] = []

if "position" not in st.session_state:
    st.session_state["position"] = None

# =========================================
# UI
# =========================================
st.sidebar.header("Configuração")
ticker = st.sidebar.selectbox("Ativo", ["BTC","ETH"])
auto = st.sidebar.toggle("Auto Trade (Simulado)")

df_raw = load_data(ticker)

# =========================================
# MAIN
# =========================================
if df_raw is not None and not df_raw.empty:

    spot = df_raw['estimated_delivery_price'].iloc[0]

    df = calc_exposure(df_raw, spot)

    res = df.groupby('strike').agg({'gex':'sum','vex':'sum','charm':'sum'}).reset_index()
    res = res.sort_values('strike')

    res['Net GEX'] = res['gex']/1e9
    res['Net VEX'] = res['vex']/1e9
    res['Net Charm'] = res['charm']/1e9

    spot_range = np.linspace(spot*0.9, spot*1.1, 30)
    profile = gamma_profile(df_raw, spot_range)

    score = calc_score(res, profile, spot_range)
    signal = get_signal(score)

    # =========================================
    # DASHBOARD
    # =========================================
    st.title("📊 GEX Engine (Simulação Profissional)")

    col1, col2, col3 = st.columns(3)
    col1.metric("Score", round(score,1))
    col2.metric("Sinal", signal)
    col3.metric("Preço", round(spot,2))

    st.info("⚠️ Modo simulação ativo")

    # =========================================
    # EXECUÇÃO SIMULADA
    # =========================================
    if auto:

        pos = st.session_state["position"]

        # ABRIR POSIÇÃO
        if pos is None and signal in ["LONG","SHORT"]:
            trade = {
                "tipo": signal,
                "entrada": spot,
                "hora": datetime.now().strftime("%H:%M:%S")
            }
            st.session_state["position"] = trade
            st.session_state["trades"].append(trade)

        # FECHAR POSIÇÃO
        elif pos is not None and signal != pos["tipo"] and signal != "NEUTRO":

            pnl = (spot - pos["entrada"]) if pos["tipo"]=="LONG" else (pos["entrada"] - spot)

            pos["saida"] = spot
            pos["pnl"] = pnl
            pos["hora_saida"] = datetime.now().strftime("%H:%M:%S")

            st.session_state["position"] = None

    # =========================================
    # HISTÓRICO
    # =========================================
    st.subheader("📜 Histórico de Trades")

    trades_df = pd.DataFrame(st.session_state["trades"])

    if not trades_df.empty:

        # Blindagem total
        if "pnl" not in trades_df.columns:
            trades_df["pnl"] = 0.0
        if "saida" not in trades_df.columns:
            trades_df["saida"] = np.nan
        if "hora_saida" not in trades_df.columns:
            trades_df["hora_saida"] = ""

        st.dataframe(trades_df)

        total_pnl = trades_df["pnl"].fillna(0).sum()
        st.metric("PnL Total (simulado)", round(total_pnl,2))

    # =========================================
    # PNL EM ABERTO
    # =========================================
    pos = st.session_state.get("position")

    if pos is not None:
        pnl_aberto = (spot - pos["entrada"]) if pos["tipo"]=="LONG" else (pos["entrada"] - spot)
        st.info(f"📈 PnL em aberto: {pnl_aberto:.2f}")

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
