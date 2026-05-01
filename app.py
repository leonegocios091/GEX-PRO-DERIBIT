import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timezone

# 1. SETUP
st.set_page_config(page_title="GEX Master Engine Pro", layout="wide")
st_autorefresh(interval=30000, key="datarefresh")

# 2. MOTOR DE DADOS (DERIBIT)
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

df_raw = carregar_deribit(st.sidebar.selectbox("Ativo", ["BTC", "ETH"]))

if df_raw is not None and not df_raw.empty:
    preco_spot = df_raw['estimated_delivery_price'].iloc[0]
    hoje_utc = datetime.now(timezone.utc).strftime("%d%b%y").upper()
    exp_list = sorted(df_raw['data_exp'].unique())
    
    # Garantir que 30APR26 seja selecionada se disponível
    selecao_exp = st.sidebar.multiselect(
        "Expirações", options=exp_list, 
        default=[hoje_utc] if hoje_utc in exp_list else [exp_list[0]],
        format_func=lambda x: f"⚡ {x} (0DTE/LIVE)" if x == hoje_utc else x
    )

    if selecao_exp:
        df = df_raw[df_raw['data_exp'].isin(selecao_exp)].copy()
        
        # Cálculos Financeiros (Escala M)
        df['c_val'] = df.apply(lambda x: (x['open_interest'] * x['strike']) / 1e6 if x['tipo'] == 'C' else 0, axis=1)
        df['p_val'] = df.apply(lambda x: (x['open_interest'] * x['strike']) / 1e6 if x['tipo'] == 'P' else 0, axis=1)
        
        res = df.groupby('strike').agg({'c_val': 'sum', 'p_val': 'sum'}).reset_index()
        res['Net GEX'] = res['c_val'] - res['p_val']
        res['GEX Abs'] = res['c_val'] + res['p_val']

        # --- RANKING PARA TRADINGVIEW ---
        c_sort = res.sort_values('c_val', ascending=False)['strike'].tolist()
        p_sort = res.sort_values('p_val', ascending=False)['strike'].tolist()
        g_flip = res.iloc[(res['Net GEX']).abs().argsort()[:1]]['strike'].values[0]

        # --- GRÁFICO PRINCIPAL (Ajuste Visual de Barras) ---
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=res['strike'], y=res['GEX Abs'], fill='tozeroy', mode='none', 
                                 fillcolor='rgba(255,255,0,0.12)', name='GEX Abs'))
        
        # Barras Net GEX agora proporcionais ao Abs
        fig.add_trace(go.Bar(x=res['strike'], y=res['Net GEX'], 
                             marker_color=['#00ffbb' if v > 0 else '#ff4444' for v in res['Net GEX']], 
                             name='Net GEX'))

        fig.update_layout(template="plotly_dark", height=600,
                          yaxis=dict(title="Liquidez (Milhões $)", ticksuffix="M"),
                          xaxis=dict(range=[preco_spot*0.9, preco_spot*1.1], dtick=500))
        
        # Linhas Principais
        fig.add_vline(x=preco_spot, line_color="orange", annotation_text="SPOT")
        fig.add_vline(x=c_sort[0], line_color="#00ffbb", line_dash="dash", annotation_text="CallWall")
        fig.add_vline(x=p_sort[0], line_color="#ff4444", line_dash="dash", annotation_text="PutWall")

        st.plotly_chart(fig, use_container_width=True)

        # --- EXPORTAÇÃO FORMATADA (ESTILO EXEMPLO) ---
        st.subheader("📋 Pine Script Master Engine String")
        
        # Formatação: Label,Valor,Label,Valor...
        tv_string = (
            f"CallWall/VOL+,{c_sort[0]},2CallWall,{c_sort[1]},3CallWall,{c_sort[2]},4CallWall,{c_sort[3]},"
            f"PutWall,{p_sort[0]},2PutWall,{p_sort[1]},3PutWall,{p_sort[2]},4PutWall,{p_sort[3]},"
            f"GammaFlip,{g_flip},Vol50+,{preco_spot*1.02:.2f},Vol95+,{preco_spot*1.05:.2f},"
            f"Vanna,{res['Net GEX'].sum()*0.01:.2f},Charm,{res['Net GEX'].mean():.2f}"
        )
        st.code(tv_string, language="text")

        # --- SUBGRÁFICO DEALER HEDGE ---
        st.subheader("🌊 Dealer Hedge Flow (Buy/Sell Pressure)")
        fig_h = go.Figure()
        fig_h.add_trace(go.Scatter(x=res['strike'], y=res['c_val'] * 0.05, name="Hedge Call (Blue)", line=dict(color='#0088ff', width=2)))
        fig_h.add_trace(go.Scatter(x=res['strike'], y=res['p_val'] * -0.05, name="Hedge Put (Red)", line=dict(color='#ff0000', width=2)))
        fig_h.update_layout(template="plotly_dark", height=250, yaxis=dict(ticksuffix="M"))
        st.plotly_chart(fig_h, use_container_width=True)

else:
    st.info("Conectando à API Deribit...")
