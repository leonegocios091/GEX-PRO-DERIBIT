import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Deribit Live GEX", layout="wide")

def buscar_dados_api(moeda):
    try:
        # 1. Preço Spot
        url_index = f"https://www.deribit.com/api/v2/public/get_index_price?index_name={moeda.lower()}_usd"
        res_index = requests.get(url_index, timeout=10).json()
        spot = float(res_index['result']['index_price'])
        
        # 2. Market Summary
        url_summary = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={moeda}&kind=option"
        res_summary = requests.get(url_summary, timeout=10).json()
        dados = res_summary.get('result', [])
        
        df = pd.DataFrame(dados)
        if df.empty: return df, spot

        # 3. Limpeza de Dados
        df['strike'] = df['instrument_name'].str.split('-').str[-2].astype(float)
        df['tipo'] = df['instrument_name'].str.split('-').str[-1]
        
        for col in ['open_interest', 'gamma', 'delta']:
            df[col] = pd.to_numeric(df.get(col, 0), errors='coerce').fillna(0.0)
        
        # 4. Cálculos
        df['GEX'] = df['gamma'] * df['open_interest'] * (spot**2)
        df['DEX'] = df['delta'] * df['open_interest'] * spot
        df['OI'] = df['open_interest']
        
        return df, spot
    except Exception as e:
        st.error(f"Erro na API: {e}")
        return pd.DataFrame(), 0.0

# --- UI ---
st.title("⚡ Deribit Real-Time Options Dashboard")
moeda = st.sidebar.selectbox("Ativo", ["BTC", "ETH", "SOL"])
metrica = st.sidebar.radio("Métrica", ["GEX", "DEX", "OI"])
raio_pct = st.sidebar.slider("Raio de Strikes (%)", 5, 50, 20)

if st.sidebar.button("Atualizar Agora") or 'df_live' not in st.session_state:
    df, spot = buscar_dados_api(moeda)
    st.session_state.df_live = df
    st.session_state.spot_live = spot

if 'df_live' in st.session_state and not st.session_state.df_live.empty:
    df_raw = st.session_state.df_live
    spot = st.session_state.spot_live

    # Filtro de Strikes
    margem = spot * (raio_pct / 100)
    df_filt = df_raw[(df_raw['strike'] > spot - margem) & (df_raw['strike'] < spot + margem)].copy()

    if df_filt[metrica].sum() == 0:
        st.warning(f"⚠️ A métrica {metrica} está zerada para estes strikes. Tente mudar para 'OI' ou aumentar o Raio.")
    
    # Agrupamento
    pivot = df_filt.groupby(['strike', 'tipo'])[metrica].sum().unstack().fillna(0)
    for t in ['C', 'P']: 
        if t not in pivot.columns: pivot[t] = 0
    pivot = pivot.reset_index()

    # --- GRÁFICO ---
    fig = go.Figure()
    fig.add_trace(go.Bar(x=pivot['strike'], y=pivot['C'], name='Calls', marker_color='#2E64FE'))
    fig.add_trace(go.Bar(x=pivot['strike'], y=pivot['P'], name='Puts', marker_color='#F4D03F'))

    fig.add_vline(x=spot, line_dash="dash", line_color="red", annotation_text=f"SPOT: {spot:,.0f}")

    fig.update_layout(
        template="plotly_dark", barmode='group',
        xaxis=dict(title="Strike", type='category'), # 'category' garante que todas as barras apareçam
        yaxis=dict(title=metrica), height=600
    )

    st.plotly_chart(fig, use_container_width=True)
    st.info(f"Última atualização: {moeda} @ ${spot:,.2f}")
else:
    st.info("Clique em 'Atualizar Agora' para carregar dados reais.")
