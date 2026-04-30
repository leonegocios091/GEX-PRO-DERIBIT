import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh # Precisaremos instalar esta!

# 1. CONFIGURAÇÃO E AUTO-REFRESH
st.set_page_config(page_title="GEX Dashboard Pro", layout="wide")

# Atualiza o app automaticamente a cada 30 segundos
st_autorefresh(interval=30000, key="datarefresh")

st.title("📊 GEX & DEX Master Engine")

# 2. FUNÇÃO PARA BUSCAR DADOS
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
st.sidebar.header("Painel de Controle")
moeda_escolhida = st.sidebar.selectbox("Ativo", ["BTC", "ETH"])

# 4. PROCESSAMENTO DOS DADOS
df_raw = carregar_dados(moeda_escolhida)

if df_raw is not None and not df_raw.empty:
    # Extração de Strike, Tipo e DATA de Expiração
    # Ex nome: BTC-30APR26-65000-C
    df_raw['data_exp'] = df_raw['instrument_name'].str.split('-').str[1]
    df_raw['strike'] = df_raw['instrument_name'].str.split('-').str[2].astype(float)
    df_raw['tipo'] = df_raw['instrument_name'].str.split('-').str[3]
    
    # Seletor de Expirações na Sidebar
    expiracoes_disponiveis = sorted(df_raw['data_exp'].unique())
    data_selecionada = st.sidebar.multiselect(
        "Filtrar Expirações", 
        options=expiracoes_disponiveis,
        default=expiracoes_disponiveis[0] # Começa com a mais próxima
    )
    
    # Filtrar o DataFrame com base na seleção
    df = df_raw[df_raw['data_exp'].isin(data_selecionada)].copy()
    
    # Cálculo de GEX
    df['gex_val'] = df.apply(lambda x: x['open_interest'] if x['tipo'] == 'C' else -x['open_interest'], axis=1)
    gex_por_strike = df.groupby('strike')['gex_val'].sum().reset_index()
    abs_gex = df.groupby('strike')['open_interest'].sum().reset_index()
    preco_spot = df_raw['estimated_delivery_price'].iloc[0]

    # --- GRÁFICO ---
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=abs_gex['strike'], y=abs_gex['open_interest'],
        fill='tozeroy', mode='none', fillcolor='rgba(100, 80, 250, 0.2)', name='Liquidez Total'
    ))

    fig.add_trace(go.Bar(
        x=gex_por_strike['strike'], y=gex_por_strike['gex_val'],
        marker_color=['#00ffbb' if val > 0 else '#ff4444' for val in gex_por_strike['gex_val']],
        name='Net GEX'
    ))

    fig.add_vline(x=preco_spot, line_width=2, line_color="#FFA500")
    
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#111727", plot_bgcolor="#111727",
        height=600,
        xaxis=dict(title="STRIKE", range=[preco_spot * 0.8, preco_spot * 1.2]),
        title=f"Expirações Selecionadas: {', '.join(data_selecionada)}"
    )

    st.plotly_chart(fig, use_container_width=True)
    
    # Métricas com tempo de atualização
    c1, c2, c3 = st.columns(3)
    c1.metric("Preço Spot", f"${preco_spot:,.2f}")
    c2.metric("OI Filtrado", f"{df['open_interest'].sum():,.0f}")
    c3.info("Atualização: Cada 30s")

else:
    st.warning("Carregando dados da Deribit...")
