import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Deribit GEX Monitor", layout="wide")

# --- FUNÇÕES DE BUSCA DE DADOS ---
def buscar_dados_deribit(moeda):
    # 1. Busca o preço atual do índice (Spot)
    url_preco = f"https://www.deribit.com/api/v2/public/get_index_price?index_name={moeda.lower()}_usd"
    resposta_preco = requests.get(url_preco).json()
    preco_spot = resposta_preco['result']['index_price']
    
    # 2. Busca o resumo de todos os contratos de opções
    url_summary = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={moeda}&kind=option"
    resposta_summary = requests.get(url_summary).json()
    dados = resposta_summary['result']
    
    # Converte para Tabela (DataFrame)
    df = pd.DataFrame(dados)
    
    # Extrai Strike e Tipo (Call/Put) do nome do instrumento
    # Exemplo: BTC-26DEC25-50000-C -> Strike: 50000, Tipo: C
    df['strike'] = df['instrument_name'].str.split('-').str[2].astype(float)
    df['tipo'] = df['instrument_name'].str.split('-').str[3]
    
    return df, preco_spot

# --- INTERFACE DO USUÁRIO ---
st.title("⚡ Deribit Real-Time GEX Dashboard")
st.markdown("Monitor de Exposição Gamma e Liquidez de Opções")

# Menu Lateral
moeda_selecionada = st.sidebar.selectbox("Selecione a Moeda", ["BTC", "ETH", "SOL"])
margem_percentual = st.sidebar.slider("Raio de visualização (% do preço)", 5, 30, 15)

if st.sidebar.button("Atualizar Dashboard"):
    try:
        # Busca os dados
        with st.spinner('Conectando à API da Deribit...'):
            df_opcoes, preco_spot = buscar_dados_deribit(moeda_selecionada)
        
        # --- TRATAMENTO E FILTRAGEM ---
        # Filtra os strikes ao redor do preço atual
        margem = preco_spot * (margem_percentual / 100)
        df_filt = df_opcoes[(df_opcoes['strike'] > preco_spot - margem) & 
                           (df_opcoes['strike'] < preco_spot + margem)].copy()

        # BLINDAGEM CONTRA ERROS: Converte colunas para números e preenche vazios com 0
        df_filt['gamma'] = pd.to_numeric(df_filt['gamma'], errors='coerce').fillna(0)
        df_filt['open_interest'] = pd.to_numeric(df_filt['open_interest'], errors='coerce').fillna(0)

        # Cálculo do GEX (Gamma Exposure)
        # Se for Call (C): Gamma * OI * Preço
        # Se for Put (P): -Gamma * OI * Preço
        def calcular_gex(row):
            valor_gex = row['gamma'] * row['open_interest'] * preco_spot
            return valor_gex if row['tipo'] == 'C' else -valor_gex

        df_filt['gex_calculado'] = df_filt.apply(calcular_gex, axis=1)

        # Agrupa por Strike para consolidar Calls e Puts no mesmo nível
        gex_final = df_filt.groupby('strike')['gex_calculado'].sum().reset_index()
        gex_final['cor'] = ['#00FF00' if x > 0 else '#FF0000' for x in gex_final['gex_calculado']]

        # --- CONSTRUÇÃO DO GRÁFICO ---
        fig = go.Figure()

        # Adiciona as barras de GEX
        fig.add_trace(go.Bar(
            x=gex_final['gex_calculado'],
            y=gex_final['strike'],
            orientation='h',
            marker_color=gex_final['cor'],
            name='Net GEX'
        ))

        # Adiciona linha do Preço Spot Atual
        fig.add_hline(
            y=preco_spot, 
            line_dash="dash", 
            line_color="yellow", 
            annotation_text=f"PREÇO ATUAL: {preco_spot:.2f}",
            annotation_position="top right"
        )

        # Estilização do Gráfico
        fig.update_layout(
            title=f"Perfil de Exposição Gamma (Net GEX) - {moeda_selecionada}",
            xaxis_title="Exposição Financeira (Pressão de Mercado)",
            yaxis_title="Preço (Strike)",
            template="plotly_dark",
            height=800,
            bargap=0.1
        )

        # Exibe o gráfico no Streamlit
        st.plotly_chart(fig, use_container_width=True)
        
        # Mostra métricas rápidas abaixo do gráfico
        col1, col2 = st.columns(2)
        col1.metric("Preço Index", f"${preco_spot:,.2f}")
        col2.metric("Total de Contratos Analisados", int(df_filt['open_interest'].sum()))

    except Exception as e:
        st.error(f"Erro ao processar dados: {e}")
        st.info("Dica: Tente atualizar novamente em alguns segundos. A API pode estar instável.")

else:
    st.info("Clique no botão 'Atualizar Dashboard' no menu lateral para carregar os dados reais.")
