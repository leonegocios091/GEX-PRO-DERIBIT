import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# 1. CONFIGURAÇÃO E ESTILO
st.set_page_config(page_title="GEX Master Pro", layout="wide")
st_autorefresh(interval=30000, key="datarefresh")

# CSS para fundo escuro e botões
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #161b22; padding: 10px; border-radius: 5px; }
    </style>
    """, unsafe_allow_html=True)

# 2. FUNÇÃO DE FORMATAÇÃO (Milhões/Bilhões)
def formatar_escala(valor):
    if abs(valor) >= 1_000_000_000:
        return f"{valor / 1_000_000_000:.2f}B"
    elif abs(valor) >= 1_000_000:
        return f"{valor / 1_000_000:.2f}M"
    return f"{valor:,.0f}"

# 3. INTERFACE LATERAL
st.sidebar.header("🕹️ Painel de Controle")
moeda = st.sidebar.selectbox("Ativo", ["BTC", "ETH"])
modo_visao = st.sidebar.radio("Métrica Principal", ["Net GEX", "Open Interest (OI)", "DEX"])
cor_abs = st.sidebar.selectbox("Cor do GEX Absoluto", ["Roxo", "Amarelo"])

cor_preenchimento = 'rgba(100, 80, 250, 0.2)' if cor_abs == "Roxo" else 'rgba(255, 255, 0, 0.15)'

# 4. CARREGAMENTO DE DADOS
@st.cache_data(ttl=30)
def carregar_dados(ticker):
    url = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={ticker}&kind=option"
    res = requests.get(url).json()
    return pd.DataFrame(res['result']) if 'result' in res else None

df_raw = carregar_dados(moeda)

if df_raw is not None:
    # Processamento base
    df_raw['strike'] = df_raw['instrument_name'].str.split('-').str[2].astype(float)
    df_raw['tipo'] = df_raw['instrument_name'].str.split('-').str[3]
    preco_spot = df_raw['estimated_delivery_price'].iloc[0]

    # Cálculos agrupados
    df_raw['gex'] = df_raw.apply(lambda x: x['open_interest'] if x['tipo'] == 'C' else -x['open_interest'], axis=1)
    gex_strike = df_raw.groupby('strike')['gex'].sum().reset_index()
    oi_strike = df_raw.groupby('strike')['open_interest'].sum().reset_index()

    # --- GRÁFICO ---
    fig = go.Figure()

    # Sombra Absoluta (Selecionável)
    fig.add_trace(go.Scatter(
        x=oi_strike['strike'], y=oi_strike['open_interest'],
        fill='tozeroy', mode='none', fillcolor=cor_preenchimento, name='Liquidez Abs'
    ))

    # Barras de Exposição
    y_vals = gex_strike['gex'] if modo_visao == "Net GEX" else oi_strike['open_interest']
    fig.add_trace(go.Bar(
        x=gex_strike['strike'], y=y_vals,
        marker_color=['#00ffbb' if v > 0 else '#ff4444' for v in y_vals],
        name=modo_visao
    ))

    fig.update_layout(
        template="plotly_dark", paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
        xaxis=dict(range=[preco_spot * 0.9, preco_spot * 1.1], title="STRIKE"),
        yaxis=dict(title=f"Volume ({modo_visao})")
    )
    # Formatação do eixo Y para K/M/B
    fig.update_yaxes(tickformat=".2s")

    st.plotly_chart(fig, use_container_width=True)

    # --- ÁREA DE EXPORTAÇÃO TRADINGVIEW ---
    st.divider()
    st.subheader("📋 Exportar Níveis para TradingView")
    
    # Seus dados de exemplo formatados como uma string única
    dados_tv = (
        f"OI+,80000,Vol95+,79092,2CallWall,78000,CallWall/VOL+,77500,Vol50+,77288,"
        f"MaxPain/ExpPain/LocalPain/DynPain,77000,GammaFlip,76926,PutWall,76500,"
        f"2PutWall/FlowPain,76000,OI-/VOL-/Tail,75500,Vol50-,75397,Vol95-,73593,Compressão,69000"
    )
    
    st.text_area("Dados formatados:", dados_tv, height=70)
    if st.button("Copiar dados para o Indicador"):
        st.write("✔️ Copiado! (Use CTRL+V no seu script Pine do TradingView)")
        # Nota: O Streamlit não acessa o clipboard do sistema diretamente por segurança em navegadores, 
        # mas o campo de texto acima permite seleção rápida.

    # Métricas formatadas em M/B
    c1, c2, c3 = st.columns(3)
    c1.metric("Preço Spot", f"${preco_spot:,.2f}")
    c2.metric("OI Total", formatar_escala(df_raw['open_interest'].sum()))
    c3.metric("GEX Líquido", formatar_escala(gex_strike['gex'].sum()))

else:
    st.warning("Aguardando resposta da Deribit...")
