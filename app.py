import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timezone

# 1. SETUP E REFRESH
st.set_page_config(page_title="GEX Master Engine Pro", layout="wide")
st_autorefresh(interval=30000, key="datarefresh")

# 2. CONTROLES LATERAIS
st.sidebar.header("🕹️ Parâmetros de Mercado")
moeda = st.sidebar.selectbox("Ativo", ["BTC", "ETH"])
modo_visao = st.sidebar.radio("Métrica Principal", ["Net GEX", "Net DEX (Delta)", "Open Interest"])
opacidade_sombra = st.sidebar.slider("Opacidade Sombra GEX Abs", 0.0, 1.0, 0.15)

# 3. CARREGAMENTO DE DADOS (DERIBIT)
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
    
    # --- CORREÇÃO DEFINITIVA 0DTE ---
    hoje_utc = datetime.now(timezone.utc).strftime("%d%b%y").upper()
    exp_list = sorted(df_raw['data_exp'].unique())
    
    # Busca exata ou a mais próxima se for feriado/fuso
    selecao_exp = st.sidebar.multiselect(
        "Expirações", options=exp_list, 
        default=[hoje_utc] if hoje_utc in exp_list else [exp_list[0]],
        format_func=lambda x: f"⚡ {x} (0DTE/LIVE)" if x == hoje_utc else x
    )

    if selecao_exp:
        df = df_raw[df_raw['data_exp'].isin(selecao_exp)].copy()
        
        # Cálculos de Métricas
        df['call_oi'] = df.apply(lambda x: x['open_interest'] if x['tipo'] == 'C' else 0, axis=1)
        df['put_oi'] = df.apply(lambda x: x['open_interest'] if x['tipo'] == 'P' else 0, axis=1)
        df['gex_net'] = (df['call_oi'] - df['put_oi']) * 0.1  # Proxy Gamma
        df['gex_abs'] = (df['call_oi'] + df['put_oi']) * 0.1
        df['dex_net'] = (df['call_oi'] - df['put_oi']) * df['strike']

        resumo = df.groupby('strike').agg({
            'gex_net': 'sum', 'gex_abs': 'sum', 'dex_net': 'sum', 
            'call_oi': 'sum', 'put_oi': 'sum', 'open_interest': 'sum'
        }).reset_index()

        # --- CÁLCULO DE NÍVEIS SECUNDÁRIOS ---
        cwall = resumo.loc[resumo['call_oi'].idxmax(), 'strike']
        pwall = resumo.loc[resumo['put_oi'].idxmax(), 'strike']
        gflip = resumo.iloc[(resumo['gex_net']).abs().argsort()[:1]]['strike'].values[0]
        
        # Níveis AG, C1/C2 e P1/P2 baseados em ranking de OI
        top_calls = resumo.sort_values(by='call_oi', ascending=False)
        c1, c2 = top_calls.iloc[1]['strike'], top_calls.iloc[2]['strike']
        
        top_puts = resumo.sort_values(by='put_oi', ascending=False)
        p1, p2 = top_puts.iloc[1]['strike'], top_puts.iloc[2]['strike']
        
        top_abs = resumo.sort_values(by='gex_abs', ascending=False)
        ag1, ag2 = top_abs.iloc[0]['strike'], top_abs.iloc[1]['strike']

        # --- GRÁFICO PRINCIPAL ---
        fig = go.Figure()

        # GEX Absoluto como SHAPE de fundo (Não sobrepõe as barras)
        fig.add_trace(go.Scatter(
            x=resumo['strike'], y=resumo['gex_abs'], fill='tozeroy', 
            mode='lines', line=dict(width=0), fillcolor=f'rgba(255, 255, 0, {opacidade_sombra})',
            name='GEX Abs (Liquidez)', hoverinfo='skip'
        ))

        # Barras de GEX/DEX/OI
        y_vals = resumo['gex_net'] if modo_visao == "Net GEX" else resumo['dex_net'] if modo_visao == "Net DEX (Delta)" else resumo['open_interest']
        
        fig.add_trace(go.Bar(
            x=resumo['strike'], y=y_vals,
            marker_color=['#00ffbb' if v > 0 else '#ff4444' for v in y_vals],
            name=modo_visao
        ))

        # CONFIGURAÇÃO DE ESCALA M/B
        fig.update_layout(
            template="plotly_dark", height=550,
            xaxis=dict(title="STRIKE", range=[preco_spot*0.9, preco_spot*1.1], dtick=500),
            yaxis=dict(
                title=f"{modo_visao} (Escala M/B)",
                tickformat=".2s", # Força 1M, 10M, 1B
                hoverformat=".2s",
                exponentformat="SI"
            ),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )

        # Plotagem dos Níveis (Primários e Secundários)
        niveis = [
            (preco_spot, "orange", "SPOT", "solid"),
            (cwall, "#00ffbb", "CWALL", "dash"),
            (pwall, "#ff4444", "PWALL", "dash"),
            (gflip, "gray", "GFLIP", "dot")
        ]
        for val, col, txt, style in niveis:
            fig.add_vline(x=val, line_color=col, line_dash=style, annotation_text=txt)

        st.plotly_chart(fig, use_container_width=True)

        # --- SUBGRÁFICO PCR PREMIUM ---
        st.subheader("📊 PCR Premium Flow (Call vs Put OI)")
        fig_pcr = go.Figure()
        fig_pcr.add_trace(go.Scatter(x=resumo['strike'], y=resumo['call_oi'], name="Call OI", line=dict(color='#00ffbb')))
        fig_pcr.add_trace(go.Scatter(x=resumo['strike'], y=resumo['put_oi'], name="Put OI", line=dict(color='#ff4444')))
        fig_pcr.update_layout(template="plotly_dark", height=250, yaxis=dict(tickformat=".2s"))
        st.plotly_chart(fig_pcr, use_container_width=True)

        # --- PAINEL DE NÍVEIS SECUNDÁRIOS ---
        st.divider()
        c1_col, c2_col, c3_col, c4_col = st.columns(4)
        c1_col.metric("AG1 (GEX)", f"${ag1:,.0f}")
        c2_col.metric("C1 (CallWall)", f"${c1:,.0f}")
        c3_col.metric("P1 (PutWall)", f"${p1:,.0f}")
        c4_col.metric("PCR", f"{(df['put_oi'].sum()/df['call_oi'].sum()):.2f}")

        # --- EXPORT PINE SCRIPT ---
        st.subheader("📋 Pine Script Master String")
        tv_export = f"SPOT,{preco_spot:.0f},CWALL,{cwall},PWALL,{pwall},GFLIP,{gflip},AG1,{ag1},AG2,{ag2},C1,{c1},P1,{p1}"
        st.code(tv_export, language="text")
