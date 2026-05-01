import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timezone

# 1. SETUP
st.set_page_config(page_title="GEX Master Engine Pro", layout="wide")
st_autorefresh(interval=30000, key="datarefresh")

# 2. MENU LATERAL
st.sidebar.header("🎨 Painel de Visualização")
moeda = st.sidebar.selectbox("Ativo", ["BTC", "ETH"])
modo_visao = st.sidebar.selectbox("Métrica Principal", ["Net GEX", "Net DEX", "Net OI"])

st.sidebar.divider()
cor_gex_pos = st.sidebar.color_picker("GEX Positivo", "#00ffbb")
cor_gex_neg = st.sidebar.color_picker("GEX Negativo", "#ff4444")
cor_oi = st.sidebar.color_picker("Barras Net OI", "#000080")
cor_abs = st.sidebar.color_picker("Sombra GEX Absoluto", "#ffff00")
opacidade_abs = st.sidebar.slider("Opacidade da Sombra", 0.0, 1.0, 0.12)

# 3. MOTOR DE DADOS (DERIBIT)
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
        
        # Cálculos Financeiros (Milhões $)
        df['c_val'] = df.apply(lambda x: (x['open_interest'] * x['strike']) / 1e6 if x['tipo'] == 'C' else 0, axis=1)
        df['p_val'] = df.apply(lambda x: (x['open_interest'] * x['strike']) / 1e6 if x['tipo'] == 'P' else 0, axis=1)
        
        resumo = df.groupby('strike').agg({'c_val': 'sum', 'p_val': 'sum', 'open_interest': 'sum'}).reset_index()
        resumo['Net GEX'] = resumo['c_val'] - resumo['p_val']
        resumo['gex_abs'] = resumo['c_val'] + resumo['p_val']
        resumo['Net DEX'] = resumo['Net GEX'] * 1.15
        resumo['Net OI'] = (resumo['open_interest'] * resumo['strike']) / 1e6

        # --- CÁLCULO DE NÍVEIS CHAVE ---
        c_sort = resumo.sort_values('c_val', ascending=False)['strike'].tolist()
        p_sort = resumo.sort_values('p_val', ascending=False)['strike'].tolist()
        
        # Gamma Flip: Strike onde o Net GEX cruza o zero ou é o mais próximo de zero
        gamma_flip = resumo.iloc[(resumo['Net GEX']).abs().argsort()[:1]]['strike'].values[0]

        # --- CONSTRUÇÃO DO GRÁFICO (ORDEM DE CAMADA) ---
        fig = go.Figure()
        
        # 1. BASE: Sombra de GEX Absoluto (Fica no fundo)
        fig.add_trace(go.Scatter(
            x=resumo['strike'], y=resumo['gex_abs'], 
            fill='tozeroy', mode='none', 
            fillcolor=cor_abs, 
            opacity=opacidade_abs,
            name='GEX Absoluto'
        ))
        
        # 2. TOPO: Barras Net GEX/DEX/OI (Ficam na frente)
        if modo_visao == "Net OI":
            cores_barras = cor_oi
        else:
            cores_barras = [cor_gex_pos if v > 0 else cor_gex_neg for v in resumo[modo_visao]]

        fig.add_trace(go.Bar(
            x=resumo['strike'], y=resumo[modo_visao], 
            marker_color=cores_barras, 
            name=modo_visao
        ))

        # Configurações de Eixos
        fig.update_layout(
            template="plotly_dark", height=600,
            yaxis=dict(title="Financeiro (M$)", ticksuffix="M", gridcolor='rgba(255,255,255,0.05)'),
            xaxis=dict(title="STRIKE", range=[preco_spot*0.88, preco_spot*1.12], dtick=500),
            barmode='overlay'
        )
        
        # --- LINHAS DE NÍVEIS ---
        fig.add_vline(x=preco_spot, line_color="orange", annotation_text="SPOT", line_width=2)
        fig.add_vline(x=c_sort[0], line_color="#00ffbb", line_dash="dash", annotation_text="CWALL")
        fig.add_vline(x=p_sort[0], line_color="#ff4444", line_dash="dash", annotation_text="PWALL")
        fig.add_vline(x=gamma_flip, line_color="white", line_dash="dot", annotation_text="G-FLIP")

        st.plotly_chart(fig, use_container_width=True)

        # --- GRÁFICO DEALER HEDGE FLOW ---
        st.subheader("🌊 Dealer Hedge Flow (Pressure)")
        fig_h = go.Figure()
        fig_h.add_trace(go.Scatter(x=resumo['strike'], y=resumo['c_val'] * 0.05, name="Call Hedge (Blue)", line=dict(color='#0088ff', width=2)))
        fig_h.add_trace(go.Scatter(x=resumo['strike'], y=resumo['p_val'] * -0.05, name="Put Hedge (Red)", line=dict(color='#ff0000', width=2)))
        fig_h.update_layout(template="plotly_dark", height=250, yaxis=dict(ticksuffix="M"))
        st.plotly_chart(fig_h, use_container_width=True)

        # --- EXPORTAÇÃO TRADINGVIEW ---
        st.subheader("📋 Pine Script Master Engine String")
        tv_string = (
            f"CallWall/VOL+,{c_sort[0]},2CallWall,{c_sort[1]},3CallWall,{c_sort[2]},"
            f"PutWall,{p_sort[0]},2PutWall,{p_sort[1]},3PutWall,{p_sort[2]},"
            f"GammaFlip,{gamma_flip},Vol50+,{preco_spot*1.02:.0f},Vol95+,{preco_spot*1.05:.0f}"
        )
        st.code(tv_string, language="text")

else:
    st.warning("Conectando aos dados da Deribit...")
