import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Deribit GEX/DEX Monitor", layout="wide")

def buscar_dados_deribit(moeda):
    # Preço Spot atual
    url_preco = f"https://www.deribit.com/api/v2/public/get_index_price?index_name={moeda.lower()}_usd"
    resposta_preco = requests.get(url_preco).json()
    preco_spot = resposta_preco['result']['index_price']
    
    # Resumo do mercado
    url_summary = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={moeda}&kind=option"
    resposta_summary = requests.get(url_summary).json()
    dados = resposta_summary['result']
    
    df = pd.DataFrame(dados)
    df['strike'] = df['instrument_name'].str.split('-').str[2].astype(float)
    df['tipo'] = df['instrument_name'].str.split('-').str[3]
    
    # Garantindo que as colunas sejam numéricas
    for col in ['gamma', 'delta', 'open_interest']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        else:
            df[col] = 0.0
    
    return df, preco_spot

# --- INTERFACE ---
st.title("📊 GEX & DEX Vertical Exposure")

moeda = st.sidebar.selectbox("Selecione a Moeda", ["BTC", "ETH", "SOL"])
tipo_exposicao = st.sidebar.radio("Métrica", ["GEX (Gamma)", "DEX (Delta)"])
raio = st.sidebar.slider("Raio de Strikes (%)", 5, 50, 20)

if st.sidebar.button("Atualizar Dashboard"):
    try:
        df_opcoes, preco_spot = buscar_dados_deribit(moeda)
        
        # Filtro de strikes
        margem = preco_spot * (raio / 100)
        df_filt = df_opcoes[(df_opcoes['strike'] > preco_spot - margem) & 
                           (df_opcoes['strike'] < preco_spot + margem)].copy()

        if df_filt.empty:
            st.warning("Aumente o Raio de Strikes para encontrar dados.")
        else:
            # --- CÁLCULO COM MULTIPLICADOR DE VISIBILIDADE ---
            if tipo_exposicao == "GEX (Gamma)":
                # Multiplicamos por um fator grande para as barras aparecerem no gráfico
                df_filt['valor_calc'] = (df_filt['gamma'] * df_filt['open_interest'] * (preco_spot**2))
                label_y = "Gamma Exposure (Ajustada)"
            else:
                # Delta já costuma ser maior, mas ajustamos para escala
                df_filt['valor_calc'] = (df_filt['delta'] * df_filt['open_interest'] * preco_spot)
                label_y = "Delta Exposure (Ajustada)"

            # Agrupar por strike e separar tipo[cite: 1]
            calls = df_filt[df_filt['tipo'] == 'C'].groupby('strike')['valor_calc'].sum().reset_index()
            puts = df_filt[df_filt['tipo'] == 'P'].groupby('strike')['valor_calc'].sum().reset_index()
            
            # Removemos valores ínfimos que "esmagam" o gráfico
            calls = calls[calls['valor_calc'].abs() > 0.0001]
            puts = puts[puts['valor_calc'].abs() > 0.0001]

            # --- CONSTRUÇÃO DO GRÁFICO (Visual Deribit) ---[cite: 1]
            fig = go.Figure()

            # Barras Calls (Azul)
            fig.add_trace(go.Bar(
                x=calls['strike'],
                y=calls['valor_calc'],
                name='Calls',
                marker_color='#2E64FE'
            ))

            # Barras Puts (Amarelo)
            fig.add_trace(go.Bar(
                x=puts['strike'],
                y=puts['valor_calc'],
                name='Puts',
                marker_color='#F4D03F'
            ))

            # Linha Spot
            fig.add_vline(x=preco_spot, line_dash="dash", line_color="red", 
                          annotation_text=f"SPOT: {preco_spot:,.0f}")

            fig.update_layout(
                template="plotly_dark",
                barmode='group', 
                height=600,
                xaxis=dict(title="Strike Price", type='category'), # 'category' faz os strikes ficarem espaçados como na foto[cite: 1]
                yaxis=dict(title=label_y),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)
            )

            st.plotly_chart(fig, use_container_width=True)
            st.success(f"Dashboard Atualizado! Preço {moeda}: ${preco_spot:,.2f}")

    except Exception as e:
        st.error(f"Erro: {e}")
