import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import os

st.set_page_config(page_title="Debug Deribit", layout="wide")

# 1. FUNÇÃO DE CARREGAMENTO (VARRE TUDO)
def carregar_tudo():
    arquivos = [f for f in os.listdir('.') if f.endswith('.csv')]
    if not arquivos:
        return pd.DataFrame()
    
    lista = []
    for f in arquivos:
        df_temp = pd.read_csv(f)
        if 'Instrument' in df_temp.columns:
            lista.append(df_temp)
    
    df_total = pd.concat(lista, ignore_index=True)
    
    # Tratamento de Colunas
    partes = df_total['Instrument'].str.split('-', expand=True)
    df_total['expiracao'] = partes[1]
    df_total['strike'] = pd.to_numeric(partes[2], errors='coerce')
    df_total['tipo'] = partes[3]

    # Limpeza de hífens e conversão
    for col in ['Open', 'Gamma', 'Δ|Delta']:
        if col in df_total.columns:
            df_total[col] = pd.to_numeric(df_total[col].astype(str).str.replace('-', '0'), errors='coerce').fillna(0)
    
    return df_total

# 2. EXECUÇÃO
st.title("🚀 Verificador de Dados Deribit")

df = carregar_tudo()

if df.empty:
    st.error("Nenhum arquivo CSV detectado na pasta raiz.")
else:
    # Sidebar
    exps = sorted(df['expiracao'].unique())
    sel_exps = st.sidebar.multiselect("Expirações Detectadas", exps, default=exps)
    metrica = st.sidebar.selectbox("Métrica", ["Open", "Gamma", "Δ|Delta"])
    spot = st.sidebar.number_input("Spot", value=77000.0)

    # Filtro
    df_filt = df[df['expiracao'].isin(sel_exps)].copy()
    
    # Agrupamento para o Gráfico
    if not df_filt.empty:
        # Soma os valores por strike para consolidar as expirações
        resumo = df_filt.groupby(['strike', 'tipo'])[metrica].sum().unstack().fillna(0)
        
        # Garante colunas C e P
        for c in ['C', 'P']:
            if c not in resumo.columns: resumo[c] = 0
        resumo = resumo.reset_index()

        # 3. GRÁFICO
        fig = go.Figure()
        fig.add_trace(go.Bar(x=resumo['strike'], y=resumo['C'], name='Calls', marker_color='blue'))
        fig.add_trace(go.Bar(x=resumo['strike'], y=resumo['P'], name='Puts', marker_color='orange'))
        
        fig.update_layout(
            template="plotly_dark",
            barmode='group',
            xaxis={'type': 'category', 'title': 'Strike'},
            title=f"Visualizando: {metrica}"
        )
        
        st.plotly_chart(fig, use_container_width=True)

        # 4. TABELA DE CONFERÊNCIA (MUITO IMPORTANTE)
        st.write("### 🔍 Conferência de Dados (Se o gráfico sumir, olhe aqui):")
        st.dataframe(df_filt[['Instrument', 'expiracao', 'strike', 'tipo', metrica]].sort_values('strike'))
    else:
        st.warning("Selecione uma expiração no menu lateral.")

# Lista arquivos na tela para você conferir se o GitHub sincronizou
st.sidebar.write("Arquivos lidos:", [f for f in os.listdir('.') if f.endswith('.csv')])
