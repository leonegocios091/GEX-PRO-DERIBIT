import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Deribit Live GEX", layout="wide")

def limpar_e_converter(df, col):
    """Garante que a coluna exista e seja convertida para float com segurança."""
    if col not in df.columns:
        df[col] = 0.0
    # Converte para numérico e substitui nulos ou erros por 0.0
    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
    return df[col]

def buscar_dados_api(moeda):
    try:
        # 1. Busca Preço de Índice (Spot)
        url_index = f"https://www.deribit.com/api/v2/public/get_index_price?index_name={moeda.lower()}_usd"
        res_index = requests.get(url_index, timeout=10).json()
        spot = float(res_index['result']['index_price'])
        
        # 2. Busca Resumo do Mercado
        url_summary = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={moeda}&kind=option"
        res_summary = requests.get(url_summary, timeout=10).json()
        dados = res_summary.get('result', [])
        
        if not dados:
            return pd.DataFrame(), spot

        df = pd.DataFrame(dados)

        # 3. Tratamento de Estrutura (Strike e Tipo)
        df['strike'] = df['instrument_name'].str.split('-').str[-2].astype(float)
        df['tipo'] = df['instrument_name'].str.split('-').str[-1]
        
        # 4. Blindagem de Colunas (Evita o erro 'gamma', 'delta' ou 'open_interest')
        df['open_interest'] = limpar_e_converter(df, 'open_interest')
        df['gamma'] = limpar_e_converter(df, 'gamma')
        df['delta'] = limpar_e_converter(df, 'delta')
        
        # 5. Cálculos de Exposição
        df['GEX'] = df['gamma'] * df['open_interest'] * (spot**2)
        df['DEX'] = df['delta'] * df['open_interest'] * spot
        df['OI'] = df['open_interest']
        
        return df, spot
    except Exception as e:
        st.error(f"Erro na conexão ou processamento: {e}")
        return pd.DataFrame(), 0.0

# --- INTERFACE ---
st.title("⚡ Deribit Real-Time Options Dashboard")
moeda = st.sidebar.selectbox("Selecione o Ativo", ["BTC", "ETH", "SOL"])
metrica = st.sidebar.radio("Métrica Visual", ["OI", "GEX", "DEX"])
raio_pct = st.sidebar.slider("Raio de Strikes (%)", 5, 50, 20)

# Gatilho de atualização
if st.sidebar.button("Atualizar via API") or 'df_live' not in st.session_state:
    df, spot = buscar_dados_api(moeda)
    st.session_state.df_live = df
    st.session_state.spot_live = spot

if 'df_live' in st.session_state and not st.session_state.df_live.empty:
    df_raw = st.session_state.df_live
    spot = st.session_state.spot_live

    # Filtro de Strikes próximo ao preço atual
    margem = spot * (raio_pct / 100)
    df_filt = df_raw[(df_raw['strike'] > spot - margem) & (df_raw['strike'] < spot + margem)].copy()

    if not df_filt.empty:
        # Agrupamento para o visual de barras verticais lado a lado
        pivot = df_filt.groupby(['strike', 'tipo'])[metrica].sum().unstack().fillna(0)
        
        # Garante que as colunas de Call (C) e Put (P) existam no pivot
        for t in ['C', 'P']: 
            if t not in pivot.columns: pivot[t] = 0
        pivot = pivot.reset_index()

        # --- CONSTRUÇÃO DO GRÁFICO (Estilo Captura de Tela_30-4-2026_01556_www.deribit.com.jpeg) ---
        fig = go.Figure()
        
        # Barras de Calls (Azul)
        fig.add_trace(go.Bar(
            x=pivot['strike'], y=pivot['C'], 
            name='Calls', marker_color='#2E64FE'
        ))
        
        # Barras de Puts (Amarelo)
        fig.add_trace(go.Bar(
            x=pivot['strike'], y=pivot['P'], 
            name='Puts', marker_color='#F4D03F'
        ))

        # Linha Vertical do Preço Spot
        fig.add_vline(x=spot, line_dash="dash", line_color="red", 
                      annotation_text=f"SPOT: {spot:,.0f}", annotation_position="top")

        fig.update_layout(
            template="plotly_dark",
            barmode='group', # Lado a lado como solicitado
            xaxis=dict(title="Strike Price", type='category'), # 'category' para organizar os strikes linearmente
            yaxis=dict(title=metrica),
            height=600,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)
        )

        st.plotly_chart(fig, use_container_width=True)
        
        # Alerta se a métrica estiver zerada na API
        if df_filt[metrica].sum() == 0:
            st.warning(f"Os dados de {metrica} estão zerados na API para este ativo. Tente visualizar 'OI'.")
    else:
        st.warning("Nenhum contrato encontrado neste raio de preço.")
else:
    st.info("Clique em 'Atualizar' para buscar dados da Deribit.")
