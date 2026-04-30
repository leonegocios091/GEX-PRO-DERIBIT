import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="GEX Dashboard Pro", layout="wide")

# Estilização para remover margens brancas e deixar o fundo bem escuro
st.markdown("""
    <style>
    .main { background-color: #111727; }
    header {visibility: hidden;}
    </style>
    """, unsafe_allow_index=True)

st.title("📊 GEX & DEX Master Engine")

# 2. FUNÇÃO PARA BUSCAR DADOS DA DERIBIT
def carregar_dados(moeda):
    # Chamada para obter o resumo de todas as opções da moeda escolhida
    url = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={moeda}&kind=option"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return pd.DataFrame(response.json()['result'])
    except Exception as e:
        st.error(f"Erro de conexão: {e}")
    return None

# 3. INTERFACE LATERAL
st.sidebar.header("Configurações")
moeda_escolhida = st.sidebar.selectbox("Escolha o Ativo", ["BTC", "ETH"])

# 4. PROCESSAMENTO E GRÁFICO
df = carregar_dados(moeda_escolhida)

if df is not None and not df.empty:
    # Tratamento dos dados para extrair Strike e Tipo (Call/Put)
    # Exemplo de nome: BTC-27MAR26-65000-C
    df['strike'] = df['instrument_name'].str.split('-').str[2].astype(float)
    df['tipo'] = df['instrument_name'].str.split('-').str[3]
    
    # Cálculo simplificado de GEX (Proxy usando Open Interest)
    # Calls = Positivo, Puts = Negativo
    df['gex_val'] = df.apply(lambda x: x['open_interest'] if x['tipo'] == 'C' else -x['open_interest'], axis=1)

    # Agrupando por Strike
    gex_por_strike = df.groupby('strike')['gex_val'].sum().reset_index()
    abs_gex = df.groupby('strike')['open_interest'].sum().reset_index()
    
    # Preço Spot (Atual)
    preco_spot = df['estimated_delivery_price'].iloc[0]

    # --- CONSTRUÇÃO DO GRÁFICO ---
    fig = go.Figure()

    # Adicionando a Área Roxa (Abs GEX) - Sombra ao fundo
    fig.add_trace(go.Scatter(
        x=abs_gex['strike'],
        y=abs_gex['open_interest'],
        fill='tozeroy',
        mode='none',
        fillcolor='rgba(100, 80, 250, 0.15)',
        name='Abs GEX (OI)'
    ))

    # Adicionando as Barras de Net GEX
    fig.add_trace(go.Bar(
        x=gex_por_strike['strike'],
        y=gex_por_strike['gex_val'],
        marker_color=['#00ffbb' if val > 0 else '#ff4444' for val in gex_por_strike['gex_val']],
        name='Net GEX'
    ))

    # Adicionando a Linha do Preço Spot (Laranja)
    fig.add_vline(x=preco_spot, line_width=2, line_dash="solid", line_color="#FFA500")
    
    # Ajustes finais de layout (Cores e Eixos)
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#111727",
        plot_bgcolor="#111727",
        height=600,
        margin=dict(l=20, r=20, t=50, b=20),
        title=dict(
            text=f"{moeda_escolhida} | Net GEX & Liquidez por Strike",
            font=dict(size=20, color="white")
        ),
        xaxis=dict(
            title="STRIKE PRICE",
            gridcolor="#232936",
            range=[preco_spot * 0.7, preco_spot * 1.3] # Foca nos strikes próximos ao preço
        ),
        yaxis=dict(title="EXPOSIÇÃO / OPEN INTEREST", gridcolor="#232936"),
        showlegend=True
    )

    # Mostrar o gráfico
    st.plotly_chart(fig, use_container_width=True)
    
    # Métricas rápidas no topo
    col1, col2 = st.columns(2)
    col1.metric("Preço Spot", f"${preco_spot:,.2f}")
    col2.metric("Total Open Interest", f"{df['open_interest'].sum():,.0f}")

else:
    st.info("Aguardando dados da API da Deribit...")
