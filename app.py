import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Deribit Automated GEX", layout="wide")

def buscar_dados_api(moeda):
    try:
        # 1. Busca Preço de Índice (Spot)
        url_index = f"https://www.deribit.com/api/v2/public/get_index_price?index_name={moeda.lower()}_usd"
        res_index = requests.get(url_index).json()
        spot = float(res_index['result']['index_price'])
        
        # 2. Busca Resumo de todas as opções
        url_summary = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={moeda}&kind=option"
        res_summary = requests.get(url_summary).json()
        dados = res_summary.get('result', [])
        
        # Criamos o DataFrame garantindo que ele exista
        df = pd.DataFrame(dados)
        
        if df.empty:
            return df, spot

        # 3. Tratamento de Dados (Correção do Erro AttributeError)
        # Extrai Strike e Tipo
        df['strike'] = df['instrument_name'].str.split('-').str[-2].astype(float)
        df['tipo'] = df['instrument_name'].str.split('-').str[-1]
        
        # COLUNAS CRÍTICAS: Garantimos que sejam Series e tratamos nulos
        for col in ['open_interest', 'gamma', 'delta']:
            if col not in df.columns:
                df[col] = 0.0
            # Convertemos a coluna inteira de uma vez, evitando o erro de 'int object'
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
        
        # 4. Cálculos de Exposição
        df['GEX'] = df['gamma'] * df['open_interest'] * (spot**2)
        df['DEX'] = df['delta'] * df['open_interest'] * spot
        df['OI'] = df['open_interest']
        
        return df, spot
    except Exception as e:
        st.error(f"Erro na conexão com a API: {e}")
        return pd.DataFrame(), 0.0

# --- INTERFACE ---
st.title("⚡ Deribit Automated GEX Dashboard")

moeda = st.sidebar.selectbox("Ativo", ["BTC", "ETH", "SOL"])
metrica = st.sidebar.radio("Métrica", ["OI", "GEX", "DEX"])
raio_pct = st.sidebar.slider("Raio de Strikes (%)", 5, 50, 15)

# Lógica de atualização
if st.sidebar.button("Atualizar via API") or 'df_live' not in st.session_state:
    df, spot = buscar_dados_api(moeda)
    st.session_state.df_live = df
    st.session_state.spot_live = spot

if 'df_live' in st.session_state and not st.session_state.df_live.empty:
    df_filt = st.session_state.df_live
    spot = st.session_state.spot_live

    # Filtro de Strikes próximo ao Spot
    margem = spot * (raio_pct / 100)
    df_plot = df_filt[(df_filt['strike'] > spot - margem) & (df_filt['strike'] < spot + margem)].copy()
    
    # Agrupamento para visual (Barras lado a lado)
    pivot = df_plot.groupby(['strike', 'tipo'])[metrica].sum().unstack().fillna(0)
    
    # Garante que as colunas de Call e Put existam para o gráfico não quebrar
    if 'C' not in pivot.columns: pivot['C'] = 0
    if 'P' not in pivot.columns: pivot['P'] = 0
    pivot = pivot.reset_index()

    # --- GRÁFICO ---
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=pivot['strike'], y=pivot['C'], 
        name='Calls', marker_color='#2E64FE'
    ))
    
    fig.add_trace(go.Bar(
        x=pivot['strike'], y=pivot['P'], 
        name='Puts', marker_color='#F4D03F'
    ))

    fig.add_vline(x=spot, line_dash="dash", line_color="red", 
                  annotation_text=f"SPOT: {spot:,.0f}", annotation_position="top")

    fig.update_layout(
        template="plotly_dark",
        barmode='group',
        title=f"Distribuição Real-Time de {metrica} - {moeda}",
        xaxis=dict(title="Strike Price", type='category'),
        yaxis=dict(title=metrica),
        height=600
    )

    st.plotly_chart(fig, use_container_width=True)
    st.info(f"Dados atualizados via API. Preço Spot: ${spot:,.2f}")
else:
    st.warning("Aguardando dados da API ou ativo sem opções disponíveis.")
