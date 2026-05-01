import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timezone

# 1. CONFIGURAÇÃO E AUTO-REFRESH (30s)
st.set_page_config(page_title="GEX Master Engine Pro", layout="wide")
st_autorefresh(interval=30000, key="datarefresh")

# 2. FUNÇÃO DE FORMATAÇÃO PARA TEXTOS (M/B)
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
modo_visao = st.sidebar.radio("Métrica Principal", ["Net GEX", "Net DEX (Delta)", "Open Interest (OI)"])
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
    # Tratamento de dados base
    df_raw['strike'] = df_raw['instrument_name'].str.split('-').str[2].astype(float)
    df_raw['tipo'] = df_raw['instrument_name'].str.split('-').str[3]
    df_raw['data_exp'] = df_raw['instrument_name'].str.split('-').str[1]
    preco_spot = df_raw['estimated_delivery_price'].iloc[0]

    # --- CORREÇÃO 0DTE (Fuso Deribit) ---
    # Pegamos a data atual em UTC para bater com o vencimento da exchange
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
        
        # --- CÁLCULOS DE GEX E DEX ---
        # Gamma e Delta Proxy (OI como base de liquidez)
        df['gex_pos'] = df.apply(lambda x: x['open_interest'] if x['tipo'] == 'C' else 0, axis=1)
        df['gex_neg'] = df.apply(lambda x: -x['open_interest'] if x['tipo'] == 'P' else 0, axis=1)
        df['net_gex'] = df['gex_pos'] + df['gex_neg']
        
        # DEX (Delta) - Peso maior para strikes próximos ao preço
        df['net_dex'] = df.apply(lambda x: (x['open_interest'] * x['strike']) if x['tipo'] == 'C' else (-x['open_interest'] * x['strike']), axis=1)

        # Agrupamento por Strike
        resumo = df.groupby('strike').agg({
            'gex_pos': 'sum',
            'gex_neg': 'sum',
            'net_gex': 'sum',
            'net_dex': 'sum',
            'open_interest': 'sum'
        }).reset_index()

        # Níveis Críticos
        call_wall = df[df['tipo'] == 'C'].groupby('strike')['open_interest'].sum().idxmax()
        put_wall = df[df['tipo'] == 'P'].groupby('strike')['open_interest'].sum().idxmax()
        gamma_flip = resumo.iloc[(resumo['net_gex']).abs().argsort()[:1]]['strike'].values[0]

        # Configurações de Estética
        template = "plotly_dark" if modo_tema == "Dark" else "plotly_white"
        bg_color = "#0e1117" if modo_tema == "Dark" else "#ffffff"
        cor_fill = 'rgba(100, 80, 250, 0.2)' if cor_abs == "Roxo" else 'rgba(255, 255, 0, 0.2)'

        # --- GRÁFICO ---
        fig = go.Figure()

        # Sombra de Gamma Absoluto
        fig.add_trace(go.Scatter(x=resumo['strike'], y=resumo['open_interest'], fill='tozeroy', mode='none', fillcolor=cor_fill, name='Abs Gex'))

        # Seleção de Métrica para Plotagem
        if modo_visao == "Net GEX":
            y_vals = resumo['net_gex']
            color_map = ['#00ffbb' if v > 0 else '#ff4444' for v in y_vals]
        elif modo_visao == "Net DEX (Delta)":
            y_vals = resumo['net_dex']
            color_map = ['#00d4ff' if v > 0 else '#ff9900' for v in y_vals]
        else:
            y_vals = resumo['open_interest']
            color_map = ['#6450fa'] * len(y_vals)

        # Barras Principais
        fig.add_trace(go.Bar(x=resumo['strike'], y=y_vals, marker_color=color_map, name=modo_visao))

        # --- AJUSTE DE ESCALA M/B E STRIKES 500 EM 500 ---
        fig.update_layout(
            template=template, paper_bgcolor=bg_color, plot_bgcolor=bg_color,
            xaxis=dict(
                title="STRIKE PRICE",
                range=[preco_spot - 5000, preco_spot + 5000], 
                dtick=500, # Strikes de 500 em 500
                tickformat="d"
            ),
            yaxis=dict(
                title=modo_visao,
                tickformat=".2s", # Escala 1M, 10M, 1B de forma limpa
                exponentformat="SI"
            ),
            height=650,
            bargap=0.1
        )

        # Linhas de Referência
        fig.add_vline(x=preco_spot, line_color="orange", annotation_text="SPOT", line_width=2)
        fig.add_vline(x=call_wall, line_color="#00ffbb", line_dash="dash", annotation_text="Call Wall")
        fig.add_vline(x=put_wall, line_color="#ff4444", line_dash="dash", annotation_text="Put Wall")
        fig.add_vline(x=gamma_flip, line_color="gray", line_dash="dot", annotation_text="G-Flip")

        st.plotly_chart(fig, use_container_width=True)

        # --- SEÇÃO TRADINGVIEW ---
        st.subheader("📋 Dados para TradingView")
        pine_string = (
            f"OI+,{call_wall+1000},CallWall,{call_wall},Spot,{preco_spot:.0f},"
            f"GammaFlip,{gamma_flip},PutWall,{put_wall},OI-,{put_wall-1000}"
        )
        st.code(pine_string, language="text")

        # --- MÉTRICAS DETALHADAS ---
        st.divider()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Gamma Positivo (+)", formatar_escala(resumo['gex_pos'].sum()))
        c2.metric("Gamma Negativo (-)", formatar_escala(abs(resumo['gex_neg'].sum())))
        c3.metric("Net Gamma Total", formatar_escala(resumo['net_gex'].sum()))
        c4.metric("Net Delta Total", formatar_escala(resumo['net_dex'].sum()))

else:
    st.info("Conectando à Deribit... (Se o 0DTE não aparecer, aguarde a atualização de mercado)")
