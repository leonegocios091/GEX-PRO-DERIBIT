import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Deribit OI Dashboard", layout="wide")

def buscar_dados_deribit(moeda):
    # Preço Spot atual
    url_preco = f"https://www.deribit.com/api/v2/public/get_index_price?index_name={moeda.lower()}_usd"
    preco_spot = requests.get(url_preco).json()['result']['index_price']
    
    # Resumo do mercado (Opções)
    url_summary = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={moeda}&kind=option"
    dados = requests.get(url_summary).json()['result']
    
    df = pd.DataFrame(dados)
    # Extração de Strike e Tipo (Call/Put)
    df['strike'] = df['instrument_name'].str.split('-').str[2].astype(float)
    df['tipo'] = df['instrument_name'].str.split('-').str[3]
    df['open_interest'] = pd.to_numeric(df['open_interest'], errors='coerce').fillna(0)
    
    return df, preco_spot

# --- INTERFACE ---
st.title("📊 Open Interest By Strike Price")

moeda = st.sidebar.selectbox("Selecione a Moeda", ["BTC", "ETH", "SOL"])
raio = st.sidebar.slider("Raio de Strikes (%)", 5, 30, 15)

if st.sidebar.button("Atualizar Dashboard"):
    try:
        df_opcoes, preco_spot = buscar_dados_deribit(moeda)
        
        # Filtro de strikes ao redor do preço para não poluir o gráfico
        margem = preco_spot * (raio / 100)
        df_filt = df_opcoes[(df_opcoes['strike'] > preco_spot - margem) & 
                           (df_opcoes['strike'] < preco_spot + margem)].copy()

        # Separar Calls e Puts
        calls = df_filt[df_filt['tipo'] == 'C'].groupby('strike')['open_interest'].sum().reset_index()
        puts = df_filt[df_filt['tipo'] == 'P'].groupby('strike')['open_interest'].sum().reset_index()

        # Criar o Gráfico de Barras Verticais (lado a lado)
        fig = go.Figure()

        # Adicionar Barras de Calls (Azul conforme exemplo)
        fig.add_trace(go.Bar(
            x=calls['strike'],
            y=calls['open_interest'],
            name='Calls',
            marker_color='#2E64FE' # Azul
        ))

        # Adicionar Barras de Puts (Amarelo conforme exemplo)
        fig.add_trace(go.Bar(
            x=puts['strike'],
            y=puts['open_interest'],
            name='Puts',
            marker_color='#F4D03F' # Amarelo
        ))

        # Linha vertical do preço atual (Max Pain/Spot aproximado)
        fig.add_vline(x=preco_spot, line_dash="dash", line_color="red", 
                      annotation_text=f"Spot: ${preco_spot:,.0f}", 
                      annotation_position="top")

        # Ajustes de Layout para ficar idêntico ao exemplo
        fig.update_layout(
            template="plotly_dark",
            barmode='group', # Coloca as barras lado a lado
            height=600,
            xaxis=dict(title="Strike Price", tickformat=".0f", gridcolor='gray'),
            yaxis=dict(title="Open Interest", gridcolor='gray'),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            bargap=0.15,
            bargroupgap=0.1
        )

        st.plotly_chart(fig, use_container_width=True)

        # --- MÉTRICAS INFERIORES (Igual ao rodapé da sua imagem) ---
        total_calls = calls['open_interest'].sum()
        total_puts = puts['open_interest'].sum()
        p_c_ratio = total_puts / total_calls if total_calls > 0 else 0

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Call Open Interest", f"{total_calls:,.1f}")
        col2.metric("Put Open Interest", f"{total_puts:,.1f}")
        col3.metric("Total Open Interest", f"{(total_calls + total_puts):,.1f}")
        col4.metric("Put/Call Ratio", f"{p_c_ratio:.2f}")

    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")
else:
    st.info("Clique em 'Atualizar Dashboard' para visualizar os contratos abertos.")
