import streamlit as st
import pandas as pd
import plotly.graph_objects as go

st.set_page_config(page_title="GEX Pro - Deribit", layout="wide")

def carregar_dados():
    df = pd.read_csv('BTC-30APR26-export.csv')
    
    # Limpeza robusta: converte '-' em 0 e garante float
    for col in ['Open', 'Gamma', 'Δ|Delta']:
        df[col] = pd.to_numeric(df[col].astype(str).str.replace('-', '0'), errors='coerce').fillna(0)
    
    df['strike'] = df['Instrument'].str.split('-').str[-2].astype(float)
    df['tipo'] = df['Instrument'].str.split('-').str[-1]
    return df

try:
    df = carregar_dados()
    spot_ref = 77000.0 # Ajuste conforme o mercado real
    
    st.title("📊 Análise de Opções BTC-30APR26")
    
    # Escolha de Métrica para evitar gráfico vazio
    metrica = st.selectbox("Selecione a Métrica", ["Open Interest (OI)", "GEX (Gamma)", "DEX (Delta)"])
    
    if metrica == "GEX (Gamma)":
        df['plot_val'] = df['Gamma'] * df['Open'] * (spot_ref**2)
        if df['Gamma'].sum() == 0:
            st.warning("⚠️ Atenção: Os valores de Gamma no CSV estão zerados. As barras de GEX não aparecerão.")
    elif metrica == "DEX (Delta)":
        df['plot_val'] = df['Δ|Delta'] * df['Open'] * spot_ref
    else:
        df['plot_val'] = df['Open']

    # Filtro de Strikes próximos ao Spot
    df_filt = df[(df['strike'] > spot_ref * 0.8) & (df['strike'] < spot_ref * 1.2)]
    
    # Gráfico de Barras Lado a Lado
    fig = go.Figure()
    for t, cor, nome in [('C', '#2E64FE', 'Calls'), ('P', '#F4D03F', 'Puts')]:
        d = df_filt[df_filt['tipo'] == t]
        fig.add_trace(go.Bar(x=d['strike'], y=d['plot_val'], name=nome, marker_color=cor))

    fig.update_layout(template="plotly_dark", barmode='group', title=f"Distribuição de {metrica}")
    st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.error(f"Erro ao carregar CSV: {e}")
