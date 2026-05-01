import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timezone

# 1. CONFIGURAÇÃO E REFRESH
st.set_page_config(page_title="GEX Master Engine Pro", layout="wide")
st_autorefresh(interval=30000, key="datarefresh")

# 2. SIDEBAR - MENUS DE CONFIGURAÇÃO
st.sidebar.header("⚙️ Configurações de Visualização")
moeda = st.sidebar.selectbox("Ativo", ["BTC", "ETH"])
modo_tema = st.sidebar.radio("Tema", ["Dark", "Light"])
modo_visao = st.sidebar.radio("Métrica das Barras", ["Net GEX", "Net DEX (Delta)"])
cor_abs = st.sidebar.selectbox("Cor da Sombra (GEX Abs)", ["Roxo", "Amarelo", "Cinza"])

# Mapeamento de cores para a sombra
cores_sombra = {
    "Roxo": "rgba(100, 80, 250, 0.2)",
    "Amarelo": "rgba(255, 255, 0, 0.15)",
    "Cinza": "rgba(150, 150, 150, 0.2)"
}

# 3. CARREGAMENTO DE DADOS
def carregar_deribit(ticker):
    url = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={ticker}&kind=option"
    try:
        response = requests.get(url, timeout=10).json()
        if 'result' not in response: return None
        df = pd.DataFrame(response['result'])
        
        # Extração de componentes das colunas
        df['strike'] = df['instrument_name'].str.split('-').str[2].astype(float)
        df['data_exp'] = df['instrument_name'].str.split('-').str[1]
        df['tipo'] = df['instrument_name'].str.split('-').str[3]
        return df
    except Exception as e:
        return None

df_raw = carregar_deribit(moeda)

if df_raw is not None and not df_raw.empty:
    preco_spot = df_raw['estimated_delivery_price'].iloc[0]
    
    # --- AJUSTE DE DATA (30/04/2026 EM DIANTE) ---
    exp_list = sorted(df_raw['data_exp'].unique())
    # Hoje no formato Deribit (ex: 30APR26)
    hoje_utc = datetime.now(timezone.utc).strftime("%d%b%y").upper()
    
    selecao_exp = st.sidebar.multiselect(
        "Expirações Disponíveis", 
        options=exp_list, 
        default=[exp_list[0]],
        format_func=lambda x: f"⚡ {x} (LIVE/0DTE)" if x == hoje_utc or x == exp_list[0] else x
    )

    if selecao_exp:
        df = df_raw[df_raw['data_exp'].isin(selecao_exp)].copy()
        
        # Cálculos de OI e GEX
        df['call_oi'] = df.apply(lambda x: x['open_interest'] if x['tipo'] == 'C' else 0, axis=1)
        df['put_oi'] = df.apply(lambda x: x['open_interest'] if x['tipo'] == 'P' else 0, axis=1)
        df['gex_net'] = df['call_oi'] - df['put_oi']
        df['gex_abs'] = df['call_oi'] + df['put_oi']
        df['dex_net'] = df.apply(lambda x: (x['open_interest'] * x['strike']) if x['tipo'] == 'C' else (-x['open_interest'] * x['strike']), axis=1)
        
        # Agrupamento Seguro
        resumo = df.groupby('strike').agg({
            'gex_net': 'sum', 'gex_abs': 'sum', 'dex_net': 'sum', 
            'call_oi': 'sum', 'put_oi': 'sum'
        }).reset_index()

        # Níveis Críticos
        cwall = resumo.loc[resumo['call_oi'].idxmax(), 'strike']
        pwall = resumo.loc[resumo['put_oi'].idxmax(), 'strike']
        gflip = resumo.iloc[(resumo['gex_net']).abs().argsort()[:1]]['strike'].values[0]

        # --- PLOTAGEM COM ESCALA M/B ---
        fig = go.Figure()

        # Sombra de GEX Absoluto (Cor configurável)
        fig.add_trace(go.Scatter(
            x=resumo['strike'], y=resumo['gex_abs'], 
            fill='tozeroy', mode='none', 
            fillcolor=cores_sombra[cor_abs], 
            name='GEX Absoluto'
        ))

        # Barras de Net GEX ou Net DEX
        y_plot = resumo['gex_net'] if modo_visao == "Net GEX" else resumo['dex_net']
        colors = ['#00ffbb' if v > 0 else '#ff4444' for v in y_plot]

        fig.add_trace(go.Bar(x=resumo['strike'], y=y_plot, marker_color=colors, name=modo_visao))

        fig.update_layout(
            template="plotly_dark" if modo_tema == "Dark" else "plotly_white",
            xaxis=dict(
                title="Strike Price", 
                range=[preco_spot - 5000, preco_spot + 5000], 
                dtick=500, 
                tickformat="d"
            ),
            yaxis=dict(
                title=modo_visao, 
                tickformat=".2s",  # ESCALA M/B PARA GEX E DELTA
                exponentformat="SI"
            ),
            height=600,
            margin=dict(l=50, r=50, t=50, b=50)
        )

        # Linhas de Referência
        fig.add_vline(x=preco_spot, line_color="orange", annotation_text="SPOT", line_width=2)
        fig.add_vline(x=cwall, line_color="#00ffbb", line_dash="dash", annotation_text="Call Wall")
        fig.add_vline(x=pwall, line_color="#ff4444", line_dash="dash", annotation_text="Put Wall")
        fig.add_vline(x=gflip, line_color="gray", line_dash="dot", annotation_text="G-Flip")

        st.plotly_chart(fig, use_container_width=True)

        # --- PAINEL DE MÉTRICAS INFERIOR ---
        st.divider()
        col1, col2, col3, col4, col5 = st.columns(5)
        
        def fmt_val(v): return f"{v/1e6:.1f}M" if abs(v) >= 1e6 else f"{v:,.0f}"

        col1.metric("SPOT PRICE", f"${preco_spot:,.0f}")
        col2.metric("CALL WALL", f"${cwall:,.0f}")
        col3.metric("PUT WALL", f"${pwall:,.0f}")
        col4.metric("GAMMA FLIP", f"${gflip:,.0f}")
        col5.metric("PCR (OI)", f"{(df['put_oi'].sum()/df['call_oi'].sum()):.2f}")

        # STRING PARA TRADINGVIEW (SEM CORTES)
        st.subheader("📋 Pine Script Engine String")
        tv_string = f"CWALL,{cwall},PWALL,{pwall},GFLIP,{gflip},SPOT,{preco_spot:.0f}"
        st.code(tv_string, language="text")

    else:
        st.warning("Selecione ao menos uma expiração no menu lateral.")
else:
    st.error("Não foi possível carregar os dados da Deribit. Verifique a conexão.")
