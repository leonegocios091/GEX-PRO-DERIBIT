import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timezone

# 1. CONFIGURAÇÃO E AUTO-REFRESH
st.set_page_config(page_title="GEX Master Engine Pro", layout="wide")
st_autorefresh(interval=30000, key="datarefresh")

# 2. FUNÇÃO DE FORMATAÇÃO PARA AS MÉTRICAS (Texto)
def formatar_escala(valor):
    if abs(valor) >= 1_000_000_000:
        return f"{valor / 1_000_000_000:.2f}B"
    elif abs(valor) >= 1_000_000:
        return f"{valor / 1_000_000:.2f}M"
    return f"{valor:,.0f}"

# 3. INTERFACE LATERAL
st.sidebar.header("⚙️ Painel de Controle")
moeda = st.sidebar.selectbox("Ativo", ["BTC", "ETH"])
modo_tema = st.sidebar.radio("Tema", ["Dark", "Light"])
modo_visao = st.sidebar.radio("Métrica", ["Net GEX", "Open Interest (OI)", "DEX"])
cor_abs = st.sidebar.selectbox("Cor Liquidez Abs", ["Roxo", "Amarelo"])

# 4. CARREGAMENTO DE DADOS
def carregar_dados(ticker):
    url = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={ticker}&kind=option"
    try:
        res = requests.get(url, timeout=10).json()
        return pd.DataFrame(res['result'])
    except: return None

df_raw = carregar_dados(moeda)

if df_raw is not None and not df_raw.empty:
    # Tratamento dos dados
    df_raw['strike'] = df_raw['instrument_name'].str.split('-').str[2].astype(float)
    df_raw['tipo'] = df_raw['instrument_name'].str.split('-').str[3]
    df_raw['data_exp'] = df_raw['instrument_name'].str.split('-').str[1]
    preco_spot = df_raw['estimated_delivery_price'].iloc[0]

    # --- CORREÇÃO 0DTE ---
    # A Deribit usa o formato DDMMMYY (ex: 30APR26). 
    # Forçamos o UTC para bater com o fechamento da exchange.
    hoje_utc = datetime.now(timezone.utc).strftime("%d%b%y").upper()
    exp_list = sorted(df_raw['data_exp'].unique())
    
    selecao_exp = st.sidebar.multiselect(
        "Expirações", 
        options=exp_list, 
        default=[exp_list[0]],
        format_func=lambda x: f"⚡ {x} (0DTE)" if x == hoje_utc else x
    )

    if selecao_exp:
        df = df_raw[df_raw['data_exp'].isin(selecao_exp)].copy()
        
        # Cálculos de GEX/OI
        df['gex'] = df.apply(lambda x: x['open_interest'] if x['tipo'] == 'C' else -x['open_interest'], axis=1)
        gex_strike = df.groupby('strike')['gex'].sum().reset_index()
        oi_strike = df.groupby('strike')['open_interest'].sum().reset_index()

        # Cálculo de Níveis Críticos
        call_wall = df[df['tipo'] == 'C'].groupby('strike')['open_interest'].sum().idxmax()
        put_wall = df[df['tipo'] == 'P'].groupby('strike')['open_interest'].sum().idxmax()
        gamma_flip = gex_strike.iloc[(gex_strike['gex']).abs().argsort()[:1]]['strike'].values[0]

        # Estética
        template = "plotly_dark" if modo_tema == "Dark" else "plotly_white"
        bg_color = "#0e1117" if modo_tema == "Dark" else "#ffffff"
        cor_fill = 'rgba(100, 80, 250, 0.2)' if cor_abs == "Roxo" else 'rgba(255, 255, 0, 0.2)'

        # --- GRÁFICO ---
        fig = go.Figure()

        # Sombra de Gamma Absoluto
        fig.add_trace(go.Scatter(x=oi_strike['strike'], y=oi_strike['open_interest'], fill='tozeroy', mode='none', fillcolor=cor_fill, name='Abs Gex'))

        # Barras Principais
        y_vals = gex_strike['gex'] if modo_visao == "Net GEX" else oi_strike['open_interest']
        fig.add_trace(go.Bar(x=gex_strike['strike'], y=y_vals, marker_color=['#00ffbb' if v > 0 else '#ff4444' for v in y_vals], name=modo_visao))

        # --- CORREÇÃO ESCALA M/B E STRIKES 500 ---
        fig.update_layout(
            template=template, paper_bgcolor=bg_color, plot_bgcolor=bg_color,
            xaxis=dict(
                title="STRIKE PRICE",
                range=[preco_spot - 4000, preco_spot + 4000], 
                dtick=500, # Força strikes de 500 em 500
                tickformat="d"
            ),
            yaxis=dict(
                title=modo_visao,
                tickformat=".2s", # Força escala M e B (ex: 1.5M, 2.0B)
                exponentformat="SI"
            ),
            height=600
        )

        # Linhas de Níveis
        fig.add_vline(x=preco_spot, line_color="orange", annotation_text="SPOT")
        fig.add_vline(x=call_wall, line_color="#00ffbb", line_dash="dash", annotation_text="Call Wall")
        fig.add_vline(x=put_wall, line_color="#ff4444", line_dash="dash", annotation_text="Put Wall")
        fig.add_vline(x=gamma_flip, line_color="gray", line_dash="dot", annotation_text="G-Flip")

        st.plotly_chart(fig, use_container_width=True)

        # --- DADOS TRADINGVIEW ---
        st.subheader("📋 Pine Script Data")
        pine_string = f"CallWall,{call_wall},PutWall,{put_wall},GammaFlip,{gamma_flip},Spot,{preco_spot:.0f}"
        st.code(pine_string, language="text")

        # Métricas Rodapé
        c1, c2, c3 = st.columns(3)
        c1.metric("Spot", f"${preco_spot:,.2f}")
        c2.metric("OI Total (F)", formatar_escala(df['open_interest'].sum()))
        c3.metric("G-Flip", f"${gamma_flip:,.0f}")
else:
    st.info("Aguardando dados...")
