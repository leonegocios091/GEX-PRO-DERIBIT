import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timezone

# 1. CONFIGURAÇÃO
st.set_page_config(page_title="GEX Master Engine Pro", layout="wide")
st_autorefresh(interval=30000, key="datarefresh")

def fmt_m_b(valor):
    abs_v = abs(valor)
    if abs_v >= 1e9: return f"{valor/1e9:.2f}B"
    if abs_v >= 1e6: return f"{valor/1e6:.2f}M"
    return f"{valor:,.0f}"

# 2. CARGA DE DADOS (Com tratamento de erro)
def carregar_deribit(ticker):
    url = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={ticker}&kind=option"
    try:
        data = requests.get(url, timeout=10).json()['result']
        df = pd.DataFrame(data)
        # Padronização de nomes
        df['strike'] = df['instrument_name'].str.split('-').str[2].astype(float)
        df['data_exp'] = df['instrument_name'].str.split('-').str[1]
        df['tipo'] = df['instrument_name'].str.split('-').str[3]
        return df
    except: return None

df_raw = carregar_deribit(st.sidebar.selectbox("Ativo", ["BTC", "ETH"]))

if df_raw is not None and not df_raw.empty:
    preco_spot = df_raw['estimated_delivery_price'].iloc[0]
    
    # 0DTE Logic
    exp_list = sorted(df_raw['data_exp'].unique())
    hoje_utc = datetime.now(timezone.utc).strftime("%d%b%y").upper()
    
    selecao_exp = st.sidebar.multiselect("Expirações", options=exp_list, default=[exp_list[0]],
        format_func=lambda x: f"⚡ {x} (0DTE)" if x == hoje_utc else x)

    if selecao_exp:
        df = df_raw[df_raw['data_exp'].isin(selecao_exp)].copy()
        
        # CÁLCULOS SEGUROS
        df['call_oi'] = df.apply(lambda x: x['open_interest'] if x['tipo'] == 'C' else 0, axis=1)
        df['put_oi'] = df.apply(lambda x: x['open_interest'] if x['tipo'] == 'P' else 0, axis=1)
        df['gex_net'] = df['call_oi'] - df['put_oi']
        df['gex_abs'] = df['call_oi'] + df['put_oi']
        df['dex_net'] = df.apply(lambda x: (x['open_interest'] * x['strike']) if x['tipo'] == 'C' else (-x['open_interest'] * x['strike']), axis=1)
        
        # Agrupamento (Removido 'bid' e 'ask' do agg, pois não eram usados na plotagem)
        resumo = df.groupby('strike').agg({
            'gex_net': 'sum', 'gex_abs': 'sum', 'dex_net': 'sum', 
            'call_oi': 'sum', 'put_oi': 'sum'
        }).reset_index()

        # Níveis
        cwall = resumo.loc[resumo['call_oi'].idxmax(), 'strike']
        pwall = resumo.loc[resumo['put_oi'].idxmax(), 'strike']
        gflip = resumo.iloc[(resumo['gex_net']).abs().argsort()[:1]]['strike'].values[0]

        # --- PLOTAGEM ---
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=resumo['strike'], y=resumo['gex_abs'], fill='tozeroy', mode='none', fillcolor='rgba(150, 150, 150, 0.15)', name='Liquidez Abs'))
        
        modo_visao = st.sidebar.radio("Métrica", ["Net GEX", "Net DEX"])
        y_plot = resumo['gex_net'] if modo_visao == "Net GEX" else resumo['dex_net']
        
        fig.add_trace(go.Bar(x=resumo['strike'], y=y_plot, marker_color=['#00ffbb' if v > 0 else '#ff4444' for v in y_plot]))

        fig.update_layout(template="plotly_dark", 
                          xaxis=dict(range=[preco_spot*0.9, preco_spot*1.1], dtick=500),
                          yaxis=dict(tickformat=".2s", exponentformat="SI"), height=500)

        for n, c, txt in [(preco_spot, "orange", "SPOT"), (cwall, "#00ffbb", "CWALL"), (pwall, "#ff4444", "PWALL"), (gflip, "gray", "GFLIP")]:
            fig.add_vline(x=n, line_color=c, line_dash="dash", annotation_text=txt)

        st.plotly_chart(fig, use_container_width=True)

        # PAINEL INFERIOR
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("SPOT", f"${preco_spot:,.0f}")
        m2.metric("CWALL", f"${cwall:,.0f}")
        m3.metric("PWALL", f"${pwall:,.0f}")
        m4.metric("G-FLIP", f"${gflip:,.0f}")
        
        st.code(f"CWALL,{cwall},PWALL,{pwall},GFLIP,{gflip},SPOT,{preco_spot:.0f}", language="text")
    else:
        st.warning("Selecione uma data na barra lateral.")
else:
    st.info("Carregando ou sem dados para esta data...")
