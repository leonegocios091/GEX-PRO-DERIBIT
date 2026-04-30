import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Deribit GEX", layout="wide")

def carregar_dados():
    # Carrega o arquivo e força a limpeza de cara
    df = pd.read_csv('BTC-30APR26-export.csv')
    
    # Extração robusta
    partes = df['Instrument'].str.split('-', expand=True)
    df['expiracao'] = partes[1]
    df['strike'] = pd.to_numeric(partes[2], errors='coerce')
    df['tipo'] = partes[3]

    # Converte '-' em 0 e garante que tudo seja número
    df['Open'] = pd.to_numeric(df['Open'].astype(str).str.replace('-', '0'), errors='coerce').fillna(0)
    df['Gamma'] = pd.to_numeric(df['Gamma'].astype(str).str.replace('-', '0'), errors='coerce').fillna(0)
    df['Delta'] = pd.to_numeric(df['Δ|Delta'].astype(str).str.replace('-', '0'), errors='coerce').fillna(0)
    
    return df

try:
    df_raw = carregar_dados()

    # --- BARRA LATERAL ---
    st.sidebar.header("Configurações")
    
    # Menu de Expirações
    lista_exp = sorted(df_raw['expiracao'].unique())
    escolha_exp = st.sidebar.multiselect("Datas de Expiração", lista_exp, default=lista_exp)
    
    metrica = st.sidebar.radio("Métrica", ["Open Interest (OI)", "GEX (Gamma)", "DEX (Delta)"])
    spot_ref = st.sidebar.number_input("Preço Spot Atual", value=77000.0)
    
    # --- PROCESSAMENTO ---
    df_filt = df_raw[df_raw['expiracao'].isin(escolha_exp)].copy()

    # Cálculos das métricas
    if metrica == "GEX (Gamma)":
        df_filt['valor'] = df_filt['Gamma'] * df_filt['Open'] * (spot_ref**2)
    elif metrica == "DEX (Delta)":
        df_filt['valor'] = df_filt['Delta'] * df_filt['Open'] * spot_ref
    else:
        df_filt['valor'] = df_filt['Open']

    # --- PLOTAGEM ---
    st.subheader(f"Distribuição de {metrica}")

    if not df_filt.empty:
        # Agrupar para garantir que Call e Put fiquem lado a lado
        pivot = df_filt.groupby(['strike', 'tipo'])['valor'].sum().unstack().fillna(0)
        
        # Garante que as colunas existam para o gráfico não dar erro
        if 'C' not in pivot.columns: pivot['C'] = 0
        if 'P' not in pivot.columns: pivot['P'] = 0
        pivot = pivot.reset_index()

        fig = go.Figure()
        
        # Barras Calls (Azul)
        fig.add_trace(go.Bar(
            x=pivot['strike'], y=pivot['C'], 
            name='Calls', marker_color='#2E64FE'
        ))
        
        # Barras Puts (Amarelo)
        fig.add_trace(go.Bar(
            x=pivot['strike'], y=pivot['P'], 
            name='Puts', marker_color='#F4D03F'
        ))

        fig.update_layout(
            template="plotly_dark",
            barmode='group',
            xaxis=dict(title="Strike", type='category'), # 'category' força a exibição de todas as barras
            yaxis=dict(title="Valor"),
            height=600
        )

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Nenhum dado encontrado para os filtros selecionados.")

except Exception as e:
    st.error(f"Erro ao processar: {e}")
