import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# 1. CONFIGURAÇÃO E AUTO-REFRESH
st.set_page_config(page_title="GEX Master Engine", layout="wide")
st_autorefresh(interval=30000, key="datarefresh")

# Estilo para manter o padrão Dark do Quant App
st.markdown("<style>.main { background-color: #111727; }</style>", unsafe_allow_html=True)

# 2. FUNÇÃO DE DADOS
def carregar_dados(moeda):
    url = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={moeda}&kind=option"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return pd.DataFrame(response.json()['result'])
    except Exception as e:
        st.error(f"Erro: {e}")
    return None

# 3. INTERFACE LATERAL
st.sidebar.header("⚙️ Painel de Controle")
moeda = st.sidebar.selectbox("Ativo", ["BTC", "ETH"])
modo_visao = st.sidebar.radio("Visualização", ["Net GEX", "Open Interest (OI)", "DEX (Delta Exp)"])

# 4. PROCESSAMENTO
df_raw = carregar_dados(moeda)

if df_raw is not None and not df_raw.empty:
    # Extração de dados
    df_raw['strike'] = df_raw['instrument_name'].str.split('-').str[2].astype(float)
    df_raw['tipo'] = df_raw['instrument_name'].str.split('-').str[3]
    df_raw['data_exp'] = df_raw['instrument_name'].str.split('-').str[1]
    
    # Filtro de Expiração
    expiracoes = sorted(df_raw['data_exp'].unique())
    selecao = st.sidebar.multiselect("Expirações", expiracoes, default=expiracoes[0])
    
    if selecao:
        df = df_raw[df_raw['data_exp'].isin(selecao)].copy()
        preco_spot = df_raw['estimated_delivery_price'].iloc[0]

        # Cálculos de GEX e DEX (Simplificados para Proxy)
        df['gex'] = df.apply(lambda x: x['open_interest'] if x['tipo'] == 'C' else -x['open_interest'], axis=1)
        df['dex'] = df.apply(lambda x: x['open_interest'] * (x['strike']/preco_spot) if x['tipo'] == 'C' else -x['open_interest'] * (x['strike']/preco_spot), axis=1)

        # Agrupamentos
        gex_strike = df.groupby('strike')['gex'].sum().reset_index()
        oi_strike = df.groupby('strike')['open_interest'].sum().reset_index()
        dex_strike = df.groupby('strike')['dex'].sum().reset_index()

        # --- CÁLCULO DE NÍVEIS CHAVE ---
        call_wall = df[df['tipo'] == 'C'].groupby('strike')['open_interest'].sum().idxmax()
        put_wall = df[df['tipo'] == 'P'].groupby('strike')['open_interest'].sum().idxmax()
        
        # Gamma Flip (Onde o GEX cruza o zero ou o menor valor absoluto)
        gamma_flip = gex_strike.iloc[(gex_strike['gex']).abs().argsort()[:1]]['strike'].values[0]

        # --- GRÁFICO ---
        fig = go.Figure()

        # Alternar dados baseados no botão selecionado
        if modo_visao == "Net GEX":
            y_data = gex_strike['gex']
            color_map = ['#00ffbb' if v > 0 else '#ff4444' for v in y_data]
            label = "Net GEX"
        elif modo_visao == "DEX (Delta Exp)":
            y_data = dex_strike['dex']
            color_map = ['#00d4ff' if v > 0 else '#ff9900' for v in y_data]
            label = "Net DEX"
        else:
            y_data = oi_strike['open_interest']
            color_map = ['#6450fa'] * len(y_data)
            label = "Open Interest"

        # Sombra Absoluta ao fundo
        fig.add_trace(go.Scatter(x=oi_strike['strike'], y=oi_strike['open_interest'], fill='tozeroy', mode='none', fillcolor='rgba(100, 80, 250, 0.1)', name='Liquidez'))
        
        # Barras Principais
        fig.add_trace(go.Bar(x=gex_strike['strike'], y=y_data, marker_color=color_map, name=label))

        # Linhas de Níveis
        fig.add_vline(x=preco_spot, line_color="orange", line_dash="solid", annotation_text="SPOT")
        fig.add_vline(x=call_wall, line_color="#00ffbb", line_dash="dot", annotation_text="Call Wall")
        fig.add_vline(x=put_wall, line_color="#ff4444", line_dash="dot", annotation_text="Put Wall")
        fig.add_vline(x=gamma_flip, line_color="white", line_dash="dash", annotation_text="Gamma Flip")

        fig.update_layout(
            template="plotly_dark", paper_bgcolor="#111727", plot_bgcolor="#111727",
            xaxis=dict(range=[preco_spot * 0.85, preco_spot * 1.15], title="STRIKE"),
            title=f"{moeda} | {modo_visao} Analysis"
        )

        st.plotly_chart(fig, use_container_width=True)

        # Painel de Níveis Chave (Dashboard Inferior)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Spot Price", f"${preco_spot:,.2f}")
        c2.metric("Gamma Flip", f"${gamma_flip:,.0f}")
        c3.metric("Call Wall", f"${call_wall:,.0f}")
        c4.metric("Put Wall", f"${put_wall:,.0f}")

else:
    st.info("Conectando aos servidores da Deribit...")
