import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timezone
import numpy as np

# 1. SETUP
st.set_page_config(page_title="GEX Master Engine Pro", layout="wide")
st_autorefresh(interval=30000, key="datarefresh")

# 2. MENU LATERAL
st.sidebar.header("📊 Painel de Controle")
moeda = st.sidebar.selectbox("Ativo", ["BTC", "ETH"])
modo_visao = st.sidebar.selectbox("Métrica Principal", ["Net GEX", "Net DEX", "Net OI"])
opacidade_abs = st.sidebar.slider("Opacidade Amarela (Abs)", 0.0, 1.0, 0.15)

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
        
        # Cálculos de Exposição (M$)
        df['c_val'] = df.apply(lambda x: (x['open_interest'] * x['strike']) / 1e6 if x['tipo'] == 'C' else 0, axis=1)
        df['p_val'] = df.apply(lambda x: (x['open_interest'] * x['strike']) / 1e6 if x['tipo'] == 'P' else 0, axis=1)
        
        res = df.groupby('strike').agg({'c_val': 'sum', 'p_val': 'sum', 'open_interest': 'sum'}).reset_index()
        res['Net GEX'] = res['c_val'] - res['p_val']
        res['Net DEX'] = res['Net GEX'] * 1.15
        res['Net OI'] = (res['open_interest'] * res['strike']) / 1e6
        res['abs_gex'] = res['c_val'] + res['p_val']

        # Cálculos de Níveis
        c_sort = res.sort_values('c_val', ascending=False)['strike'].tolist()
        p_sort = res.sort_values('p_val', ascending=False)['strike'].tolist()
        g_flip = res.iloc[(res['Net GEX']).abs().argsort()[:1]]['strike'].values[0]
        
        # Estimativa Simples de Vanna/Charm para Exportação (Baseada em concentração de Gamma/Time)
        vanna_level = res.iloc[(res['abs_gex']).argsort()[-3:]]['strike'].mean() # Centro de Liquidez
        charm_level = g_flip * 0.98 if preco_spot < g_flip else g_flip * 1.02 # Atração temporal

        # --- GRÁFICO PRINCIPAL ---
        fig = go.Figure()
        
        # 1. Abs GEX (Sombra AMARELA ao fundo)
        fig.add_trace(go.Scatter(
            x=res['strike'], y=res['abs_gex'],
            fill='tozeroy', mode='none',
            fillcolor=f'rgba(255, 255, 0, {opacidade_abs})', # AMARELO CONFIGURÁVEL
            name='Abs GEX (Liquidez)'
        ))
        
        # 2. Barras Dinâmicas (GEX, DEX ou OI)
        cores = ['#00ffbb' if v > 0 else '#ff4444' for v in res[modo_visao]]
        fig.add_trace(go.Bar(
            x=res['strike'], y=res[modo_visao],
            marker_color=cores,
            width=300,
            name=modo_visao
        ))

        fig.update_layout(
            template="plotly_dark", height=600,
            yaxis=dict(title="M$", gridcolor='rgba(255,255,255,0.05)'),
            xaxis=dict(title="STRIKE", range=[preco_spot*0.85, preco_spot*1.15], dtick=500),
            barmode='overlay'
        )
        
        # Linhas Primárias
        fig.add_vline(x=preco_spot, line_color="orange", annotation_text="SPOT")
        fig.add_vline(x=c_sort[0], line_color="#00ffbb", line_dash="dash", annotation_text="CWALL")
        fig.add_vline(x=p_sort[0], line_color="#ff4444", line_dash="dash", annotation_text="PWALL")
        fig.add_vline(x=g_flip, line_color="white", line_dash="dot", annotation_text="G-FLIP")

        st.plotly_chart(fig, use_container_width=True)

        # --- HEDGE FLOW ---
        st.subheader("🌊 Dealer Hedge Flow & Greeks Pressure")
        fig_h = go.Figure()
        fig_h.add_trace(go.Scatter(x=res['strike'], y=res['c_val']*0.03, name="Vanna (+)", line=dict(color='#ffff00', width=2)))
        fig_h.add_trace(go.Scatter(x=res['strike'], y=res['p_val']*-0.03, name="Charm (-)", line=dict(color='#ff00ff', width=2)))
        fig_h.update_layout(template="plotly_dark", height=200)
        st.plotly_chart(fig_h, use_container_width=True)

        # --- STRING DE CÓPIA (VANNA & CHARM INCLUÍDOS) ---
        st.divider()
        st.subheader("📋 Pine Script Master String (Copy & Paste)")
        tv_string = (
            f"Spot,{preco_spot:.0f},GFlip,{g_flip:.0f},"
            f"CW1,{c_sort[0]:.0f},CW2,{c_sort[1]:.0f},"
            f"PW1,{p_sort[0]:.0f},PW2,{p_sort[1]:.0f},"
            f"Vanna,{vanna_level:.0f},Charm,{charm_level:.0f}"
        )
        st.code(tv_string, language="text")
        st.caption("Use estes valores para atualizar os níveis de suporte e magnetismo no seu indicador TradingView.")

else:
    st.info("Conectando ao terminal de dados Deribit...")
