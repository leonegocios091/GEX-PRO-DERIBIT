import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Deribit GEX Monitor", layout="wide")

# --- FUNÇÃO DE BUSCA DE DADOS ---
def buscar_dados_deribit(moeda):
    url_preco = f"https://www.deribit.com/api/v2/public/get_index_price?index_name={moeda.lower()}_usd"
    resposta_preco = requests.get(url_preco).json()
    preco_spot = resposta_preco['result']['index_price']
    
    url_summary = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={moeda}&kind=option"
    resposta_summary = requests.get(url_summary).json()
    dados = resposta_summary['result']
    
    df = pd.DataFrame(dados)
    df['strike'] = df['instrument_name'].str.split('-').str[2].astype(float)
    df['tipo'] = df['instrument_name'].str.split('-').str[3]
    
    return df, preco_spot

# --- INTERFACE DO USUÁRIO ---
st.title("⚡ Deribit Real-Time GEX Dashboard")

moeda_selecionada = st.sidebar.selectbox("Selecione a Moeda", ["BTC", "ETH", "SOL"])
margem_percentual = st.sidebar.slider("Raio de visualização (%)", 5, 30, 15)

if st.sidebar.button("Atualizar Dashboard"):
    try:
        with st.spinner('Conectando à Deribit...'):
            df_opcoes, preco_spot = buscar_dados_deribit(moeda_selecionada)
        
        # Filtro de Strikes
        margem = preco_spot * (margem_percentual / 100)
        df_filt = df_opcoes[(df_opcoes['strike'] > preco_spot - margem) & 
                           (df_opcoes['strike'] < preco_spot + margem)].copy()

        # --- CORREÇÃO AQUI: 'in' em vez de 'em' ---
        for col in ['gamma', 'open_interest']:
            if col not in df_filt.columns:
                df_filt[col] = 0
            else:
                df_filt[col] = pd.to_numeric(df_filt[col], errors='coerce').fillna(0)

        # Cálculo do GEX
        def calcular_gex(row):
            gamma = float(row.get('gamma', 0))
            oi = float(row.get('open_interest', 0))
            valor_gex = gamma * oi * preco_spot
            return valor_gex if row['tipo'] == 'C' else -valor_gex

        df_filt['gex_calculado'] = df_filt.apply(calcular_gex, axis=1)

        # Agrupamento e Cores
        gex_final = df_filt.groupby('strike')['gex_calculado'].sum().reset_index()
        gex_final['cor'] = ['#00FF00' if x > 0 else '#FF0000' for x in gex_final['gex_calculado']]

        # Gráfico
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=gex_final['gex_calculado'],
            y=gex_final['strike'],
            orientation='h',
            marker_color=gex_final['cor']
        ))

        fig.add_hline(y=preco_spot, line_dash="dash", line_color="yellow", 
                      annotation_text=f"SPOT: {preco_spot:.2f}")

        fig.update_layout(template="plotly_dark", height=700, 
                          title=f"Net GEX Profile - {moeda_selecionada}")
        
        st.plotly_chart(fig, use_container_width=True)
        
    except Exception as e:
        st.error(f"Erro ao processar dados: {e}")
else:
    st.info("Clique no botão lateral para carregar.")
