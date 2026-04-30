import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Deribit GEX Monitor", layout="wide")

# --- FUNÇÃO DE BUSCA DE DADOS ---
def buscar_dados_deribit(moeda):
    # Preço Spot
    url_preco = f"https://www.deribit.com/api/v2/public/get_index_price?index_name={moeda.lower()}_usd"
    resposta_preco = requests.get(url_preco).json()
    preco_spot = resposta_preco['result']['index_price']
    
    # Resumo do Mercado (Summary)
    url_summary = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={moeda}&kind=option"
    resposta_summary = requests.get(url_summary).json()
    dados = resposta_summary['result']
    
    df = pd.DataFrame(dados)
    # Extração de Strike e Tipo
    df['strike'] = df['instrument_name'].str.split('-').str[2].astype(float)
    df['tipo'] = df['instrument_name'].str.split('-').str[3]
    
    return df, preco_spot

# --- INTERFACE ---
st.title("⚡ Deribit Real-Time GEX Dashboard")

moeda_selecionada = st.sidebar.selectbox("Selecione a Moeda", ["BTC", "ETH", "SOL"])
# Aumentei o padrão para 20% para garantir que pegue strikes com liquidez
margem_percentual = st.sidebar.slider("Raio de visualização (%)", 5, 50, 20)

if st.sidebar.button("Atualizar Dashboard"):
    try:
        with st.spinner('Coletando dados da Deribit...'):
            df_opcoes, preco_spot = buscar_dados_deribit(moeda_selecionada)
        
        # Filtro de strikes ao redor do preço
        margem = preco_spot * (margem_percentual / 100)
        df_filt = df_opcoes[(df_opcoes['strike'] > preco_spot - margem) & 
                           (df_opcoes['strike'] < preco_spot + margem)].copy()

        # Blindagem de colunas
        for col in ['gamma', 'open_interest']:
            if col not in df_filt.columns:
                df_filt[col] = 0
            else:
                df_filt[col] = pd.to_numeric(df_filt[col], errors='coerce').fillna(0)

        # CÁLCULO COM AJUSTE DE ESCALA (Multiplicador para tornar as barras visíveis)
        def calcular_gex_visivel(row):
            gamma = float(row['gamma'])
            oi = float(row['open_interest'])
            # Multiplicamos pelo preço ao quadrado para converter o gamma nominal em valor financeiro visível
            valor = gamma * oi * (preco_spot ** 2)
            return valor if row['tipo'] == 'C' else -valor

        df_filt['gex_total'] = df_filt.apply(calcular_gex_visivel, axis=1)

        # Agrupamento por Strike
        gex_final = df_filt.groupby('strike')['gex_total'].sum().reset_index()
        gex_final['cor'] = ['#00FF00' if x > 0 else '#FF0000' for x in gex_final['gex_total']]

        # --- GRÁFICO ---
        fig = go.Figure()
        
        fig.add_trace(go.Bar(
            x=gex_final['gex_total'],
            y=gex_final['strike'],
            orientation='h',
            marker_color=gex_final['cor'],
            name='Net GEX'
        ))

        # Linha do Preço Atual
        fig.add_hline(y=preco_spot, line_dash="dash", line_color="yellow", 
                      annotation_text=f"SPOT: {preco_spot:.2f}", 
                      annotation_position="top right")

        fig.update_layout(
            template="plotly_dark", 
            height=800, 
            title=f"Net GEX Profile - {moeda_selecionada} (Ajustado)",
            xaxis_title="Exposição Gamma (Escala Financeira)",
            yaxis_title="Strike Price",
            bargap=0.1,
            # Garante que o eixo Y (preços) seja tratado de forma linear e organizada
            yaxis=dict(type='linear')
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Exibe o preço atual em destaque
        st.success(f"Dados atualizados com sucesso para {moeda_selecionada}!")

    except Exception as e:
        st.error(f"Erro ao processar dados: {e}")
else:
    st.info("Utilize o menu lateral para carregar os dados da exchange.")
