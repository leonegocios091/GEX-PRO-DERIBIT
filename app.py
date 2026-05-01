import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timezone

# 1. CONFIGURAÇÃO
st.set_page_config(page_title="GEX Master Engine Pro", layout="wide")
st_autorefresh(interval=30000, key="datarefresh")

# 2. HELPER DE FORMATAÇÃO
def fmt_m_b(valor):
    abs_v = abs(valor)
    if abs_v >= 1e9: return f"{valor/1e9:.2f}B"
    if abs_v >= 1e6: return f"{valor/1e6:.2f}M"
    return f"{valor:,.0f}"

# 3. SIDEBAR
st.sidebar.header("🕹️ Painel de Controle")
moeda = st.sidebar.selectbox("Ativo", ["BTC", "ETH"])
modo_tema = st.sidebar.radio("Tema", ["Dark", "Light"])
modo_visao = st.sidebar.radio("Métrica das Barras", ["Net GEX", "Net DEX (Delta)"])

# 4. CARGA DE DADOS
def carregar_deribit(ticker):
    url = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={ticker}&kind=option"
    try:
        data = requests.get(url, timeout=10).json()['result']
        df = pd.DataFrame(data)
        # Extração de componentes
        df['strike'] = df['instrument_name'].str.split('-').str[2].astype(float)
        df['data_exp'] = df['instrument_name'].str.split('-').str[1]
        df['tipo'] = df['instrument_name'].str.split('-').str[3]
        return df
    except: return None

df_raw = carregar_deribit(moeda)

if df_raw is not None:
    preco_spot = df_raw['estimated_delivery_price'].iloc[0]
    
    # --- LOGICA 0DTE ROBUSTA ---
    exp_list = sorted(df_raw['data_exp'].unique())
    hoje_utc = datetime.now(timezone.utc).strftime("%d%b%y").upper()
    
    # Se o 0DTE sumir por fuso, pegamos a data mais próxima da lista
    data_proxima = exp_list[0] 
    
    selecao_exp = st.sidebar.multiselect(
        "Expirações", options=exp_list, default=[data_proxima],
        format_func=lambda x: f"⚡ {x} (0DTE/Próx)" if x == data_proxima else x
    )

    if selecao_exp:
        df = df_raw[df_raw['data_exp'].isin(selecao_exp)].copy()
        
        # Cálculos de GEX/DEX/Premium
        df['call_oi'] = df.apply(lambda x: x['open_interest'] if x['tipo'] == 'C' else 0, axis=1)
        df['put_oi'] = df.apply(lambda x: x['open_interest'] if x['tipo'] == 'P' else 0, axis=1)
        df['gex_net'] = df['call_oi'] - df['put_oi']
        df['gex_abs'] = df['call_oi'] + df['put_oi']
        df['dex_net'] = df.apply(lambda x: (x['open_interest'] * x['strike']) if x['tipo'] == 'C' else (-x['open_interest'] * x['strike']), axis=1)
        
        # Agrupamento
        resumo = df.groupby('strike').agg({
            'gex_net': 'sum', 'gex_abs': 'sum', 'dex_net': 'sum', 
            'call_oi': 'sum', 'put_oi': 'sum', 'bid': 'sum', 'ask': 'sum'
        }).reset_index()

        # Níveis Principais e Secundários
        cwall = resumo.loc[resumo['call_oi'].idxmax(), 'strike']
        pwall = resumo.loc[resumo['put_oi'].idxmax(), 'strike']
        gflip = resumo.iloc[(resumo['gex_net']).abs().argsort()[:1]]['strike'].values[0]
        
        # AG1 e AG2 (Maiores concentrações de GEX Absoluto excluindo as Walls principais)
        concentracoes = resumo.sort_values(by='gex_abs', ascending=False)
        ag1 = concentracoes.iloc[0]['strike']
        ag2 = concentracoes.iloc[1]['strike']

        # Put/Call Ratio (OI)
        pcr = df['put_oi'].sum() / df['call_oi'].sum() if df['call_oi'].sum() > 0 else 0

        # --- PLOTAGEM PRINCIPAL ---
        fig = go.Figure()

        # Sombra de GEX Absoluto (Concentração de Liquidez)
        fig.add_trace(go.Scatter(
            x=resumo['strike'], y=resumo['gex_abs'], fill='tozeroy', 
            mode='none', fillcolor='rgba(150, 150, 150, 0.15)', name='GEX Absoluto'
        ))

        y_plot = resumo['gex_net'] if modo_visao == "Net GEX" else resumo['dex_net']
        colors = ['#00ffbb' if v > 0 else '#ff4444' for v in y_plot]

        fig.add_trace(go.Bar(x=resumo['strike'], y=y_plot, marker_color=colors, name=modo_visao))

        fig.update_layout(
            template="plotly_dark" if modo_tema == "Dark" else "plotly_white",
            xaxis=dict(title="Strike", range=[preco_spot*0.9, preco_spot*1.1], dtick=500, tickformat="d"),
            yaxis=dict(title=modo_visao, tickformat=".2s", exponentformat="SI"), # ESCALA M/B FIXA
            height=500, margin=dict(l=20, r=20, t=50, b=20)
        )

        # Linhas de Nível
        for n, c, txt in [(preco_spot, "orange", "SPOT"), (cwall, "#00ffbb", "CWALL"), 
                          (pwall, "#ff4444", "PWALL"), (gflip, "gray", "GFLIP")]:
            fig.add_vline(x=n, line_color=c, line_dash="dash", annotation_text=txt)

        st.plotly_chart(fig, use_container_width=True)

        # --- NOVO: GRÁFICO DE RATIO E PREMIUMS ---
        st.subheader("📊 Put/Call Premium & Ratio")
        fig_ratio = go.Figure()
        fig_ratio.add_trace(go.Scatter(x=resumo['strike'], y=resumo['call_oi'], name="Call OI", line=dict(color='#00ffbb')))
        fig_ratio.add_trace(go.Scatter(x=resumo['strike'], y=resumo['put_oi'], name="Put OI", line=dict(color='#ff4444')))
        fig_ratio.update_layout(height=300, template="plotly_dark" if modo_tema == "Dark" else "plotly_white",
                                xaxis=dict(dtick=1000), yaxis=dict(tickformat=".2s"))
        st.plotly_chart(fig_ratio, use_container_width=True)

        # --- PAINEL INFERIOR DE MÉTRICAS ---
        st.divider()
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("SPOT", f"${preco_spot:,.0f}")
        m2.metric("CALL WALL", f"${cwall:,.0f}")
        m3.metric("PUT WALL", f"${pwall:,.0f}")
        m4.metric("G-FLIP", f"${gflip:,.0f}")
        m5.metric("PCR (OI)", f"{pcr:.2f}")

        st.subheader("📌 Níveis Secundários (AG)")
        col_ag1, col_ag2 = st.columns(2)
        col_ag1.info(f"**AG1 (Maior GEX Abs):** {ag1:,.0f}")
        col_ag2.info(f"**AG2 (2º Maior GEX Abs):** {ag2:,.0f}")

        # String para TradingView
        st.subheader("📋 Pine Script String")
        tv_str = f"CWALL,{cwall},PWALL,{pwall},GFLIP,{gflip},SPOT,{preco_spot:.0f},AG1,{ag1},AG2,{ag2}"
        st.code(tv_str, language="text")

else:
    st.warning("Falha ao conectar com a Deribit. Verifique sua internet.")
