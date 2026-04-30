import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Deribit GEX/DEX Dashboard", layout="wide")

def buscar_dados_deribit(moeda):
    # Preço Spot atual
    url_preco = f"https://www.deribit.com/api/v2/public/get_index_price?index_name={moeda.lower()}_usd"
    preco_spot = requests.get(url_preco).json()['result']['index_price']
    
    # Resumo do mercado (Opções)
    url_summary = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={moeda}&kind=option"
    dados = requests.get(url_summary).json()['result']
    
    df = pd.DataFrame(dados)
    # Extração de Strike e Tipo
    df['strike'] = df['instrument_name'].str.split('-').str[2].astype(float)
    df['tipo'] = df['instrument_name'].str.split('-').str[3]
    
    # Blindagem de colunas críticas
    for col in ['gamma', 'delta', 'open_interest']:
        df[col] = pd.to_numeric(df.get(col, 0), errors='coerce').fillna(0)
    
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

        # CÁLCULO GEX E DEX (Normalizado para escala financeira)
        if tipo_exposicao == "GEX (Gamma)":
            # GEX = Gamma * OI * (Spot^2) / 100
            df_filt['valor_calc'] = (df_filt['gamma'] * df_filt['open_interest'] * (preco_spot**2)) / 100
            label_y = "Gamma Exposure (GEX)"
        else:
            # DEX = Delta * OI * Spot
            df_filt['valor_calc'] = (df_filt['delta'] * df_filt['open_interest'] * preco_spot)
            label_y = "Delta Exposure (DEX)"

        # Separar por Calls e Puts para o visual de barras lado a lado
        calls = df_filt[df_filt['tipo'] == 'C'].groupby('strike')['valor_calc'].sum().reset_index()
        puts = df_filt[df_filt['tipo'] == 'P'].groupby('strike')['valor_calc'].sum().reset_index()

        # --- CONSTRUÇÃO DO GRÁFICO (Visual Deribit) ---[cite: 1]
        fig = go.Figure()

        # Barras de Calls (Azul)[cite: 1]
        fig.add_trace(go.Bar(
            x=calls['strike'],
            y=calls['valor_calc'],
            name='Calls',
            marker_color='#2E64FE'
        ))

        # Barras de Puts (Amarelo)[cite: 1]
        fig.add_trace(go.Bar(
            x=puts['strike'],
            y=puts['valor_calc'],
            name='Puts',
            marker_color='#F4D03F'
        ))

        # Linha do Preço Spot[cite: 1]
        fig.add_vline(x=preco_spot, line_dash="dash", line_color="red", 
                      annotation_text=f"SPOT: ${preco_spot:,.0f}")

        fig.update_layout(
            template="plotly_dark",
            barmode='group', # Barras verticais lado a lado[cite: 1]
            height=600,
            xaxis=dict(title="Strike Price", gridcolor='#333'),
            yaxis=dict(title=label_y, gridcolor='#333'),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            bargap=0.15
        )

        st.plotly_chart(fig, use_container_width=True)

        # --- MÉTRICAS GLOBAIS NO RODAPÉ ---[cite: 1]
        total_gex = df_filt['valor_calc'].sum()
        max_strike = df_filt.loc[df_filt['valor_calc'].idxmax(), 'strike'] if not df_filt.empty else 0

        col1, col2, col3 = st.columns(3)
        col1.metric(f"Total {tipo_exposicao}", f"{total_gex:,.2f}")
        col2.metric("Preço de Índice", f"${preco_spot:,.2f}")
        col3.metric("Strike de Maior Exposição", f"${max_strike:,.0f}")

    except Exception as e:
        st.error(f"Erro no processamento: {e}")
else:
    st.info("Aguardando atualização de dados...")
