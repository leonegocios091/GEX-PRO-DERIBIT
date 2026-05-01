import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timezone

# 1. SETUP
st.set_page_config(page_title="GEX Master Engine Pro", layout="wide")
st_autorefresh(interval=30000, key="datarefresh")

# 2. CONTROLES LATERAIS
st.sidebar.header("📊 Configurações")
moeda = st.sidebar.selectbox("Ativo", ["BTC", "ETH"])
modo_visao = st.sidebar.selectbox("Métrica Principal", ["Net GEX", "Net DEX", "Net OI"])
# Controle de opacidade para o usuário calibrar o fundo
opacidade_fundo = st.sidebar.slider("Opacidade GEX Abs (Fundo)", 0.0, 1.0, 0.12)

# 3. MOTOR DE DADOS
def carregar_deribit(ticker):
    url = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={ticker}&kind=option"
    try:
        res = requests.get(url, timeout=10).json()['result']
        df = pd.DataFrame(res)
        df['strike'] = df['instrument_name'].str.split('-').str[2].astype(float)
        df['data_exp'] = df['instrument_name'].str.split('-').str[1]
        df['tipo'] = df['instrument_name'].str.split('-').str[3]
        return df
    except: return None

df_raw = carregar_deribit(moeda)

if df_raw is not None and not df_raw.empty:
    preco_spot = df_raw['estimated_delivery_price'].iloc[0]
    hoje_utc = datetime.now(timezone.utc).strftime("%d%b%y").upper()
    exp_list = sorted(df_raw['data_exp'].unique())
    
    selecao_exp = st.sidebar.multiselect("Vencimentos", options=exp_list, 
                                       default=[hoje_utc] if hoje_utc in exp_list else [exp_list[0]])

    if selecao_exp:
        df = df_raw[df_raw['data_exp'].isin(selecao_exp)].copy()
        
        # Cálculos de Exposição (Milhões $)
        df['c_val'] = df.apply(lambda x: (x['open_interest'] * x['strike']) / 1e6 if x['tipo'] == 'C' else 0, axis=1)
        df['p_val'] = df.apply(lambda x: (x['open_interest'] * x['strike']) / 1e6 if x['tipo'] == 'P' else 0, axis=1)
        
        res = df.groupby('strike').agg({'c_val': 'sum', 'p_val': 'sum', 'open_interest': 'sum'}).reset_index()
        res['Net GEX'] = res['c_val'] - res['p_val']
        res['Net DEX'] = res['Net GEX'] * 1.15
        res['Net OI'] = (res['open_interest'] * res['strike']) / 1e6
        res['gex_abs'] = res['c_val'] + res['p_val']

        # Níveis Chave
        c_sort = res.sort_values('c_val', ascending=False)['strike'].tolist()
        p_sort = res.sort_values('p_val', ascending=False)['strike'].tolist()
        g_flip = res.iloc[(res['Net GEX']).abs().argsort()[:1]]['strike'].values[0]

        # --- CONSTRUÇÃO DO GRÁFICO (ORDEM DE CAMADAS) ---
        fig = go.Figure()
        
        # CAMADA 1: Abs GEX (Ocupa o fundo com opacidade)
        fig.add_trace(go.Scatter(
            x=res['strike'], 
            y=res['gex_abs'], 
            fill='tozeroy', 
            mode='lines', 
            line=dict(width=0), # Sem borda para não sobrepor as barras
            fillcolor='#6366f1', 
            opacity=opacidade_fundo,
            name='Abs GEX (Liquidez)'
        ))
        
        # CAMADA 2: Barras Net (Desenhadas por cima da sombra)
        cores = ['#00ffbb' if v > 0 else '#ff4444' for v in res[modo_visao]]
        fig.add_trace(go.Bar(
            x=res['strike'], 
            y=res[modo_visao], 
            marker=dict(color=cores, line=dict(width=0)),
            name=modo_visao
        ))

        # Configurações de Layout
        fig.update_layout(
            template="plotly_dark", height=600,
            yaxis=dict(title="M$", ticksuffix="M", gridcolor='rgba(255,255,255,0.05)'),
            xaxis=dict(title="STRIKE", range=[preco_spot*0.9, preco_spot*1.1], dtick=500),
            barmode='overlay', # Garante que as coordenadas sejam as mesmas
            showlegend=True
        )
        
        # Linhas de Referência
        fig.add_vline(x=preco_spot, line_color="orange", annotation_text="SPOT")
        fig.add_vline(x=c_sort[0], line_color="#00ffbb", line_dash="dash", annotation_text="CWALL")
        fig.add_vline(x=p_sort[0], line_color="#ff4444", line_dash="dash", annotation_text="PWALL")
        fig.add_vline(x=g_flip, line_color="white", line_dash="dot", annotation_text="G-FLIP")

        st.plotly_chart(fig, use_container_width=True)

        # String para o seu TradingView Indicator
        st.subheader("📋 Pine Script Engine String")
        tv_string = f"CW,{c_sort[0]},PW,{p_sort[0]},GFlip,{g_flip},Spot,{preco_spot:.0f}"
        st.code(tv_string, language="text")

else:
    st.info("Aguardando dados da Deribit...")
