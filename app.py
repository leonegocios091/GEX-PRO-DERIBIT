import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import os

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Deribit Multi-File GEX", layout="wide")

def carregar_e_consolidar_csvs():
    # Lista todos os arquivos da pasta que terminam com .csv
    arquivos = [f for f in os.listdir('.') if f.endswith('.csv')]
    
    lista_dfs = []
    
    for arquivo in arquivos:
        try:
            df_temp = pd.read_csv(arquivo)
            # Verifica se a coluna 'Instrument' existe para evitar erros com arquivos errados
            if 'Instrument' in df_temp.columns:
                lista_dfs.append(df_temp)
        except Exception as e:
            st.error(f"Erro ao ler o arquivo {arquivo}: {e}")
            
    if not lista_dfs:
        return pd.DataFrame()
    
    # Junta todos os arquivos em um só
    df_total = pd.concat(lista_dfs, ignore_index=True)
    
    # Extração de dados (BTC-DATA-STRIKE-TIPO)
    partes = df_total['Instrument'].str.split('-', expand=True)
    df_total['expiracao'] = partes[1]
    df_total['strike'] = pd.to_numeric(partes[2], errors='coerce')
    df_total['tipo'] = partes[3]

    # Limpeza de valores
    for col in ['Open', 'Gamma', 'Δ|Delta']:
        if col in df_total.columns:
            df_total[col] = pd.to_numeric(df_total[col].astype(str).str.replace('-', '0'), errors='coerce').fillna(0.0)
    
    return df_total

# --- EXECUÇÃO ---
try:
    df_raw = carregar_e_consolidar_csvs()

    if df_raw.empty:
        st.warning("Nenhum arquivo CSV válido foi encontrado na pasta.")
    else:
        st.title("📊 GEX & OI Analytics - Consolidado")

        # --- MENU LATERAL ---
        st.sidebar.header("Filtros")
        
        # Detecta todas as datas de todos os arquivos carregados
        todas_exp = sorted(df_raw['expiracao'].dropna().unique())
        escolha_exp = st.sidebar.multiselect("Selecione as Expirações", todas_exp, default=todas_exp)
        
        metrica = st.sidebar.radio("Métrica", ["OI", "GEX", "DEX"])
        spot_ref = st.sidebar.number_input("Preço Spot", value=77000.0)
        raio_pct = st.sidebar.slider("Raio de Strikes (%)", 5, 100, 25)

        # --- FILTRAGEM ---
        df_filt = df_raw[df_raw['expiracao'].isin(escolha_exp)].copy()
        
        # Filtro de Raio
        margem = spot_ref * (raio_pct / 100)
        df_filt = df_filt[(df_filt['strike'] > spot_ref - margem) & (df_filt['strike'] < spot_ref + margem)]

        # Cálculos
        if metrica == "GEX":
            df_filt['valor'] = df_filt['Gamma'] * df_filt['Open'] * (spot_ref**2)
        elif metrica == "DEX":
            df_filt['valor'] = df_filt['Δ|Delta'] * df_filt['Open'] * spot_ref
        else:
            df_filt['valor'] = df_filt['Open']

        # --- GRÁFICO ---
        if not df_filt.empty:
            # Agrupa por strike somando todas as expirações selecionadas
            pivot = df_filt.groupby(['strike', 'tipo'])['valor'].sum().unstack().fillna(0)
            
            for t in ['C', 'P']:
                if t not in pivot.columns: pivot[t] = 0
            pivot = pivot.reset_index()

            fig = go.Figure()
            fig.add_trace(go.Bar(x=pivot['strike'], y=pivot['C'], name='Calls', marker_color='#2E64FE'))
            fig.add_trace(go.Bar(x=pivot['strike'], y=pivot['P'], name='Puts', marker_color='#F4D03F'))

            fig.add_vline(x=spot_ref, line_dash="dash", line_color="red", annotation_text="SPOT")

            fig.update_layout(
                template="plotly_dark", barmode='group',
                xaxis=dict(title="Strike", type='category'),
                yaxis=dict(title=metrica), height=600
            )

            st.plotly_chart(fig, use_container_width=True)
            st.success(f"Dados consolidados de {len(escolha_exp)} expiração(ões).")
        else:
            st.warning("Nenhum dado para exibir. Verifique os filtros ou o Preço Spot.")

except Exception as e:
    st.error(f"Erro Geral: {e}")
