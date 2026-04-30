import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go

# Configuração da página do Streamlit
st.set_page_config(page_title="GEX Dashboard", layout="wide")

st.title("📊 Visualizador de Gamma Exposure (GEX)")

# 1. Função para buscar dados da Deribit
def carregar_dados(moeda):
    url = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={moeda}&kind=option"
    response = requests.get(url)
    if response.status_code == 200:
        dados = response.json()['result']
        return pd.DataFrame(dados)
    return None

# 2. Interface na barra lateral
moeda_escolhida = st.sidebar.selectbox("Escolha a Moeda", ["BTC", "ETH"])

# 3. Execução
df = carregar_dados(moeda_escolhida)

if df is not None:
    st.success(f"Dados de {moeda_escolhida} carregados com sucesso!")
    
    # Exibe uma amostra dos dados brutos para você ver o que veio da API
    st.write("Amostra dos dados da Option Chain:")
    st.dataframe(df[['instrument_name', 'open_interest', 'ask_price', 'bid_price']].head())
else:
    st.error("Erro ao conectar com a Deribit.")
