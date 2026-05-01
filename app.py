import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timezone
import numpy as np

# 1. CONFIGURAÇÃO
st.set_page_config(page_title="GEX Master Engine Pro", layout="wide")
st_autorefresh(interval=30000, key="datarefresh")

# 2. SIDEBAR - CONTROLES AVANÇADOS
st.sidebar.header("🕹️ Painel de Controle")
moeda = st.sidebar.selectbox("Ativo", ["BTC", "ETH"])
modo_visao = st.sidebar.radio("Métrica das Barras", ["Net GEX", "Net DEX (Delta)", "Open Interest (OI)"])
cor_sombra = st.sidebar.color_picker("Cor da Sombra (GEX Abs)", "#6450fa")
opacidade_sombra = st.sidebar.slider("Opacidade da Sombra", 0.0, 1.0, 0.2)

# 3. CARREGAMENTO DE DADOS
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
    
    # --- FIX 0DTE: Captura exata 30APR26 ---
    hoje_utc = datetime.now(timezone.utc).strftime("%d%b%y").upper()
    exp_list = sorted(df_raw['data_exp'].unique())
    
    # Força a detecção da data atual se ela existir na lista da API
    vencimento_selecionado = st.sidebar.multiselect(
        "Expirações", options=exp_list, 
        default=[x for x in exp_list if x == hoje_utc] if hoje_utc in exp_list else [exp_list[0]],
        format_func=lambda x: f"⚡ {x} (0DTE/LIVE)" if x == hoje_utc else x
    )

    if vencimento_selecionado:
        df = df_raw[df_raw['data_exp'].isin(vencimento_selecionado)].copy()
        
        # Cálculos Base
        df['call_oi'] = df.apply(lambda x: x['open_interest'] if x['tipo'] == 'C' else 0, axis=1)
        df['put_oi'] = df.apply(lambda x: x['open_interest'] if x['tipo'] == 'P' else 0, axis=1)
        df['gex_net'] = df['call_oi'] - df['put_oi']
        df['gex_abs'] = df['call_oi'] + df['put_oi']
        df['dex_net'] = df.apply(lambda x: (x['open_interest'] * x['strike']) if x['tipo'] == 'C' else (-x['open_interest'] * x['strike']), axis=1)
        
        # Sensibilidades (Vanna/Charm Approx)
        df['vanna'] = df['gex_net'] * (df['strike'] / preco_spot)
        df['charm'] = df['gex_net'] / df['strike']

        resumo = df.groupby('strike').agg({
            'gex_net': 'sum', 'gex_abs': 'sum', 'dex_net': 'sum', 
            'call_oi': 'sum', 'put_oi': 'sum', 'vanna': 'sum', 'charm': 'sum'
        }).reset_index()

        # Níveis Principais e AGs
        cwall = resumo.loc[resumo['call_oi'].idxmax(), 'strike']
        pwall = resumo.loc[resumo['put_oi'].idxmax(), 'strike']
        gflip = resumo.iloc[(resumo['gex_net']).abs().argsort()[:1]]['strike'].values[0]
        
        ag_niveis = resumo.sort_values(by='gex_abs', ascending=False).head(4)['strike'].tolist()
        ag1, ag2 = ag_niveis[0], ag_niveis[1]

        # --- GRÁFICO PRINCIPAL ---
        fig = go.Figure()
        
        # Sombra GEX Abs com Opacidade Dinâmica
        fig.add_trace(go.Scatter(
            x=resumo['strike'], y=resumo['gex_abs'], fill='tozeroy', 
            mode='none', fillcolor=cor_sombra, opacity=opacidade_sombra, name='GEX Abs'
        ))

        # Barras com Escala Unificada
        y_vals = resumo['gex_net'] if modo_visao == "Net GEX" else resumo['dex_net'] if modo_visao == "Net DEX (Delta)" else resumo['call_oi'] + resumo['put_oi']
        
        fig.add_trace(go.Bar(
            x=resumo['strike'], y=y_vals, 
            marker_color=['#00ffbb' if v > 0 else '#ff4444' for v in y_vals],
            name=modo_visao
        ))

        fig.update_layout(
            template="plotly_dark",
            xaxis=dict(title="STRIKE", range=[preco_spot*0.92, preco_spot*1.08], dtick=500),
            yaxis=dict(
                title=f"{modo_visao} (Escala M/B)", 
                tickformat=".2s", # UNIFICAÇÃO M/B
                exponentformat="SI",
                showgrid=True,
                gridcolor='rgba(255,255,255,0.1)'
            ),
            height=600
        )
        
        # Linhas de Suporte/Resistência
        for val, col, txt in [(preco_spot, "orange", "SPOT"), (cwall, "#00ffbb", "CWALL"), (pwall, "#ff4444", "PWALL")]:
            fig.add_vline(x=val, line_color=col, line_dash="dash", annotation_text=txt)

        st.plotly_chart(fig, use_container_width=True)

        # --- MÉTRICAS E NÍVEIS SECUNDÁRIOS ---
        st.divider()
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("SPOT", f"${preco_spot:,.0f}")
        m2.metric("G-FLIP", f"${gflip:,.0f}")
        m3.metric("AG1 (GEX)", f"${ag1:,.0f}")
        m4.metric("Vanna Total", f"{resumo['vanna'].sum():.2s}")
        m5.metric("Charm Total", f"{resumo['charm'].sum():.2s}")

        # Gráfico PCR / OI Flow
        st.subheader("📈 Call/Put Premium Ratio (OI Flow)")
        fig_pcr = go.Figure()
        fig_pcr.add_trace(go.Scatter(x=resumo['strike'], y=resumo['call_oi'], name="Call OI", line=dict(color='#00ffbb')))
        fig_pcr.add_trace(go.Scatter(x=resumo['strike'], y=resumo['put_oi'], name="Put OI", line=dict(color='#ff4444')))
        fig_pcr.update_layout(template="plotly_dark", height=300, yaxis=dict(tickformat=".2s"))
        st.plotly_chart(fig_pcr, use_container_width=True)

        # Pine Script Export
        tv_code = f"CWALL,{cwall},PWALL,{pwall},GFLIP,{gflip},AG1,{ag1},AG2,{ag2},SPOT,{preco_spot:.0f}"
        st.subheader("📋 Pine Script Export")
        st.code(tv_code, language="text")
