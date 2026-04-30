import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="GEX Dashboard Pro", layout="wide")

# Atualização automática a cada 30 segundos
st_autorefresh(interval=30000, key="datarefresh")

st.title("📊 GEX & DEX Master Engine")

# 2. FUNÇÃO DE DADOS
def carregar_dados(moeda):
    url = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={moeda}&kind=option"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return pd.DataFrame(response.json()['result'])
    except Exception as e:
        st.error(f"Erro de conexão: {e}")
    return None

# 3. INTERFACE LATERAL
st.sidebar.header("Configurações")
moeda_escolhida = st.sidebar.selectbox("Ativo", ["BTC", "ETH"])

# 4. PROCESSAMENTO
df_raw = carregar_dados(moeda_escolhida)

if df_raw is not None and not df_raw.empty:
    # Organizar datas e strikes
    df_raw['data_exp'] = df_raw['instrument_name'].str.split('-').str[1]
    df_raw['strike'] = df_raw['instrument_name'].str.split('-').str[2].astype(float)
    df_raw['tipo'] = df_raw['instrument_name'].str.split('-').str[3]
    
    # Filtro de Expirações
    expiracoes = sorted(df_raw['data_exp'].unique())
    selecao_exp = st.sidebar.multiselect("Filtrar Expirações", expiracoes, default=expiracoes[0])
    
    if not selecao_exp:
        st.warning("Selecione ao menos uma data de expiração na barra lateral.")
    else:
        df = df_raw[df_raw['data_exp'].isin(selecao_exp)].copy()
        
        # Cálculo de GEX
        df['gex_val'] = df.apply(lambda x: x['open_interest'] if x['tipo'] == 'C' else -x['open_interest'], axis=1)
        gex_por_strike = df.groupby('strike')['gex_val'].sum().reset_index()
        abs_gex = df.groupby('strike')['open_interest'].sum().reset_index()
        preco_spot = df_raw['estimated_delivery_price'].iloc[0]

        # --- GRÁFICO ---
        fig = go.Figure()
        
        # Sombra de Liquidez (Abs GEX)
        fig.add_trace(go.Scatter(
            x=abs_gex['strike'], y=abs_gex['open_interest'],
            fill='tozeroy', mode='none', fillcolor='rgba(100, 80, 250, 0.2)', name='Liquidez Total'
        ))

        # Barras de Net GEX
        fig.add_trace(go.Bar(
            x=gex_por_strike['strike'], y=gex_por_strike['gex_val'],
            marker_color=['#00ffbb' if val > 0 else '#ff4444' for val in gex_por_strike['gex_val']],
            name='Net GEX'
        ))

        # Linha do Preço Spot
        fig.add_vline(x=preco_spot, line_width=2, line_color="#FFA500")
        
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="#111727", plot_bgcolor="#111727",
            height=600,
            xaxis=dict(title="STRIKE", range=[preco_spot * 0.8, preco_spot * 1.2]),
            title=f"Dashboard {moeda_escolhida} - Expirações: {', '.join(selecao_exp)}"
        )

        st.plotly_chart(fig, use_container_width=True)
        
        # Métricas em destaque
        c1, c2, c3 = st.columns(3)
        c1.metric("Preço Spot", f"${preco_spot:,.2f}")
        c2.metric("Contratos Filtrados", f"{df['open_interest'].sum():,.0f}")
        c3.info("Atualizando a cada 30s...")
else:
    st.info("Conectando à Deribit...")
