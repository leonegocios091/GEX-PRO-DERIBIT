import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="GEX Dashboard Pro", layout="wide")

# Estilização para deixar o fundo escuro (Corrigido para unsafe_allow_html)
st.markdown("""
    <style>
    .main { background-color: #111727; }
    </style>
    """, unsafe_allow_html=True)

st.title("📊 GEX & DEX Master Engine")

# 2. FUNÇÃO PARA BUSCAR DADOS DA DERIBIT
def carregar_dados(moeda):
    url = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={moeda}&kind=option"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            res_json = response.json()
            if 'result' in res_json:
                return pd.DataFrame(res_json['result'])
    except Exception as e:
        st.error(f"Erro de conexão: {e}")
    return None

# 3. INTERFACE LATERAL
st.sidebar.header("Configurações")
moeda_escolhida = st.sidebar.selectbox("Escolha o Ativo", ["BTC", "ETH"])

# 4. PROCESSAMENTO E GRÁFICO
df = carregar_dados(moeda_escolhida)

if df is not None and not df.empty:
    # Tratamento dos dados
    df['strike'] = df['instrument_name'].str.split('-').str[2].astype(float)
    df['tipo'] = df['instrument_name'].str.split('-').str[3]
    
    # Cálculo simplificado de GEX (Calls Positivas, Puts Negativas)
    df['gex_val'] = df.apply(lambda x: x['open_interest'] if x['tipo'] == 'C' else -x['open_interest'], axis=1)

    # Agrupando por Strike
    gex_por_strike = df.groupby('strike')['gex_val'].sum().reset_index()
    abs_gex = df.groupby('strike')['open_interest'].sum().reset_index()
    
    # Preço Spot (Atual)
    preco_spot = df['estimated_delivery_price'].iloc[0]

    # --- CONSTRUÇÃO DO GRÁFICO ---
    fig = go.Figure()

    # Sombra de Liquidez (Abs GEX)
    fig.add_trace(go.Scatter(
        x=abs_gex['strike'],
        y=abs_gex['open_interest'],
        fill='tozeroy',
        mode='none',
        fillcolor='rgba(100, 80, 250, 0.2)',
        name='Liquidez Total (OI)'
    ))

    # Barras de Net GEX
    fig.add_trace(go.Bar(
        x=gex_por_strike['strike'],
        y=gex_por_strike['gex_val'],
        marker_color=['#00ffbb' if val > 0 else '#ff4444' for val in gex_por_strike['gex_val']],
        name='Net GEX (C-P)'
    ))

    # Linha do Preço Spot
    fig.add_vline(x=preco_spot, line_width=2, line_dash="solid", line_color="#FFA500")
    
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#111727",
        plot_bgcolor="#111727",
        height=600,
        title=f"{moeda_escolhida} | Distribuição de Gamma e Liquidez",
        xaxis=dict(
            title="STRIKE PRICE",
            gridcolor="#232936",
            range=[preco_spot * 0.8, preco_spot * 1.2] # Zoom de 20% em torno do preço
        ),
        yaxis=dict(title="Volume de Contratos", gridcolor="#232936"),
    )

    st.plotly_chart(fig, use_container_width=True)
    
    # Métricas no rodapé
    c1, c2 = st.columns(2)
    c1.metric("Preço Atual", f"${preco_spot:,.2f}")
    c2.metric("Contratos Abertos (Total)", f"{df['open_interest'].sum():,.0f}")

else:
    st.warning("Não foi possível carregar os dados. Verifique sua conexão ou tente novamente em instantes.")
