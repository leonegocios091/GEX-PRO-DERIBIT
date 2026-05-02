import streamlit as st
import pandas as pd
import numpy as np
import ccxt
import plotly.graph_objects as go

st.set_page_config(page_title="Backtest Engine", layout="wide")

# =========================================
# CARREGAR DADOS HISTÓRICOS
# =========================================
@st.cache_data
def load_ohlc():
    exchange = ccxt.binance()
    ohlc = exchange.fetch_ohlcv("BTC/USDT", timeframe="1h", limit=500)

    df = pd.DataFrame(ohlc, columns=["time","open","high","low","close","volume"])
    df["time"] = pd.to_datetime(df["time"], unit="ms")

    return df

# =========================================
# GERADOR DE SINAL (PROXY)
# =========================================
def gerar_sinal(df):

    # proxy simples usando momentum + volatilidade
    df["ret"] = df["close"].pct_change()
    df["vol"] = df["ret"].rolling(10).std()

    df["score"] = (
        np.tanh(df["ret"]*10)*40 +
        np.tanh(df["vol"]*10)*20
    ) + 50

    def map_signal(s):
        if s > 65:
            return "LONG"
        elif s < 35:
            return "SHORT"
        return "NEUTRO"

    df["signal"] = df["score"].apply(map_signal)

    return df

# =========================================
# BACKTEST ENGINE
# =========================================
def backtest(df):

    position = None
    entry = 0
    trades = []

    equity = 0
    equity_curve = []

    for i in range(len(df)):

        price = df["close"].iloc[i]
        signal = df["signal"].iloc[i]

        # abrir posição
        if position is None and signal in ["LONG","SHORT"]:
            position = signal
            entry = price

        # fechar posição
        elif position is not None and signal != position and signal != "NEUTRO":

            pnl = (price - entry) if position=="LONG" else (entry - price)

            trades.append(pnl)

            equity += pnl
            position = None

        equity_curve.append(equity)

    return trades, equity_curve

# =========================================
# EXECUÇÃO
# =========================================
df = load_ohlc()
df = gerar_sinal(df)

trades, equity_curve = backtest(df)

# =========================================
# MÉTRICAS
# =========================================
if trades:

    trades_arr = np.array(trades)

    total_pnl = trades_arr.sum()
    winrate = (trades_arr > 0).mean() * 100
    avg_win = trades_arr[trades_arr>0].mean() if (trades_arr>0).any() else 0
    avg_loss = trades_arr[trades_arr<=0].mean() if (trades_arr<=0).any() else 0

    equity = pd.Series(equity_curve)
    peak = equity.cummax()
    drawdown = equity - peak
    max_dd = drawdown.min()

    # =========================================
    # DASHBOARD
    # =========================================
    st.title("📊 Backtest Real (Proxy GEX)")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("PnL Total", round(total_pnl,2))
    col2.metric("Winrate", f"{winrate:.1f}%")
    col3.metric("Média Gain", round(avg_win,2))
    col4.metric("Média Loss", round(avg_loss,2))

    st.metric("Max Drawdown", round(max_dd,2))

    # =========================================
    # EQUITY CURVE
    # =========================================
    fig = go.Figure()
    fig.add_trace(go.Scatter(y=equity_curve, name="Equity"))
    fig.update_layout(template="plotly_dark", height=400)
    st.plotly_chart(fig, use_container_width=True)

else:
    st.warning("Sem trades suficientes")
