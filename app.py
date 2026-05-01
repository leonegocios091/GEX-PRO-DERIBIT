import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from datetime import datetime

# 1. CONFIGURAÇÃO E AUTO-REFRESH
st.set_page_config(page_title="GEX Master Pro", layout="wide")
st_autorefresh(interval=10000, key="datarefresh")

# 2. FUNÇÃO DE FORMATAÇÃO DE ESCALA
def formatar_escala(valor):
    if abs(valor) >= 1_000_000_000:
        return f"{valor / 1_000_000_000:.2f}B"
    elif abs(valor) >= 1_000_000:
        return f"{valor / 1_000_000:.2f}M"
    return f"{valor:,.0f}"

# 3. INTERFACE LATERAL (CONTROLES)
st.sidebar.header("🕹️ Painel de Controle")
moeda = st.sidebar.selectbox("Ativo", ["BTC", "ETH"])
modo_tema = st.sidebar.radio("Tema do Gráfico", ["Dark", "Light"])
modo_visao = st.sidebar.radio("Métrica Principal", ["Net GEX", "Open Interest (OI)", "DEX"])
cor_abs = st.sidebar.selectbox("Cor do GEX Absoluto", ["Roxo", "Amarelo"])

# 4. CARREGAMENTO E TRATAMENTO
def carregar_dados(ticker):
    url = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={ticker}&kind=option"
    try:
        res = requests.get(url, timeout=10).json()
        return pd.DataFrame(res['result'])
    except: return None

df_raw = carregar_dados(moeda)

if df_raw is not None:
    # Extrair data de expiração e converter para identificar 0DTE
    df_raw['data_exp'] = df_raw['instrument_name'].str.split('-').str[1]
    df_raw['strike'] = df_raw['instrument_name'].str.split('-').str[2].astype(float)
    df_raw['tipo'] = df_raw['instrument_name'].str.split('-').str[3]
    preco_spot = df_raw['estimated_delivery_price'].iloc[0]

    # Filtro de Expirações com destaque para 0DTE
    exp_list = sorted(df_raw['data_exp'].unique())
    hoje_str = datetime.now().strftime("%d%b%y").upper() # Ex: 30APR26
    
    # Criar etiquetas amigáveis para o seletor
    labels_exp = {e: f"{e} (0DTE ⚡)" if e == hoje_str else e for e in exp_list}
    selecao_exp = st.sidebar.multiselect(
        "Selecione as Expirações", 
        options=exp_list, 
        default=[exp_list[0]], 
        format_func=lambda x: labels_exp[x]
    )

    if selecao_exp:
        df = df_raw[df_raw['data_exp'].isin(selecao_exp)].copy()
        
        # Cálculos de GEX
        df['gex'] = df.apply(lambda x: x['open_interest'] if x['tipo'] == 'C' else -x['open_interest'], axis=1)
        gex_strike = df.groupby('strike')['gex'].sum().reset_index()
        oi_strike = df.groupby('strike')['open_interest'].sum().reset_index()

        # Definição de Cores conforme Tema
        bg_color = "#0e1117" if modo_tema == "Dark" else "#ffffff"
        font_color = "white" if modo_tema == "Dark" else "black"
        grid_color = "#232936" if modo_tema == "Dark" else "#e5e5e5"
        template = "plotly_dark" if modo_tema == "Dark" else "plotly_white"
        cor_preenchimento = 'rgba(100, 80, 250, 0.2)' if cor_abs == "Roxo" else 'rgba(255, 255, 0, 0.2)'

        # --- GRÁFICO ---
        fig = go.Figure()

        # Sombra Absoluta
        fig.add_trace(go.Scatter(
            x=oi_strike['strike'], y=oi_strike['open_interest'],
            fill='tozeroy', mode='none', fillcolor=cor_preenchimento, name='Gex Abs'
        ))

        # Barras Net
        y_vals = gex_strike['gex'] if modo_visao == "Net GEX" else oi_strike['open_interest']
        fig.add_trace(go.Bar(
            x=gex_strike['strike'], y=y_vals,
            marker_color=['#00ffbb' if v > 0 else '#ff4444' for v in y_vals],
            name=modo_visao
        ))

        fig.update_layout(
            template=template, paper_bgcolor=bg_color, plot_bgcolor=bg_color,
            font_color=font_color, height=600,
            xaxis=dict(range=[preco_spot * 0.92, preco_spot * 1.08], title="STRIKE", gridcolor=grid_color),
            yaxis=dict(title=modo_visao, gridcolor=grid_color),
            title=f"Dashboard {moeda} - {', '.join(selecao_exp)}"
        )
        
        fig.add_vline(x=preco_spot, line_width=2, line_color="#FFA500", annotation_text="SPOT")

        st.plotly_chart(fig, use_container_width=True)

        # --- ÁREA DE EXPORTAÇÃO ---
        st.divider()
        st.subheader("📋 Níveis para TradingView")
        
        # Lógica para Gamma Flip e Walls (simplificada)
        call_wall = df[df['tipo'] == 'C'].groupby('strike')['open_interest'].sum().idxmax()
        put_wall = df[df['tipo'] == 'P'].groupby('strike')['open_interest'].sum().idxmax()
        
        dados_tv = f"OI+,{call_wall+2000},CallWall,{call_wall},Spot,{preco_spot:.0f},PutWall,{put_wall},OI-,{put_wall-2000}"
        
        st.code(dados_tv, language="text")
        st.caption("Selecione o texto acima e use CTRL+C / CTRL+V.")

        # Métricas
        c1, c2, c3 = st.columns(3)
        c1.metric("Preço Spot", f"${preco_spot:,.2f}")
        c2.metric("OI Filtrado", formatar_escala(df['open_interest'].sum()))
        c3.metric("GEX Líquido", formatar_escala(gex_strike['gex'].sum()))

else:
    st.info("Conectando à Deribit...")
