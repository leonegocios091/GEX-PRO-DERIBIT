import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timezone

# 1. SETUP
st.set_page_config(page_title="GEX Master Engine Pro", layout="wide")
st_autorefresh(interval=30000, key="datarefresh")

# 2. MOTOR DE DADOS
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

# Função para formatar escala M/B
def format_m_b(val):
    abs_val = abs(val)
    if abs_val >= 1e3: return f"{val/1e3:.1f}B"
    return f"{val:.0f}M"

df_raw = carregar_deribit(st.sidebar.selectbox("Ativo", ["BTC", "ETH"]))

if df_raw is not None and not df_raw.empty:
    preco_spot = df_raw['estimated_delivery_price'].iloc[0]
    hoje_utc = datetime.now(timezone.utc).strftime("%d%b%y").upper()
    exp_list = sorted(df_raw['data_exp'].unique())
    
    selecao_exp = st.sidebar.multiselect("Vencimentos", options=exp_list, 
                                       default=[hoje_utc] if hoje_utc in exp_list else [exp_list[0]])

    if selecao_exp:
        df = df_raw[df_raw['data_exp'].isin(selecao_exp)].copy()
        
        # Cálculos em Milhões (M)
        df['c_val'] = df.apply(lambda x: (x['open_interest'] * x['strike']) / 1e6 if x['tipo'] == 'C' else 0, axis=1)
        df['p_val'] = df.apply(lambda x: (x['open_interest'] * x['strike']) / 1e6 if x['tipo'] == 'P' else 0, axis=1)
        
        res = df.groupby('strike').agg({'c_val': 'sum', 'p_val': 'sum', 'open_interest': 'sum'}).reset_index()
        res['Net GEX'] = res['c_val'] - res['p_val']
        res['gex_abs'] = (res['c_val'] + res['p_val'])
        
        # --- NÍVEIS PARA TRADINGVIEW ---
        c_sort = res.sort_values('c_val', ascending=False)['strike'].tolist()
        p_sort = res.sort_values('p_val', ascending=False)['strike'].tolist()
        g_flip = res.iloc[(res['Net GEX']).abs().argsort()[:1]]['strike'].values[0]

        # --- GRÁFICO PRINCIPAL ---
        fig = go.Figure()
        
        # 1. Abs GEX (Sombra Fundo)
        fig.add_trace(go.Scatter(
            x=res['strike'], y=res['gex_abs'],
            fill='tozeroy', mode='none',
            fillcolor='rgba(100, 80, 250, 0.15)',
            name='Abs GEX (OI)'
        ))
        
        # 2. Barras Net GEX (Ajuste de Largura/Tamanho)
        cores = ['#00ffbb' if v > 0 else '#ff4444' for v in res['Net GEX']]
        fig.add_trace(go.Bar(
            x=res['strike'], y=res['Net GEX'],
            marker_color=cores,
            width=350, # Ajuste o tamanho da largura da barra aqui
            name='Net GEX'
        ))

        fig.update_layout(
            template="plotly_dark", height=600,
            yaxis=dict(title="Financeiro (M/B)", gridcolor='rgba(255,255,255,0.05)'),
            xaxis=dict(title="STRIKE", range=[preco_spot*0.85, preco_spot*1.15], dtick=500),
            barmode='overlay'
        )
        
        # Níveis Visuais
        fig.add_vline(x=preco_spot, line_color="orange", annotation_text=f"SPOT: {preco_spot:.0f}")
        fig.add_vline(x=c_sort[0], line_color="#00ffbb", line_dash="dash", annotation_text="CWALL")
        fig.add_vline(x=p_sort[0], line_color="#ff4444", line_dash="dash", annotation_text="PWALL")
        fig.add_vline(x=g_flip, line_color="white", line_dash="dot", annotation_text="G-FLIP")

        st.plotly_chart(fig, use_container_width=True)

        # --- HEDGE FLOW ---
        st.subheader("🌊 Dealer Hedge Flow")
        fig_h = go.Figure()
        # Escala de Hedge estimada
        fig_h.add_trace(go.Scatter(x=res['strike'], y=res['c_val']*0.02, name="Call Pressure", line=dict(color='#0088ff', width=2)))
        fig_h.add_trace(go.Scatter(x=res['strike'], y=res['p_val']*-0.02, name="Put Pressure", line=dict(color='#ff4444', width=2)))
        fig_h.update_layout(template="plotly_dark", height=250, margin=dict(t=0, b=0))
        st.plotly_chart(fig_h, use_container_width=True)

        # --- BOTÃO DE CÓPIA TRADINGVIEW ---
        st.divider()
        st.subheader("🚀 TradingView Master Engine Sync")
        # Formatando a string conforme os inputs do Pine Script
        tv_levels = f"Spot={preco_spot:.0f}, GFlip={g_flip:.0f}, CW1={c_sort[0]:.0f}, CW2={c_sort[1]:.0f}, PW1={p_sort[0]:.0f}, PW2={p_sort[1]:.0f}"
        st.code(tv_levels, language="text")
        st.info("Copie os valores acima para os Inputs do seu indicador no TradingView.")

else:
    st.warning("Aguardando conexão com Deribit...")
