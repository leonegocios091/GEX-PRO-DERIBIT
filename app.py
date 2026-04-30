import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Deribit Export Monitor", layout="wide")

def processar_csv_local(caminho_arquivo):
    # Lendo o arquivo exportado da Deribit
    df = pd.read_csv(caminho_arquivo)
    
    # Extração de Strike e Tipo (Ex: BTC-30APR26-69000-C)
    # O strike é o penúltimo elemento e o tipo (C/P) o último
    df['strike'] = df['Instrument'].str.split('-').str[-2].astype(float)
    df['tipo'] = df['Instrument'].str.split('-').str[-1]
    
    # Limpeza de dados (converte '-' ou nulos para 0)
    for col in ['Open', 'Gamma', 'Δ|Delta']:
        df[col] = pd.to_numeric(df[col].replace('-', '0'), errors='coerce').fillna(0.0)
    
    # Renomeando para facilitar o uso no código anterior
    df = df.rename(columns={'Open': 'OI', 'Δ|Delta': 'Delta'})
    
    return df

# --- INTERFACE ---
st.title("📈 Analisador de Exportação Deribit (BTC-30APR26)")

# Simulação de "Tempo Real": O usuário pode subir o arquivo mais recente ou 
# o script pode ler o arquivo salvo na mesma pasta do GitHub
try:
    file_path = 'BTC-30APR26-export.csv' # Nome exato do seu arquivo
    df_raw = processar_csv_local(file_path)
    
    # Menu de métricas
    metrica = st.sidebar.radio("Selecione a Métrica", ["OI", "Gamma", "Delta"])
    raio_pct = st.sidebar.slider("Zoom nos Strikes (%)", 5, 50, 20)
    
    # Preço de referência (Mark médio para estimar o Spot)
    preco_ref = df_raw['Mark'].mean() * 100000 # Ajuste manual se necessário
    # Como o CSV não tem o Spot exato, você pode definir um valor manual aqui:
    spot_manual = st.sidebar.number_input("Ajuste o Preço Spot Atual", value=77000.0)

    # Filtragem
    margem = spot_manual * (raio_pct / 100)
    df_filt = df_raw[(df_raw['strike'] > spot_manual - margem) & 
                    (df_raw['strike'] < spot_manual + margem)].copy()

    # Agrupamento para o gráfico de linhas
    plot_data = df_filt.groupby(['strike', 'tipo'])[metrica].sum().unstack().fillna(0)
    plot_data.columns = ['Calls', 'Puts']
    plot_data = plot_data.reset_index()

    # --- GRÁFICO DE LINHAS E ÁREAS ---
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=plot_data['strike'], y=plot_data['Calls'],
        mode='lines', name='Calls', fill='tozeroy',
        line=dict(color='#2E64FE', width=3)
    ))

    fig.add_trace(go.Scatter(
        x=plot_data['strike'], y=plot_data['Puts'],
        mode='lines', name='Puts', fill='tozeroy',
        line=dict(color='#F4D03F', width=3)
    ))

    fig.add_vline(x=spot_manual, line_dash="dash", line_color="red", annotation_text="SPOT")

    fig.update_layout(template="plotly_dark", height=600, hovermode="x unified",
                      title=f"Distribuição de {metrica} - BTC 30-APR-26")

    st.plotly_chart(fig, use_container_width=True)
    
    st.dataframe(df_filt[['Instrument', 'OI', 'Gamma', 'Delta']].head(10))

except Exception as e:
    st.error(f"Erro ao ler o arquivo CSV: {e}")
    st.info("Certifique-se de que o arquivo 'BTC-30APR26-export.csv' está na mesma pasta do seu app.py no GitHub.")
