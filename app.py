import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Deribit GEX/DEX Dashboard", layout="wide")

def buscar_dados_deribit(moeda):
    # 1. Preço Spot
    url_preco = f"https://www.deribit.com/api/v2/public/get_index_price?index_name={moeda.lower()}_usd"
    preco_spot = requests.get(url_preco).json()['result']['index_price']
    
    # 2. Resumo de Opções
    url_summary = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={moeda}&kind=option"
    dados = requests.get(url_summary).json()['result']
    
    df = pd.DataFrame(dados)
    
    # 3. Extração e Limpeza
    df['strike'] = df['instrument_name'].str.split('-').str[2].astype(float)
    df['tipo'] = df['instrument_name'].str.split('-').str[3]
    
    # Garante colunas numéricas mesmo que a API não envie todas
    for col in ['gamma', 'delta', 'open_interest']:
        df[col] = pd.to_numeric(df.get(col, 0), errors='coerce').fillna(0)
    
    return df, preco_spot

# --- INTERFACE ---
st.title("📊 GEX & DEX Vertical Exposure")

moeda = st.sidebar.selectbox("Selecione a Moeda", ["BTC", "ETH", "SOL"])
metrica = st.sidebar.radio("Métrica para Cor/Direção", ["GEX (Gamma)", "DEX (Delta)"])
raio = st.sidebar.slider("Raio de Strikes (%)", 5, 50, 20)

if st.sidebar.button("Atualizar Dashboard"):
    try:
        df_opcoes, preco_spot = buscar_dados_deribit(moeda)
        
        # Filtro de strikes ao redor do preço
        margem = preco_spot * (raio / 100)
        df_filt = df_opcoes[(df_opcoes['strike'] > preco_spot - margem) & 
                           (df_opcoes['strike'] < preco_spot + margem)].copy()

        if df_filt.empty:
            st.warning("Sem dados no raio selecionado. Tente aumentar o Raio de Strikes.")
        else:
            # Cálculo de Exposição - Usamos o OI como peso principal para garantir que as barras apareçam
            if metrica == "GEX (Gamma)":
                # Multiplicamos o Gamma pelo OI para ter a exposição por strike
                df_filt['exposicao'] = df_filt['gamma'] * df_filt['open_interest'] * (preco_spot**2)
            else:
                # Multiplicamos o Delta pelo OI
                df_filt['exposicao'] = df_filt['delta'] * df_filt['open_interest'] * preco_spot

            # Agrupar por Strike
            calls = df_filt[df_filt['tipo'] == 'C'].groupby('strike')['exposicao'].sum().reset_index()
            puts = df_filt[df_filt['tipo'] == 'P'].groupby('strike')['exposicao'].sum().reset_index()

            # --- GRÁFICO (Visual Idêntico ao da Deribit) ---
            fig = go.Figure()

            # Adiciona Calls (Azul)
            fig.add_trace(go.Bar(
                x=calls['strike'],
                y=calls['exposicao'],
                name='Calls (Exposição Positiva)',
                marker_color='#2E64FE' # Azul da imagem
            ))

            # Adiciona Puts (Amarelo) - Invertemos o sinal para o visual de "muro"
            fig.add_trace(go.Bar(
                x=puts['strike'],
                y=puts['exposicao'],
                name='Puts (Exposição Negativa)',
                marker_color='#F4D03F' # Amarelo da imagem
            ))

            # Linha de Preço Atual
            fig.add_vline(x=preco_spot, line_dash="dash", line_color="red", 
                          annotation_text=f"SPOT: {preco_spot:,.0f}")

            fig.update_layout(
                template="plotly_dark",
                barmode='group',
                height=600,
                xaxis=dict(title="Strike Price", type='category', tickangle=45),
                yaxis=dict(title=f"Notional {metrica}"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
                bargap=0.1,
                bargroupgap=0.1
            )

            st.plotly_chart(fig, use_container_width=True)
            
            # Tabela de dados para conferência rápida
            with st.expander("Ver Dados Brutos"):
                st.dataframe(df_filt[['instrument_name', 'strike', 'tipo', 'open_interest', 'gamma', 'exposicao']])

    except Exception as e:
        st.error(f"Erro ao processar: {e}")
else:
    st.info("Aguardando comando. Clique em Atualizar.")
