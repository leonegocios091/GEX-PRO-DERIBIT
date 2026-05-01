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
st.sidebar.header("🎨 Ajustes de Camada")
moeda = st.sidebar.selectbox("Ativo", ["BTC", "ETH"])
modo_visao = st.sidebar.selectbox("Métrica Principal", ["Net GEX", "Net DEX", "Net OI"])

st.sidebar.divider()
cor_gex_pos = st.sidebar.color_picker("GEX Positivo", "#00ffbb")
cor_gex_neg = st.sidebar.color_picker("GEX Negativo", "#ff4444")
cor_abs = st.sidebar.color_picker("Sombra GEX Abs", "#ffff00")
opacidade_abs = st.sidebar.slider("Opacidade GEX Abs (Fundo)", 0.0, 1.0, 0.10)

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
    
    selecao_exp = st.sidebar.multiselect("Expirações", options=exp_list, 
                                       default=[hoje_utc] if hoje_utc in exp_list else [exp_list[0]])

    if selecao_exp:
        df = df_raw[df_raw['data_exp'].isin(selecao_exp)].copy()
        df['c_val'] = df.apply(lambda x: (x['open_interest'] * x['strike']) / 1e6 if x['tipo'] == 'C' else 0, axis=1)
        df['p_val'] = df.apply(lambda x: (x['open_interest'] * x['strike']) / 1e6 if x['tipo'] == 'P' else 0, axis=1)
        
        res = df.groupby('strike').agg({'c_val': 'sum', 'p_val': 'sum'}).reset_index()
        res['Net GEX'] = res['c_val'] - res['p_val']
        res['GEX Abs'] = res['c_val'] + res['p_val']
        res['Net DEX'] = res['Net GEX'] * 1.1
        res['Net OI'] = (res['c_val'] + res['p_val']) / 2

        # --- NÍVEIS ---
        c_sort = res.sort_values('c_val', ascending=False)['strike'].tolist()
        p_sort = res.sort_values('p_val', ascending=False)['strike'].tolist()
        g_flip = res.iloc[(res['Net GEX']).abs().argsort()[:1]]['strike'].values[0]

        # --- GRÁFICO PRINCIPAL (ORDEm DE CAMADAS) ---
        fig = go.Figure()
        
        # 1. CAMADA DE FUNDO: GEX Abs (Scatter)
        fig.add_trace(go.Scatter(
            x=res['strike'], 
            y=res['GEX Abs'], 
            fill='tozeroy', 
            mode='lines', # 'lines' com width 0 evita que a linha cubra as barras
            line=dict(width=0),
            fillcolor=cor_abs,
            opacity=opacidade_abs,
            name='GEX Abs (Liquidez)',
            hoverinfo='skip'
        ))
        
        # 2. CAMADA DA FRENTE: Barras (Net GEX/DEX/OI)
        cores_barras = [cor_gex_pos if v > 0 else cor_gex_neg for v in res[modo_visao]]
        fig.add_trace(go.Bar(
            x=res['strike'], 
            y=res[modo_visao], 
            marker=dict(color=cores_barras, line=dict(width=0)),
            name=modo_visao
        ))

        fig.update_layout(
            template="plotly_dark", 
            height=600,
            barmode='overlay', # Garante que as barras não tentem se agrupar lateralmente
            yaxis=dict(title=f"{modo_visao} (M$)", ticksuffix="M", gridcolor='rgba(255,255,255,0.05)'),
            xaxis=dict(title="STRIKE", range=[preco_spot*0.9, preco_spot*1.1], dtick=500),
            showlegend=True
        )
        
        # Linhas de Referência
        fig.add_vline(x=preco_spot, line_color="orange", annotation_text="SPOT")
        fig.add_vline(x=c_sort[0], line_color="#00ffbb", line_dash="dash", annotation_text="CWALL")
        fig.add_vline(x=p_sort[0], line_color="#ff4444", line_dash="dash", annotation_text="PWALL")

        st.plotly_chart(fig, use_container_width=True)

        # --- GRÁFICO DE HEDGE FLOW ---
        st.subheader("🌊 Dealer Hedge Flow (Pressure)")
        fig_h = go.Figure()
        fig_h.add_trace(go.Scatter(x=res['strike'], y=res['c_val'] * 0.05, name="Buy Pressure (Calls)", line=dict(color='#0088ff', width=2)))
        fig_h.add_trace(go.Scatter(x=res['strike'], y=res['p_val'] * -0.05, name="Sell Pressure (Puts)", line=dict(color='#ff0000', width=2)))
        fig_h.update_layout(template="plotly_dark", height=250, yaxis=dict(ticksuffix="M"))
        st.plotly_chart(fig_h, use_container_width=True)

        # --- STRING TRADINGVIEW ---
        st.subheader("📋 Pine Script Engine String")
        tv_string = (
            f"CallWall/VOL+,{c_sort[0]},2CallWall,{c_sort[1]},3CallWall,{c_sort[2]},"
            f"PutWall,{p_sort[0]},2PutWall,{p_sort[1]},3PutWall,{p_sort[2]},"
            f"GammaFlip,{g_flip},Vol50+,{preco_spot*1.02:.0f},Vol95+,{preco_spot*1.05:.0f}"
        )
        st.code(tv_string, language="text")

else:
    st.info("Aguardando dados da API Deribit...")
