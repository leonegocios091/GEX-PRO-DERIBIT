import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timezone

# 1. SETUP
st.set_page_config(page_title="GEX Master Engine Pro", layout="wide")
st_autorefresh(interval=30000, key="datarefresh")

# 2. CONTROLES
st.sidebar.header("🕹️ Painel de Controle")
moeda = st.sidebar.selectbox("Ativo", ["BTC", "ETH"])
opacidade_sombra = st.sidebar.slider("Opacidade Sombra GEX Abs", 0.0, 1.0, 0.15)

# 3. CARREGAMENTO
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
    
    # --- LOGICA 0DTE REAL (30APR26) ---
    hoje_utc = datetime.now(timezone.utc).strftime("%d%b%y").upper()
    exp_list = sorted(df_raw['data_exp'].unique())
    
    selecao_exp = st.sidebar.multiselect(
        "Vencimentos", options=exp_list, 
        default=[hoje_utc] if hoje_utc in exp_list else [exp_list[0]],
        format_func=lambda x: f"⚡ {x} (0DTE/LIVE)" if x == hoje_utc else x
    )

    if selecao_exp:
        df = df_raw[df_raw['data_exp'].isin(selecao_exp)].copy()
        
        # Cálculos de Métricas (Escalonando para Milhões)
        df['call_oi_usd'] = df.apply(lambda x: x['open_interest'] * x['strike'] if x['tipo'] == 'C' else 0, axis=1)
        df['put_oi_usd'] = df.apply(lambda x: x['open_interest'] * x['strike'] if x['tipo'] == 'P' else 0, axis=1)
        
        # Dealer Hedge Flow (Estimado)
        df['hedge_call'] = df['call_oi_usd'] * 0.05 # Proxy de Delta Hedging
        df['hedge_put'] = df['put_oi_usd'] * -0.05

        resumo = df.groupby('strike').agg({
            'call_oi_usd': 'sum', 'put_oi_usd': 'sum',
            'hedge_call': 'sum', 'hedge_put': 'sum'
        }).reset_index()

        resumo['gex_net'] = resumo['call_oi_usd'] - resumo['put_oi_usd']
        resumo['gex_abs'] = resumo['call_oi_usd'] + resumo['put_oi_usd']

        # Níveis
        cwall = resumo.loc[resumo['call_oi_usd'].idxmax(), 'strike']
        pwall = resumo.loc[resumo['put_oi_usd'].idxmax(), 'strike']
        gflip = resumo.iloc[(resumo['gex_net']).abs().argsort()[:1]]['strike'].values[0]
        
        # AG1/AG2 (Top GEX Absoluto)
        top_abs = resumo.sort_values(by='gex_abs', ascending=False)
        ag1, ag2 = top_abs.iloc[0]['strike'], top_abs.iloc[1]['strike']

        # --- PLOTAGEM PRINCIPAL ---
        fig = go.Figure()

        # Sombra de Liquidez (GEX Abs) - Sempre no Fundo
        fig.add_trace(go.Scatter(
            x=resumo['strike'], y=resumo['gex_abs'], fill='tozeroy', 
            mode='lines', line=dict(width=0), fillcolor=f'rgba(255, 255, 0, {opacidade_sombra})',
            name='GEX Abs (Liquidez)'
        ))

        # Net GEX Bars
        fig.add_trace(go.Bar(
            x=resumo['strike'], y=resumo['gex_net'],
            marker_color=['#00ffbb' if v > 0 else '#ff4444' for v in resumo['gex_net']],
            name='Net GEX'
        ))

        fig.update_layout(
            template="plotly_dark", height=500,
            xaxis=dict(title="STRIKE", range=[preco_spot*0.9, preco_spot*1.1], dtick=500),
            yaxis=dict(
                title="GEX Exposure (Escala M/B)",
                tickformat=".2s", # CORREÇÃO: Força 1M, 2M...
                exponentformat="SI",
                showgrid=True
            )
        )
        
        # Linhas de Nível
        for v, c, t in [(preco_spot, "orange", "SPOT"), (cwall, "#00ffbb", "CWALL"), (pwall, "#ff4444", "PWALL")]:
            fig.add_vline(x=v, line_color=c, line_dash="dash", annotation_text=t)

        st.plotly_chart(fig, use_container_width=True)

        # --- SUBGRÁFICO: DEALER HEDGE FLOW ---
        st.subheader("🌊 Dealer Hedge Flow (Buy/Sell Pressure)")
        fig_hedge = go.Figure()
        fig_hedge.add_trace(go.Scatter(x=resumo['strike'], y=resumo['hedge_call'], name="Call Hedge (Buy)", line=dict(color='#0088ff', width=3)))
        fig_hedge.add_trace(go.Scatter(x=resumo['strike'], y=resumo['hedge_put'], name="Put Hedge (Sell)", line=dict(color='#ff0000', width=3)))
        
        fig_hedge.update_layout(
            template="plotly_dark", height=300,
            yaxis=dict(tickformat=".2s", title="Hedge Pressure"),
            xaxis=dict(range=[preco_spot*0.9, preco_spot*1.1])
        )
        st.plotly_chart(fig_hedge, use_container_width=True)

        # --- PAINEL DE MÉTRICAS ---
        st.divider()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("SPOT", f"${preco_spot:,.0f}")
        c2.metric("G-FLIP", f"${gflip:,.0f}")
        c3.metric("AG1 (LQX)", f"${ag1:,.0f}")
        c4.metric("AG2 (LQX)", f"${ag2:,.0f}")

        # PINE SCRIPT STRING
        st.subheader("📋 Pine Script Master Engine")
        st.code(f"CWALL,{cwall},PWALL,{pwall},GFLIP,{gflip},AG1,{ag1},AG2,{ag2},SPOT,{preco_spot:.0f}", language="text")
