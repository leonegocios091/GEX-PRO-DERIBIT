import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timezone

# 1. SETUP
st.set_page_config(page_title="GEX Master Engine Pro", layout="wide")
st_autorefresh(interval=30000, key="datarefresh")

# 2. MENU LATERAL
st.sidebar.header("🎨 Ajustes Visuais")
moeda = st.sidebar.selectbox("Ativo", ["BTC", "ETH"])
modo_visao = st.sidebar.selectbox("Métrica Principal", ["Net GEX", "Net DEX", "Net OI"])

st.sidebar.divider()
cor_gex_pos = st.sidebar.color_picker("Barras Positivas", "#00ffbb")
cor_gex_neg = st.sidebar.color_picker("Barras Negativas", "#ff4444")
cor_abs_fundo = st.sidebar.color_picker("Área Abs GEX (Invertida)", "#6366f1") # Tom roxo/azul da foto
opacidade_abs = st.sidebar.slider("Opacidade Abs GEX", 0.0, 1.0, 0.35)

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
        
        # Cálculos (M$)
        df['c_val'] = df.apply(lambda x: (x['open_interest'] * x['strike']) / 1e6 if x['tipo'] == 'C' else 0, axis=1)
        df['p_val'] = df.apply(lambda x: (x['open_interest'] * x['strike']) / 1e6 if x['tipo'] == 'P' else 0, axis=1)
        
        resumo = df.groupby('strike').agg({'c_val': 'sum', 'p_val': 'sum', 'open_interest': 'sum'}).reset_index()
        resumo['Net GEX'] = resumo['c_val'] - resumo['p_val']
        resumo['gex_abs_inv'] = (resumo['c_val'] + resumo['p_val']) * -1 # Inversão para o fundo
        resumo['Net DEX'] = resumo['Net GEX'] * 1.1
        resumo['Net OI'] = (resumo['open_interest'] * resumo['strike']) / 1e6

        # Níveis
        c_sort = resumo.sort_values('c_val', ascending=False)['strike'].tolist()
        p_sort = resumo.sort_values('p_val', ascending=False)['strike'].tolist()
        gamma_flip = resumo.iloc[(resumo['Net GEX']).abs().argsort()[:1]]['strike'].values[0]

        # --- CONSTRUÇÃO DO GRÁFICO ---
        fig = go.Figure()
        
        # 1. Abs GEX Invertido (Visual da foto: Área roxa com pontos na parte inferior)
        fig.add_trace(go.Scatter(
            x=resumo['strike'], 
            y=resumo['gex_abs_inv'], 
            fill='tozeroy', 
            mode='lines+markers', 
            marker=dict(size=6, color=cor_abs_fundo),
            line=dict(width=2, color=cor_abs_fundo),
            fillcolor=cor_abs_fundo, 
            opacity=opacidade_abs,
            name='Abs GEX (Liquidez Total)'
        ))
        
        # 2. Barras Net (Ficam no centro/topo)
        cores_barras = [cor_gex_pos if v > 0 else cor_gex_neg for v in resumo[modo_visao]]
        fig.add_trace(go.Bar(
            x=resumo['strike'], 
            y=resumo[modo_visao], 
            marker_color=cores_barras, 
            name=modo_visao
        ))

        fig.update_layout(
            template="plotly_dark", height=650,
            yaxis=dict(title="GEX ($)", gridcolor='rgba(255,255,255,0.05)', zerolinecolor='white'),
            xaxis=dict(title="STRIKE", range=[preco_spot*0.9, preco_spot*1.1], dtick=500),
            barmode='overlay',
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        # Níveis Visuais
        fig.add_vline(x=preco_spot, line_color="orange", annotation_text=f"Spot: {preco_spot:.2f}", line_width=2)
        fig.add_vline(x=gamma_flip, line_color="white", line_dash="dot", annotation_text="G-Flip")

        st.plotly_chart(fig, use_container_width=True)

        # --- EXPORTAÇÃO TRADINGVIEW ---
        st.subheader("📋 String para TradingView")
        tv_string = (
            f"CallWall/VOL+,{c_sort[0]},2CallWall,{c_sort[1]},"
            f"PutWall,{p_sort[0]},2PutWall,{p_sort[1]},"
            f"GammaFlip,{gamma_flip},Spot,{preco_spot:.0f}"
        )
        st.code(tv_string, language="text")

        # --- HEDGE FLOW ---
        st.subheader("🌊 Dealer Hedge Flow")
        fig_h = go.Figure()
        fig_h.add_trace(go.Scatter(x=resumo['strike'], y=resumo['c_val'] * 0.05, name="Hedge Call", line=dict(color='#0088ff')))
        fig_h.add_trace(go.Scatter(x=resumo['strike'], y=resumo['p_val'] * -0.05, name="Hedge Put", line=dict(color='#ff4444')))
        fig_h.update_layout(template="plotly_dark", height=200)
        st.plotly_chart(fig_h, use_container_width=True)

else:
    st.info("Buscando dados da Deribit...")
