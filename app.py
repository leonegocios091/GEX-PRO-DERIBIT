import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timezone

# 1. CONFIGURAÇÃO E AUTO-REFRESH
st.set_page_config(page_title="GEX Master Engine Pro", layout="wide")
st_autorefresh(interval=30000, key="datarefresh")

# 2. FUNÇÃO DE FORMATAÇÃO DE ESCALA (PARA MÉTRICAS E EIXOS)
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
modo_visao = st.sidebar.radio("Métrica", ["Net GEX", "Open Interest (OI)", "Net DEX"])
cor_abs = st.sidebar.selectbox("Cor Gex Abs", ["Roxo", "Amarelo"])

# 4. CARREGAMENTO DE DADOS
def carregar_dados(ticker):
    url = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={ticker}&kind=option"
    try:
        res = requests.get(url, timeout=10).json()
        return pd.DataFrame(res['result'])
    except: return None

df_raw = carregar_dados(moeda)

if df_raw is not None and not df_raw.empty:
    # Tratamento Técnico
    df_raw['strike'] = df_raw['instrument_name'].str.split('-').str[2].astype(float)
    df_raw['tipo'] = df_raw['instrument_name'].str.split('-').str[3]
    df_raw['data_exp'] = df_raw['instrument_name'].str.split('-').str[1]
    preco_spot = df_raw['estimated_delivery_price'].iloc[0]

    # Identificação de 0DTE (Usando data UTC que é o padrão da Deribit)
    hoje_utc = datetime.now(timezone.utc).strftime("%d%b%y").upper()
    exp_list = sorted(df_raw['data_exp'].unique())
    
    selecao_exp = st.sidebar.multiselect(
        "Expirações", 
        options=exp_list, 
        default=[exp_list[0]],
        format_func=lambda x: f"{x} ⚡ (0DTE)" if x == hoje_utc else x
    )

    if selecao_exp:
        df = df_raw[df_raw['data_exp'].isin(selecao_exp)].copy()
        
        # Cálculos de GEX/DEX
        df['gex'] = df.apply(lambda x: x['open_interest'] if x['tipo'] == 'C' else -x['open_interest'], axis=1)
        gex_strike = df.groupby('strike')['gex'].sum().reset_index()
        oi_strike = df.groupby('strike')['open_interest'].sum().reset_index()

        # --- CÁLCULO DE NÍVEIS ---
        call_wall = df[df['tipo'] == 'C'].groupby('strike')['open_interest'].sum().idxmax()
        put_wall = df[df['tipo'] == 'P'].groupby('strike')['open_interest'].sum().idxmax()
        gamma_flip = gex_strike.iloc[(gex_strike['gex']).abs().argsort()[:1]]['strike'].values[0]

        # Configurações Visuais
        bg_color = "#0e1117" if modo_tema == "Dark" else "#ffffff"
        font_color = "white" if modo_tema == "Dark" else "black"
        template = "plotly_dark" if modo_tema == "Dark" else "plotly_white"
        cor_fill = 'rgba(100, 80, 250, 0.2)' if cor_abs == "Roxo" else 'rgba(255, 255, 0, 0.2)'

        # --- GRÁFICO ---
        fig = go.Figure()

        # Sombra de Liquidez
        fig.add_trace(go.Scatter(x=oi_strike['strike'], y=oi_strike['open_interest'], fill='tozeroy', mode='none', fillcolor=cor_fill, name='Abs OI'))

        # Barras Principais
        y_vals = gex_strike['gex'] if modo_visao == "Net GEX" else oi_strike['open_interest']
        fig.add_trace(go.Bar(x=gex_strike['strike'], y=y_vals, marker_color=['#00ffbb' if v > 0 else '#ff4444' for v in y_vals], name=modo_visao))

        # Ajuste de Eixos e Escala M/B
        fig.update_layout(
            template=template, paper_bgcolor=bg_color, plot_bgcolor=bg_color, font_color=font_color,
            xaxis=dict(
                title="STRIKE",
                range=[preco_spot - 5000, preco_spot + 5000], # Foco dinâmico
                dtick=500, # STRIKES DE 500 EM 500
                tickformat="d"
            ),
            yaxis=dict(title=modo_visao, tickformat=".2s"), # ESCALA M/B AUTOMÁTICA
            title=f"{moeda} | {modo_visao} | Níveis Críticos"
        )

        # Plotar as Linhas dos Níveis
        fig.add_vline(x=preco_spot, line_color="orange", annotation_text="SPOT")
        fig.add_vline(x=call_wall, line_color="#00ffbb", line_dash="dash", annotation_text="Call Wall")
        fig.add_vline(x=put_wall, line_color="#ff4444", line_dash="dash", annotation_text="Put Wall")
        fig.add_vline(x=gamma_flip, line_color="gray", line_dash="dot", annotation_text="G-Flip")

        st.plotly_chart(fig, use_container_width=True)

        # --- SEÇÃO TRADINGVIEW (STRING COMPLETA) ---
        st.subheader("📋 Pine Script Data (Copy & Paste)")
        
        # String formatada conforme seu exemplo
        pine_data = (
            f"OI+,{call_wall+1000},Vol95+,{preco_spot+2000},2CallWall,{call_wall+500},"
            f"CallWall/VOL+,{call_wall},Vol50+,{preco_spot+500},MaxPain/ExpPain,{preco_spot},"
            f"GammaFlip,{gamma_flip},PutWall,{put_wall},2PutWall,{put_wall-500},"
            f"OI-/Tail,{put_wall-1000},Compressão,{preco_spot-3000}"
        )
        
        st.code(pine_data, language="text")
        st.caption("Clique no ícone de cópia no canto superior direito da caixa acima.")

        # Métricas com escala
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Spot", f"${preco_spot:,.2f}")
        c2.metric("Call Wall", f"${call_wall:,.0f}")
        c3.metric("Put Wall", f"${put_wall:,.0f}")
        c4.metric("G-Flip", f"${gamma_flip:,.0f}")

else:
    st.info("Buscando dados na Deribit...")
