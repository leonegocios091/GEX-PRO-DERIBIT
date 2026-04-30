import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go

st.set_page_config(page_title="GEX Dashboard", layout="wide")
st.title("📊 Visualizador de Gamma Exposure (GEX)")

def carregar_dados(moeda):
    url = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={moeda}&kind=option"
    response = requests.get(url)
    if response.status_code == 200:
        return pd.DataFrame(response.json()['result'])
    return None

moeda_escolhida = st.sidebar.selectbox("Escolha a Moeda", ["BTC", "ETH"])
df = carregar_dados(moeda_escolhida)

if df is not None:
    # --- TRATAMENTO DOS DADOS ---
    # 1. Extrair o Strike Price do nome (Ex: BTC-2MAY26-67000-C -> 67000)
    df['strike'] = df['instrument_name'].str.split('-').str[2].astype(float)
    
    # 2. Identificar se é Call (C) ou Put (P)
    df['tipo'] = df['instrument_name'].str.split('-').str[3]
    
    # 3. Cálculo Simples de Exposição (GEX)
    # Em modelos reais usamos o Gamma grego, aqui usaremos o OI para o visual inicial
    df['gex'] = df.apply(lambda x: x['open_interest'] if x['tipo'] == 'C' else -x['open_interest'], axis=1)

    # Agrupar por Strike para somar o GEX de diferentes datas
    gex_por_strike = df.groupby('strike')['gex'].sum().reset_index()

    # --- CRIAÇÃO DO GRÁFICO (Estilo Quant Trading App) ---
    fig = go.Figure()

    # Adicionando as barras
    fig.add_trace(go.Bar(
        x=gex_por_strike['strike'],
        y=gex_por_strike['gex'],
        marker_color=['#00ffbb' if val > 0 else '#ff4444' for val in gex_por_strike['gex']],
        name="Net GEX"
    ))

    # Estilizando para parecer profissional (Fundo escuro)
    fig.update_layout(
        template="plotly_dark",
        title=f"Distribuição de GEX por Strike - {moeda_escolhida}",
        xaxis_title="Strike Price",
        yaxis_title="Gamma Exposure (Proxy)",
        bargap=0.1
    )

    # Exibir o gráfico no Streamlit
    st.plotly_chart(fig, use_container_width=True)
    
    st.success("Gráfico gerado com sucesso!")
else:
    st.error("Erro ao carregar dados.")
