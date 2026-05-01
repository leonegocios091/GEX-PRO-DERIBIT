import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timezone

# 1. SETUP
st.set_page_config(page_title="GEX Master Engine Pro", layout="wide")
st_autorefresh(interval=30000, key="datarefresh")

# 2. MENU LATERAL: CUSTOMIZAÇÃO DE CORES E MÉTRICAS
st.sidebar.header("🎨 Customização e Filtros")
moeda = st.sidebar.selectbox("Ativo", ["BTC", "ETH"])
modo_visao = st.sidebar.selectbox("Métrica no Gráfico", ["Net GEX", "Net DEX", "Net OI"])

st.sidebar.divider()
st.sidebar.subheader("Cores das Barras")
cor_gex_pos = st.sidebar.color_picker("GEX Positivo", "#00ffbb")
cor_gex_neg = st.sidebar.color_picker("GEX Negativo", "#ff4444")
cor_oi = st.sidebar.color_picker("Barras de OI", "#000080") # Azul Marinho Default
cor_abs = st.sidebar.color_picker("Sombra GEX Abs", "#ffff00")
opacidade_s = st.sidebar.slider("Opacidade Sombra", 0.0, 1.0, 0.12)

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
        "Expirações", options=exp_list, 
        default=[hoje_utc] if hoje_utc in exp_list else [exp_list[0]]
    )

    if selecao_exp:
        df = df_raw[df_raw['data_exp'].isin(selecao_exp)].copy()
        
        # Cálculos de Exposição (Milhões $)
        df['c_val'] = df.apply(lambda x: (x['open_interest'] * x['strike']) / 1e6 if x['tipo'] == 'C' else 0, axis=1)
        df['p_val'] = df.apply(lambda x: (x['open_interest'] * x['strike']) / 1e6 if x['tipo'] == 'P' else 0, axis=1)
        
        res = df.groupby('strike').agg({'c_val': 'sum', 'p_val': 'sum', 'open_interest': 'sum'}).reset_index()
        res['Net GEX'] = res['c_val'] - res['p_val']
        res['GEX Abs'] = res['c_val'] + res['p_val']
        res['Net DEX'] = res['Net GEX'] * 1.2 # Proxy
        res['Net OI'] = (res['open_interest'] * res['strike']) / 1e6

        # --- NÍVEIS VANNA E CHARM (Strikes de Maior Atuação) ---
        # Identifica onde a variação de GEX é mais aguda (Proxy de sensibilidade)
        vanna_pos = res.loc[res['Net GEX'].idxmax(), 'strike']
        vanna_neg = res.loc[res['Net GEX'].idxmin(), 'strike']
        charm_strike = res.loc[res['GEX Abs'].idxmax(), 'strike']

        # Ranking Tradicional
        c_sort = res.sort_values('c_val', ascending=False)['strike'].tolist()
        p_sort = res.sort_values('p_val', ascending=False)['strike'].tolist()
        g_flip = res.iloc[(res['Net GEX']).abs().argsort()[:1]]['strike'].values[0]

        # --- GRÁFICO PRINCIPAL ---
        fig = go.Figure()
        
        # Sombra Abs Gamma
        fig.add_trace(go.Scatter(x=res['strike'], y=res['GEX Abs'], fill='tozeroy', mode='none', 
                                 fillcolor=cor_abs, opacity=opacidade_s, name='GEX Abs'))
        
        # Lógica de Cores das Barras
        if modo_visao == "Net OI":
            cores = cor_oi
        else:
            cores = [cor_gex_pos if v > 0 else cor_gex_neg for v in res[modo_visao]]

        fig.add_trace(go.Bar(x=res['strike'], y=res[modo_visao], marker_color=cores, name=modo_visao))

        # Ajuste de Eixo X (500 em 500) e Y (Milhões)
        fig.update_layout(template="plotly_dark", height=600,
                          yaxis=dict(title=f"{modo_visao} (M$)", ticksuffix="M"),
                          xaxis=dict(title="STRIKE", range=[preco_spot*0.88, preco_spot*1.12], dtick=500))
        
        # Níveis Visuais Incluindo Vanna/Charm
        niveis_plot = [
            (preco_spot, "orange", "SPOT"),
            (vanna_pos, "blue", "Vanna+"),
            (charm_strike, "purple", "Charm")
        ]
        for v, c, t in niveis_plot:
            fig.add_vline(x=v, line_color=c, line_dash="dot", annotation_text=t)

        st.plotly_chart(fig, use_container_width=True)

        # --- STRING EXPORT TRADINGVIEW (FORMATO SOLICITADO) ---
        st.subheader("📋 Pine Script Engine String")
        tv_string = (
            f"CallWall/VOL+,{c_sort[0]},2CallWall,{c_sort[1]},"
            f"Vanna+,{vanna_pos},Vanna-,{vanna_neg},Charm,{charm_strike},"
            f"GammaFlip,{g_flip},PutWall,{p_sort[0]},2PutWall,{p_sort[1]},"
            f"Vol50+,{preco_spot*1.02:.0f},Vol95+,{preco_spot*1.05:.0f}"
        )
        st.code(tv_string, language="text")

        # --- MÉTRICAS RÁPIDAS ---
        st.divider()
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Vanna Strike", f"${vanna_pos:,.0f}")
        m2.metric("Charm Strike", f"${charm_strike:,.0f}")
        m3.metric("G-Flip", f"${g_flip:,.0f}")
        m4.metric("Market Bias", "BULLISH" if res['Net GEX'].sum() > 0 else "BEARISH")

else:
    st.info("Aguardando dados da Deribit...")
