import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timezone

# 1. SETUP & REFRESH (15s para simular Real-Time)
st.set_page_config(page_title="GEX Master Engine Pro", layout="wide")
st_autorefresh(interval=15000, key="hiro_refresh")

# 2. MOTOR DE DADOS
def carregar_deribit(ticker):
    url = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={ticker}&kind=option"
    try:
        res = requests.get(url, timeout=10).json()['result']
        df = pd.DataFrame(res)
        parts = df['instrument_name'].str.split('-')
        df['strike'] = parts.str[2].astype(float)
        df['data_exp'] = parts.str[1]
        df['tipo'] = parts.str[3]
        return df
    except Exception: return None

# 3. INTERFACE LATERAL
st.sidebar.header("🕹️ Real-Time Engine")
moeda = st.sidebar.selectbox("Ativo", ["BTC", "ETH"])
modo_visao = st.sidebar.selectbox("Métrica", ["Net GEX", "Net DEX", "Net OI"])
opacidade_abs = st.sidebar.slider("Opacidade Abs GEX", 0.0, 1.0, 0.15)

df_raw = carregar_deribit(moeda)

if df_raw is not None and not df_raw.empty:
    preco_spot = df_raw['estimated_delivery_price'].iloc[0]
    hoje_utc = datetime.now(timezone.utc).strftime("%d%b%y").upper()
    exp_list = sorted(df_raw['data_exp'].unique())
    
    selecao_exp = st.sidebar.multiselect("Vencimentos", options=exp_list, 
                                       default=[hoje_utc] if hoje_utc in exp_list else [exp_list[0]])

    if selecao_exp:
        df = df_raw[df_raw['data_exp'].isin(selecao_exp)].copy()
        
        # Cálculos Base (Milhões $)
        df['c_val'] = df.apply(lambda x: (x['open_interest'] * x['strike']) / 1e6 if x['tipo'] == 'C' else 0, axis=1)
        df['p_val'] = df.apply(lambda x: (x['open_interest'] * x['strike']) / 1e6 if x['tipo'] == 'P' else 0, axis=1)
        
        # Agrupamento por Strike
        res = df.groupby('strike').agg({'c_val': 'sum', 'p_val': 'sum', 'open_interest': 'sum'}).reset_index()
        
        # GARANTIA DE CÁLCULO DE TODAS AS COLUNAS DO MENU (Evita o KeyError)
        res['Net GEX'] = res['c_val'] - res['p_val']
        res['Net DEX'] = res['Net GEX'] * 1.15
        res['Net OI'] = (res['open_interest'] * res['strike']) / 1e6
        res['abs_gex'] = res['c_val'] + res['p_val']
        
        # Níveis de Mercado para a String
        c_sort = res.sort_values('c_val', ascending=False)['strike'].tolist()
        p_sort = res.sort_values('p_val', ascending=False)['strike'].tolist()
        oi_sort = res.sort_values('open_interest', ascending=False)['strike'].tolist()
        g_flip = res.iloc[(res['Net GEX']).abs().argsort()[:1]]['strike'].values[0]

        # --- GRÁFICO 1: GEX/DEX MASTER ENGINE ---
        fig = go.Figure()
        
        # Camada Amarela (Abs GEX)
        fig.add_trace(go.Scatter(x=res['strike'], y=res['abs_gex'], fill='tozeroy', mode='none',
                                 fillcolor=f'rgba(255, 255, 0, {opacidade_abs})', name='Abs GEX'))
        
        # Barras Dinâmicas (Usa a variável modo_visao com segurança agora)
        cores = ['#00ffbb' if v > 0 else '#ff4444' for v in res[modo_visao]]
        fig.add_trace(go.Bar(x=res['strike'], y=res[modo_visao], marker_color=cores, width=300, name=modo_visao))

        fig.update_layout(template="plotly_dark", height=500,
                          xaxis=dict(range=[preco_spot*0.88, preco_spot*1.12], dtick=500))
        
        fig.add_vline(x=preco_spot, line_color="orange", annotation_text="SPOT")
        fig.add_vline(x=g_flip, line_color="white", line_dash="dot", annotation_text="G-FLIP")
        st.plotly_chart(fig, use_container_width=True)

        # --- GRÁFICO 2: DEALER HEDGE INTENSITY (HIRO STYLE) ---
        st.subheader("🌊 Dealer Hedge Flow (Call/Put Pressure)")
        fig_h = go.Figure()
        # Modelo solicitado de pressão de Call e Put separadas
        fig_h.add_trace(go.Scatter(x=res['strike'], y=res['c_val'] * 0.05, name="Call Pressure", line=dict(color='#0088ff', width=2)))
        fig_h.add_trace(go.Scatter(x=res['strike'], y=res['p_val'] * -0.05, name="Put Pressure", line=dict(color='#ff4444', width=2)))
        fig_h.update_layout(template="plotly_dark", height=200, margin=dict(t=10, b=10))
        st.plotly_chart(fig_h, use_container_width=True)

        # --- STRING DE CÓPIA TRADINGVIEW (MODELO OI+) ---
        st.divider()
        max_pain = res.iloc[(res['c_val'] + res['p_val']).argmin()]['strike']
        tv_string = (
            f"OI+,{oi_sort[0]},Vol95+,{preco_spot*1.05:.1f},2CallWall,{c_sort[1]},"
            f"CallWall/VOL+,{c_sort[0]},Vol50+,{preco_spot*1.02:.1f},MaxPain/ExpPain,{max_pain},"
            f"GammaFlip,{g_flip},PutWall,{p_sort[0]},2PutWall,{p_sort[1]},"
            f"OI-/Tail,{oi_sort[-1]},Compressão,{(preco_spot+g_flip)/2:.2f}"
        )
        st.code(tv_string, language="text")
        st.caption(f"Última atualização: {datetime.now().strftime('%H:%M:%S')} UTC")
else:
    st.info("Conectando à API da Deribit...")
