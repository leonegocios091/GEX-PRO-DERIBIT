import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import os

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Deribit Multi-File Monitor", layout="wide")

def carregar_todos_csvs():
    # Busca todos os arquivos .csv na pasta
    caminho_atual = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else "."
    arquivos = [f for f in os.listdir(caminho_atual) if f.endswith('.csv')]
    
    lista_dfs = []
    for arquivo in arquivos:
        try:
            df_temp = pd.read_csv(os.path.join(caminho_atual, arquivo))
            if 'Instrument' in df_temp.columns:
                lista_dfs.append(df_temp)
        except Exception as e:
            st.error(f"Erro ao ler {arquivo}: {e}")
            
    if not lista_dfs:
        return pd.DataFrame()
    
    df_total = pd.concat(lista_dfs, ignore_index=True)
    
    # Extração de dados do Instrumento
    partes = df_total['Instrument'].str.split('-', expand=True)
    df_total['expiracao'] = partes[1]
    df_total['strike'] = pd.to_numeric(partes[2], errors='coerce')
    df_total['tipo'] = partes[3]

    # Limpeza forçada de numéricos
    for col in ['Open', 'Gamma', 'Δ|Delta']:
        if col in df_total.columns:
            df_total[col] = pd.to_numeric(df_total[col].astype(str).str.replace('-', '0'), errors='coerce').fillna(0.0)
    
    return df_total

# --- INTERFACE ---
st.title("📊 Monitor de Opções - Múltiplos Arquivos")

df_raw = carregar_todos_csvs()

if df_raw.empty:
    st.error("❌ Nenhum arquivo CSV encontrado! Certifique-se de que os arquivos estão na mesma pasta do código.")
else:
    # Sidebar
    st.sidebar.header("Filtros")
    
    # Lista expirações únicas de TODOS os arquivos
    todas_exp = sorted(df_raw['expiracao'].dropna().unique())
    exp_selecionadas = st.sidebar.multiselect("Expirações", todas_exp, default=todas_exp)
    
    metrica = st.sidebar.radio("Métrica", ["OI", "GEX", "DEX"])
    spot_ref = st.sidebar.number_input("Preço Spot", value=77000.0)

    # Filtragem
    df_filt = df_raw[df_raw['expiracao'].isin(exp_selecionadas)].copy()

    # Cálculos Notional
    if metrica == "GEX":
        df_filt['valor'] = df_filt['Gamma'] * df_filt['Open'] * (spot_ref**2)
    elif metrica == "DEX":
        df_filt['valor'] = df_filt['Δ|Delta'] * df_filt['Open'] * spot_ref
    else:
        df_filt['valor'] = df_filt['Open']

    if not df_filt.empty and df_filt['valor'].sum() > 0:
        # Agrupamento para barras lado a lado
        pivot = df_filt.groupby(['strike', 'tipo'])['valor'].sum().unstack().fillna(0)
        for t in ['C', 'P']: 
            if t not in pivot.columns: pivot[t] = 0
        pivot = pivot.reset_index()

        # --- GRÁFICO ---
        fig = go.Figure()
        fig.add_trace(go.Bar(x=pivot['strike'], y=pivot['C'], name='Calls', marker_color='#2E64FE'))
        fig.add_trace(go.Bar(x=pivot['strike'], y=pivot['P'], name='Puts', marker_color='#F4D03F'))

        fig.add_vline(x=spot_ref, line_dash="dash", line_color="red", annotation_text="SPOT")

        fig.update_layout(
            template="plotly_dark", barmode='group',
            xaxis=dict(title="Strike Price", type='category'), # 'category' garante que as barras apareçam separadas
            yaxis=dict(title=metrica, tickformat=".2s"), # .2s abrevia números grandes (ex: 1.5M)
            height=600
        )

        st.plotly_chart(fig, use_container_width=True)
        st.success(f"Plotando {len(df_filt)} strikes de {len(exp_selecionadas)} arquivo(s).")
    else:
        st.warning(f"⚠️ Os dados para '{metrica}' estão zerados ou não existem para as expirações selecionadas. Tente mudar para 'OI'.")
        # Mostra o que foi lido para debug
        st.write("Dados brutos detectados:", df_filt[['Instrument', 'Open', 'Gamma']].head())
