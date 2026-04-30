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

        # Limpeza de dados: garante que Gamma e OI sejam números
        df_filt['gamma'] = pd.to_numeric(df_filt['gamma'], errors='coerce').fillna(0)
        df_filt['open_interest'] = pd.to_numeric(df_filt['open_interest'], errors='coerce').fillna(0)

        # --- AJUSTE DE CÁLCULO (A chave para plotar as barras) ---
        # Calculamos a exposição financeira real: Gamma * OI * (Spot^2)
        # Dividimos por 1.000.000 para facilitar a leitura (escala em Milhões)
        def calcular_gex_final(row):
            g = float(row['gamma'])
            oi = float(row['open_interest'])
            # Multiplicador financeiro para BTC/ETH
            exposicao = (g * oi * (preco_spot ** 2)) / 1000000
            return exposicao if row['tipo'] == 'C' else -exposicao

        df_filt['gex_val'] = df_filt.apply(calcular_gex_final, axis=1)

        # Agrupar por strike para consolidar o gráfico
        gex_plot = df_filt.groupby('strike')['gex_val'].sum().reset_index()
        gex_plot = gex_plot[gex_plot['gex_val'] != 0] # Remove strikes sem volume
        gex_plot['cor'] = ['#00FF00' if x > 0 else '#FF0000' for x in gex_plot['gex_val']]

        # --- PLOTAGEM ---
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=gex_plot['gex_val'],
            y=gex_plot['strike'],
            orientation='h',
            marker_color=gex_plot['cor'],
            name='Net GEX (Milhões $)'
        ))

        # Linha do Preço Spot
        fig.add_hline(y=preco_spot, line_dash="dash", line_color="yellow", 
                      annotation_text=f"SPOT: {preco_spot:,.2f}")

        fig.update_layout(
            template="plotly_dark",
            height=800,
            title=f"Perfil de Gamma Líquido - {moeda} (Escala em Milhões)",
            xaxis_title="GEX Financeiro (Notional)",
            yaxis=dict(title="Strike Price", type='linear', autorange=True),
            bargap=0.2
        )

        st.plotly_chart(fig, use_container_width=True)
        st.write(f"Preço atual de {moeda}: **${preco_spot:,.2f}**")

    except Exception as e:
        st.error(f"Erro: {e}")
else:
    st.info("Clique no botão 'Atualizar' para gerar o gráfico.")
