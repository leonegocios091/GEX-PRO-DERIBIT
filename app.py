import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
import numpy as np
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timezone

# 1. SETUP
st.set_page_config(page_title="GEX Master Engine Pro", layout="wide")
st_autorefresh(interval=30000, key="datarefresh")

# 2. CONTROLES DE INTERFACE
st.sidebar.header("🕹️ Painel de Controle")
moeda = st.sidebar.selectbox("Ativo", ["BTC", "ETH"])
modo_visao = st.sidebar.radio("Métrica Principal", ["Net GEX", "Net DEX", "Net OI"])
opacidade_sombra = st.sidebar.slider("Opacidade Sombra GEX Abs", 0.0, 1.0, 0.15)

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
    
    selecao_exp = st.sidebar.multiselect(
        "Vencimentos", options=exp_list, 
        default=[hoje_utc] if hoje_utc in exp_list else [exp_list[0]],
        format_func=lambda x: f"⚡ {x} (0DTE/LIVE)" if x == hoje_utc else x
    )

    if selecao_exp:
        df = df_raw[df_raw['data_exp'].isin(selecao_exp)].copy()
        
        # Cálculos de OI (Em milhões para escala vertical correta)
        df['call_oi_m'] = df.apply(lambda x: (x['open_interest'] * x['strike']) / 1e6 if x['tipo'] == 'C' else 0, axis=1)
        df['put_oi_m'] = df.apply(lambda x: (x['open_interest'] * x['strike']) / 1e6 if x['tipo'] == 'P' else 0, axis=1)
        
        resumo = df.groupby('strike').agg({'call_oi_m': 'sum', 'put_oi_m': 'sum'}).reset_index()
        
        # Métricas de Visualização
        resumo['Net GEX'] = (resumo['call_oi_m'] - resumo['put_oi_m']) * 0.1
        resumo['Net DEX'] = resumo['call_oi_m'] - resumo['put_oi_m']
        resumo['Net OI'] = (resumo['call_oi_m'] + resumo['put_oi_m']) / 2
        resumo['GEX Abs'] = resumo['call_oi_m'] + resumo['put_oi_m']

        # --- RANKING DE NÍVEIS (PARA TRADINGVIEW) ---
        c_levels = resumo.sort_values('call_oi_m', ascending=False)['strike'].unique()
        p_levels = resumo.sort_values('put_oi_m', ascending=False)['strike'].unique()
        
        # Pegando 4 níveis de cada lado
        c_wall, c2, c3, c4 = c_levels[0], c_levels[1], c_levels[2], c_levels[3]
        p_wall, p2, p3, p4 = p_levels[0], p_levels[1], p_levels[2], p_levels[3]
        g_flip = resumo.iloc[(resumo['Net GEX']).abs().argsort()[:1]]['strike'].values[0]

        # --- GRÁFICO PRINCIPAL ---
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=resumo['strike'], y=resumo['GEX Abs'], fill='tozeroy', mode='none', 
                                 fillcolor=f'rgba(255,255,0,{opacidade_sombra})', name='GEX Abs'))
        
        y_data = resumo[modo_visao]
        fig.add_trace(go.Bar(x=resumo['strike'], y=y_data, 
                             marker_color=['#00ffbb' if v > 0 else '#ff4444' for v in y_data], name=modo_visao))

        fig.update_layout(template="plotly_dark", height=500,
                          yaxis=dict(title=f"{modo_visao} (Milhões $)", ticksuffix="M"),
                          xaxis=dict(range=[preco_spot*0.9, preco_spot*1.1], dtick=500))
        
        for v, c, t in [(preco_spot, "orange", "SPOT"), (c_wall, "#00ffbb", "CWALL"), (p_wall, "#ff4444", "PWALL")]:
            fig.add_vline(x=v, line_color=c, line_dash="dash", annotation_text=t)

        st.plotly_chart(fig, use_container_width=True)

        # --- DEALER HEDGE FLOW (SUBGRÁFICO) ---
        st.subheader("🌊 Dealer Hedge Flow & Premium")
        fig_h = go.Figure()
        fig_h.add_trace(go.Scatter(x=resumo['strike'], y=resumo['call_oi_m'] * 0.05, name="Call Hedge (Buy)", line=dict(color='#0088ff')))
        fig_h.add_trace(go.Scatter(x=resumo['strike'], y=resumo['put_oi_m'] * -0.05, name="Put Hedge (Sell)", line=dict(color='#ff0000')))
        fig_h.update_layout(template="plotly_dark", height=250, yaxis=dict(ticksuffix="M"))
        st.plotly_chart(fig_h, use_container_width=True)

        # --- MÉTRICAS DE VOL E SENSIBILIDADE (SIMULADAS) ---
        st.divider()
        col1, col2, col3, col4 = st.columns(4)
        vol_50 = preco_spot * 0.02 # Exemplo
        vanna_total = resumo['Net GEX'].sum() * 0.01
        
        col1.metric("Vol 50%", f"${vol_50:,.0f}")
        col2.metric("Vanna", f"{vanna_total:.2f}M")
        col3.metric("Charm", f"{(vanna_total/2):.2f}M")
        col4.metric("PCR Total", f"{(resumo['put_oi_m'].sum()/resumo['call_oi_m'].sum()):.2f}")

        # --- STRING EXPORT TRADINGVIEW ---
        st.subheader("📋 Pine Script Master Engine String")
        # Níveis primários e secundários para o código Pine
        tv_string = (f"SPOT,{preco_spot:.0f},CWALL,{c_wall},C2,{c2},C3,{c3},PWALL,{p_wall},P2,{p2},P3,{p3},"
                     f"GFLIP,{g_flip},VOL50,{vol_50:.0f},VANNA,{vanna_total:.1f}")
        st.code(tv_string, language="text")

else:
    st.info("Aguardando dados da Deribit...")
