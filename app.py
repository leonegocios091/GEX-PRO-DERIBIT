import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Deribit GEX Monitor", layout="wide")

def buscar_dados_deribit(moeda):
    # Preço Spot atual
    url_preco = f"https://www.deribit.com/api/v2/public/get_index_price?index_name={moeda.lower()}_usd"
    preco_spot = requests.get(url_preco).json()['result']['index_price']
    
    # Resumo do mercado
    url_summary = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={moeda}&kind=option"
    dados = requests.get(url_summary).json()['result']
    
    df = pd.DataFrame(dados)
    # Extração de Strike e Tipo (Call/Put)
    df['strike'] = df['instrument_name'].str.split('-').str[2].astype(float)
    df['tipo'] = df['instrument_name'].str.split('-').str[3]
    
    return df, preco_spot

# --- UI ---
st.title("⚡ Deribit Real-Time GEX Dashboard")
moeda = st.sidebar.selectbox("Moeda", ["BTC", "ETH", "SOL"])
raio = st.sidebar.slider("Raio de Strikes (%)", 5, 50, 25)

if st.sidebar.button("Atualizar Dashboard"):
    try:
        df_opcoes, preco_spot = buscar_dados_deribit(moeda)
        
        # Filtro de strikes ao redor do preço
        margem = preco_spot * (raio / 100)
        df_filt = df_opcoes[(df_opcoes['strike'] > preco_spot - margem) & 
                           (df_opcoes['strike'] < preco_spot + margem)].copy()

        # --- PROTEÇÃO CONTRA ERRO 'GAMMA' ---
        # Se a coluna não existir na resposta da API, nós a criamos com zero
        if 'gamma' not in df_filt.columns:
            df_filt['gamma'] = 0
        
        # Garante que Gamma e OI sejam números, tratando erros como zero
        df_filt['gamma'] = pd.to_numeric(df_filt['gamma'], errors='coerce').fillna(0)
        df_filt['open_interest'] = pd.to_numeric(df_filt['open_interest'], errors='coerce').fillna(0)

        # Cálculo do GEX com Escala Aumentada (Preço ao Quadrado) para as barras aparecerem
        def calcular_gex_final(row):
            g = float(row['gamma'])
            oi = float(row['open_interest'])
            # Escala ajustada para visibilidade das barras
            exposicao = (g * oi * (preco_spot ** 2)) / 1000
            return exposicao if row['tipo'] == 'C' else -exposicao

        df_filt['gex_val'] = df_filt.apply(calcular_gex_final, axis=1)

        # Agrupar por strike
        gex_plot = df_filt.groupby('strike')['gex_val'].sum().reset_index()
        # Remove valores nulos para limpar o gráfico
        gex_plot = gex_plot[gex_plot['gex_val'] != 0] 
        gex_plot['cor'] = ['#00FF00' if x > 0 else '#FF0000' for x in gex_plot['gex_val']]

        # --- PLOTAGEM ---
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=gex_plot['gex_val'],
            y=gex_plot['strike'],
            orientation='h',
            marker_color=gex_plot['cor'],
            name='Net GEX'
        ))

        # Linha do Preço Spot
        fig.add_hline(y=preco_spot, line_dash="dash", line_color="yellow", 
                      annotation_text=f"SPOT: {preco_spot:,.2f}")

        fig.update_layout(
            template="plotly_dark",
            height=800,
            title=f"Perfil de Gamma Líquido - {moeda}",
            xaxis_title="Pressão Gamma (Escala Ajustada)",
            yaxis=dict(title="Strike Price", type='linear', autorange=True),
            bargap=0.2
        )

        st.plotly_chart(fig, use_container_width=True)
        st.success(f"Dados processados! Preço {moeda}: ${preco_spot:,.2f}")

    except Exception as e:
        st.error(f"Erro ao processar dados: {e}")
else:
    st.info("Clique no botão lateral para carregar os dados.")
