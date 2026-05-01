import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timezone

# 1. CONFIGURAÇÃO
st.set_page_config(page_title="GEX Master Engine Pro", layout="wide")
st_autorefresh(interval=30000, key="datarefresh")

# 2. SIDEBAR - CONTROLES
st.sidebar.header("🕹️ Painel de Controle")
moeda = st.sidebar.selectbox("Ativo", ["BTC", "ETH"])
modo_visao = st.sidebar.radio("Métrica das Barras", ["Net GEX", "Net DEX (Delta)", "Open Interest (OI)"])
cor_sombra = st.sidebar.color_picker("Cor da Sombra (GEX Abs)", "#6450fa")

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
    
    # --- LÓGICA 0DTE REAL ---
    # Captura a data exata de hoje no formato da Deribit (Ex: 30APR26)
    hoje_real = datetime.now(timezone.utc).strftime("%d%b%y").upper()
    exp_list = sorted(df_raw['data_exp'].unique())
    
    # Se a data de hoje existe na API, ela será o default. Caso contrário, não força.
    vencimento_default = [hoje_real] if hoje_real in exp_list else [exp_list[0]]
    
    selecao_exp = st.sidebar.multiselect(
        "Expirações", options=exp_list, default=vencimento_default,
        format_func=lambda x: f"⚡ {x} (0DTE/LIVE)" if x == hoje_real else x
    )

    if selecao_exp:
        df = df_raw[df_raw['data_exp'].isin(selecao_exp)].copy()
        
        # Cálculos de OI, GEX e DEX
        df['call_oi'] = df.apply(lambda x: x['open_interest'] if x['tipo'] == 'C' else 0, axis=1)
        df['put_oi'] = df.apply(lambda x: x['open_interest'] if x['tipo'] == 'P' else 0, axis=1)
        df['gex_net'] = df['call_oi'] - df['put_oi']
        df['gex_abs'] = df['call_oi'] + df['put_oi']
        # DEX Scaled to M/B
        df['dex_net'] = df.apply(lambda x: (x['open_interest'] * x['strike']) if x['tipo'] == 'C' else (-x['open_interest'] * x['strike']), axis=1)
        
        resumo = df.groupby('strike').agg({
            'gex_net': 'sum', 'gex_abs': 'sum', 'dex_net': 'sum', 
            'call_oi': 'sum', 'put_oi': 'sum', 'open_interest': 'sum'
        }).reset_index()

        # Níveis Críticos
        cwall = resumo.loc[resumo['call_oi'].idxmax(), 'strike']
        pwall = resumo.loc[resumo['put_oi'].idxmax(), 'strike']
        gflip = resumo.iloc[(resumo['gex_net']).abs().argsort()[:1]]['strike'].values[0]

        # --- GRÁFICO PRINCIPAL ---
        fig = go.Figure()
        
        # Sombra de Liquidez (GEX Abs)
        fig.add_trace(go.Scatter(x=resumo['strike'], y=resumo['gex_abs'], fill='tozeroy', mode='none', fillcolor=cor_sombra, opacity=0.2, name='GEX Abs'))

        # Seleção Dinâmica de Métrica
        if modo_visao == "Net GEX":
            y_vals = resumo['gex_net']
        elif modo_visao == "Net DEX (Delta)":
            y_vals = resumo['dex_net']
        else:
            y_vals = resumo['open_interest']

        fig.add_trace(go.Bar(x=resumo['strike'], y=y_vals, marker_color=['#00ffbb' if v > 0 else '#ff4444' for v in y_vals], name=modo_visao))

        fig.update_layout(
            template="plotly_dark",
            xaxis=dict(title="STRIKE", range=[preco_spot - 5000, preco_spot + 5000], dtick=500),
            yaxis=dict(title=modo_visao, tickformat=".2s", exponentformat="SI"), # ESCALA M/B ATIVA
            height=500
        )
        
        # Linhas SPOT e Walls
        for val, col, txt in [(preco_spot, "orange", "SPOT"), (cwall, "#00ffbb", "CWALL"), (pwall, "#ff4444", "PWALL")]:
            fig.add_vline(x=val, line_color=col, line_dash="dash", annotation_text=txt)

        st.plotly_chart(fig, use_container_width=True)

        # --- GRÁFICO DE LINHAS: CALL/PUT PREMIUM (PCR) ---
        st.subheader("📈 Call vs Put Premium (OI Flow)")
        fig_pcr = go.Figure()
        fig_pcr.add_trace(go.Scatter(x=resumo['strike'], y=resumo['call_oi'], name="Call OI", line=dict(color='#00ffbb', width=2)))
        fig_pcr.add_trace(go.Scatter(x=resumo['strike'], y=resumo['put_oi'], name="Put OI", line=dict(color='#ff4444', width=2)))
        
        fig_pcr.update_layout(
            template="plotly_dark", height=300,
            xaxis=dict(title="Strike", range=[preco_spot - 5000, preco_spot + 5000]),
            yaxis=dict(tickformat=".2s")
        )
        st.plotly_chart(fig_pcr, use_container_width=True)

        # --- MÉTRICAS ---
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("SPOT", f"${preco_spot:,.0f}")
        m2.metric("C-WALL", f"${cwall:,.0f}")
        m3.metric("P-WALL", f"${pwall:,.0f}")
        m4.metric("G-FLIP", f"${gflip:,.0f}")
        m5.metric("PCR", f"{(df['put_oi'].sum()/df['call_oi'].sum()):.2f}")

        st.code(f"CWALL,{cwall},PWALL,{pwall},GFLIP,{gflip},SPOT,{preco_spot:.0f}", language="text")
