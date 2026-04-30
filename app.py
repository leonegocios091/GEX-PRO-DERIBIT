import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Deribit GEX/DEX Dashboard", layout="wide")

def buscar_dados_deribit(moeda):
    # Preço Spot atual
    url_preco = f"https://www.deribit.com/api/v2/public/get_index_price?index_name={moeda.lower()}_usd"
    resposta_preco = requests.get(url_preco).json()
    preco_spot = resposta_preco['result']['index_price']
    
    # Resumo do mercado (Opções)
    url_summary = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={moeda}&kind=option"
    resposta_summary = requests.get(url_summary).json()
    dados = resposta_summary['result']
    
    df = pd.DataFrame(dados)
    
    # Extração de Strike e Tipo
    df['strike'] = df['instrument_name'].str.split('-').str[2].astype(float)
    df['tipo'] = df['instrument_name'].str.split('-').str[3]
    
    # CORREÇÃO DO ERRO: Garantindo que as colunas sejam tratadas como Series do Pandas antes do fillna
    for col in ['gamma', 'delta', 'open_interest']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        else:
            df[col] = 0.0
    
    return df, preco_spot

# --- INTERFACE ---
st.title("📊 GEX & DEX Exposure By Strike")

moeda = st.sidebar.selectbox("Selecione a Moeda", ["BTC", "ETH", "SOL"])
tipo_exposicao = st.sidebar.radio("Escolha a Métrica", ["GEX (Gamma)", "DEX (Delta)"])
raio = st.sidebar.slider("Raio de Strikes (%)", 5, 30, 15)

if st.sidebar.button("Atualizar Dashboard"):
    try:
        df_opcoes, preco_spot = buscar_dados_deribit(moeda)
        
        # Filtro de strikes ao redor do preço
        margem = preco_spot * (raio / 100)
        df_filt = df_opcoes[(df_opcoes['strike'] > preco_spot - margem) & 
                           (df_opcoes['strike'] < preco_spot + margem)].copy()

        if df_filt.empty:
            st.warning("Nenhum dado encontrado para o raio selecionado.")
        else:
            # CÁLCULO GEX E DEX
            if tipo_exposicao == "GEX (Gamma)":
                # Escala ajustada para visibilidade
                df_filt['valor_calc'] = (df_filt['gamma'] * df_filt['open_interest'] * (preco_spot**2)) / 100
                label_y = "Gamma Exposure (GEX)"
            else:
                df_filt['valor_calc'] = (df_filt['delta'] * df_filt['open_interest'] * preco_spot)
                label_y = "Delta Exposure (DEX)"

            # Separar por Calls e Puts para o visual de barras lado a lado[cite: 1]
            calls = df_filt[df_filt['tipo'] == 'C'].groupby('strike')['valor_calc'].sum().reset_index()
            puts = df_filt[df_filt['tipo'] == 'P'].groupby('strike')['valor_calc'].sum().reset_index()

            # --- CONSTRUÇÃO DO GRÁFICO (Visual Estilo Deribit) ---[cite: 1]
            fig = go.Figure()

            fig.add_trace(go.Bar(
                x=calls['strike'],
                y=calls['valor_calc'],
                name='Calls',
                marker_color='#2E64FE' # Azul[cite: 1]
            ))

            fig.add_trace(go.Bar(
                x=puts['strike'],
                y=puts['valor_calc'],
                name='Puts',
                marker_color='#F4D03F' # Amarelo[cite: 1]
            ))

            fig.add_vline(x=preco_spot, line_dash="dash", line_color="red", 
                          annotation_text=f"SPOT: ${preco_spot:,.0f}")

            fig.update_layout(
                template="plotly_dark",
                barmode='group', 
                height=600,
                xaxis=dict(title="Strike Price", gridcolor='#333'),
                yaxis=dict(title=label_y, gridcolor='#333'),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
                bargap=0.15
            )

            st.plotly_chart(fig, use_container_width=True)

            # --- MÉTRICAS ---
            total_calc = df_filt['valor_calc'].sum()
            col1, col2 = st.columns(2)
            col1.metric(f"Total {tipo_exposicao}", f"{total_calc:,.2f}")
            col2.metric("Preço Spot", f"${preco_spot:,.2f}")

    except Exception as e:
        st.error(f"Erro no processamento: {e}")
else:
    st.info("Clique no botão para carregar os dados.")
