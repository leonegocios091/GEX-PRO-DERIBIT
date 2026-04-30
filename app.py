import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Deribit Real-Time GEX", layout="wide")

def buscar_dados_api(moeda):
    # 1. Busca Preço de Índice (Spot)
    url_index = f"https://www.deribit.com/api/v2/public/get_index_price?index_name={moeda.lower()}_usd"
    res_index = requests.get(url_index).json()
    spot = float(res_index['result']['index_price'])
    
    # 2. Busca Resumo de todas as opções do ativo
    url_summary = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={moeda}&kind=option"
    res_summary = requests.get(url_summary).json()
    dados = res_summary.get('result', [])
    
    df = pd.DataFrame(dados)
    
    if df.empty:
        return df, spot

    # 3. Tratamento de Dados
    # Extrai Strike e Tipo do nome do instrumento (Ex: BTC-26JUN26-80000-C)
    df['strike'] = df['instrument_name'].str.split('-').str[-2].astype(float)
    df['tipo'] = df['instrument_name'].str.split('-').str[-1]
    
    # Converte colunas críticas para numérico
    for col in ['open_interest', 'gamma', 'delta']:
        df[col] = pd.to_numeric(df.get(col, 0), errors='coerce').fillna(0.0)
    
    # 4. Cálculos de Exposição Notional[cite: 1]
    df['GEX'] = df['gamma'] * df['open_interest'] * (spot**2)
    df['DEX'] = df['delta'] * df['open_interest'] * spot
    df['OI'] = df['open_interest']
    
    return df, spot

# --- INTERFACE ---
st.title("⚡ Deribit Automated GEX Dashboard")

moeda = st.sidebar.selectbox("Ativo", ["BTC", "ETH", "SOL"])
metrica = st.sidebar.radio("Métrica", ["OI", "GEX", "DEX"])
raio_pct = st.sidebar.slider("Raio de Strikes (%)", 5, 50, 15)

# Automação de atualização[cite: 1]
if st.sidebar.button("Atualizar via API") or 'df_live' not in st.session_state:
    with st.spinner("Conectando à Deribit..."):
        df, spot = buscar_dados_api(moeda)
        st.session_state.df_live = df
        st.session_state.spot_live = spot

df_filt = st.session_state.df_live
spot = st.session_state.spot_live

if not df_filt.empty:
    # Filtro de Strikes próximo ao Spot[cite: 1]
    margem = spot * (raio_pct / 100)
    df_plot = df_filt[(df_filt['strike'] > spot - margem) & (df_filt['strike'] < spot + margem)].copy()
    
    # Agrupamento para visual side-by-side[cite: 1]
    # Usamos o formato da sua imagem de referência (Barras verticais lado a lado)
    pivot = df_plot.groupby(['strike', 'tipo'])[metrica].sum().unstack().fillna(0)
    if 'C' not in pivot.columns: pivot['C'] = 0
    if 'P' not in pivot.columns: pivot['P'] = 0
    pivot = pivot.reset_index()

    # --- GRÁFICO ---
    fig = go.Figure()
    
    # Calls (Azul)[cite: 1]
    fig.add_trace(go.Bar(
        x=pivot['strike'], y=pivot['C'], 
        name='Calls', marker_color='#2E64FE'
    ))
    
    # Puts (Amarelo)[cite: 1]
    fig.add_trace(go.Bar(
        x=pivot['strike'], y=pivot['P'], 
        name='Puts', marker_color='#F4D03F'
    ))

    fig.add_vline(x=spot, line_dash="dash", line_color="red", annotation_text=f"SPOT: {spot:,.0f}")

    fig.update_layout(
        template="plotly_dark",
        barmode='group',
        title=f"Distribuição Real-Time de {metrica} - {moeda}",
        xaxis=dict(title="Strike Price", type='category'), # 'category' mantém o visual limpo como na sua imagem[cite: 1]
        yaxis=dict(title=metrica),
        height=600
    )

    st.plotly_chart(fig, use_container_width=True)
    st.success(f"Dados atualizados diretamente da exchange. Preço atual: ${spot:,.2f}")
else:
    st.error("Erro ao carregar dados da API.")
