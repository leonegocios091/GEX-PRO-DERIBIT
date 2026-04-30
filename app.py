import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="GEX Pro - Deribit Analytics", layout="wide")

def carregar_e_limpar_dados(caminho):
    # Lendo o CSV exportado
    df = pd.read_csv(caminho)
    
    # Extração de Strike e Tipo (C/P)
    # Formato esperado: BTC-30APR26-69000-C
    df['strike'] = df['Instrument'].str.split('-').str[-2].astype(float)
    df['tipo'] = df['Instrument'].str.split('-').str[-1]
    
    # Função para limpar strings e converter em número
    def clean_num(valor):
        if isinstance(valor, str):
            valor = valor.replace('-', '0').replace('$', '').replace(',', '').strip()
        try:
            return float(valor)
        except:
            return 0.0

    # Limpando as colunas críticas
    colunas_limpar = ['Open', 'Gamma', 'Δ|Delta', 'Mark']
    for col in colunas_limpar:
        if col in df.columns:
            df[col] = df[col].apply(clean_num)
        else:
            df[col] = 0.0

    return df

# --- UI ---
st.title("📊 Deribit Options Analytics: BTC-30APR26")

try:
    # Lendo o arquivo local
    file_path = 'BTC-30APR26-export.csv'
    df_raw = carregar_e_limpar_dados(file_path)
    
    # Sidebar
    metrica = st.sidebar.selectbox("Métrica Principal", ["OI (Open Interest)", "GEX (Gamma)", "DEX (Delta)"])
    spot_manual = st.sidebar.number_input("Preço Spot (Referência)", value=float(df_raw['Mark'].max() * 1.1 if not df_raw.empty else 77000))
    raio_pct = st.sidebar.slider("Raio de Strikes (%)", 5, 50, 20)

    # Cálculos de Exposição baseados no CSV[cite: 1]
    # GEX = Gamma * Open * (Spot^2)
    df_raw['GEX_calc'] = df_raw['Gamma'] * df_raw['Open'] * (spot_manual**2)
    # DEX = Delta * Open * Spot
    df_raw['DEX_calc'] = df_raw['Δ|Delta'] * df_raw['Open'] * spot_manual
    
    # Seleção da métrica para o gráfico
    mapa_metrica = {
        "OI (Open Interest)": "Open",
        "GEX (Gamma)": "GEX_calc",
        "DEX (Delta)": "DEX_calc"
    }
    col_plot = mapa_metrica[metrica]

    # Filtro de Strikes
    margem = spot_manual * (raio_pct / 100)
    df_filt = df_raw[(df_raw['strike'] > spot_manual - margem) & 
                    (df_raw['strike'] < spot_manual + margem)].copy()

    # Preparação para Linhas e Áreas
    plot_data = df_filt.groupby(['strike', 'tipo'])[col_plot].sum().unstack().fillna(0)
    if 'C' not in plot_data.columns: plot_data['C'] = 0
    if 'P' not in plot_data.columns: plot_data['P'] = 0
    plot_data = plot_data.reset_index()

    # --- GRÁFICO ---
    fig = go.Figure()

    # Linha de Calls (Azul)
    fig.add_trace(go.Scatter(
        x=plot_data['strike'], y=plot_data['C'],
        mode='lines', name='Calls', fill='tozeroy',
        line=dict(color='#2E64FE', width=3)
    ))

    # Linha de Puts (Amarela)
    fig.add_trace(go.Scatter(
        x=plot_data['strike'], y=plot_data['P'],
        mode='lines', name='Puts', fill='tozeroy',
        line=dict(color='#F4D03F', width=3)
    ))

    # Linha do Spot
    fig.add_vline(x=spot_manual, line_dash="dash", line_color="red", 
                  annotation_text=f"SPOT: {spot_manual:,.0f}")

    fig.update_layout(
        template="plotly_dark", height=600,
        title=f"Distribuição de {metrica} por Strike",
        xaxis_title="Strike Price",
        yaxis_title="Volume / Exposição",
        hovermode="x unified"
    )

    st.plotly_chart(fig, use_container_width=True)

    # Resumo métrico
    c1, c2, c3 = st.columns(3)
    c1.metric("Total OI", f"{df_filt['Open'].sum():,.0f}")
    c2.metric("Net GEX", f"{df_filt['GEX_calc'].sum():,.2e}")
    c3.metric("Net DEX", f"{df_filt['DEX_calc'].sum():,.2e}")

except Exception as e:
    st.error(f"Erro ao processar arquivo: {e}")
