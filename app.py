import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Deribit GEX/DEX Dashboard", layout="wide")

def buscar_dados_deribit(moeda):
    # 1. Preço Spot
    url_preco = f"https://www.deribit.com/api/v2/public/get_index_price?index_name={moeda.lower()}_usd"
    resposta_preco = requests.get(url_preco).json()
    preco_spot = float(resposta_preco['result']['index_price'])
    
    # 2. Resumo de Opções
    url_summary = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={moeda}&kind=option"
    resposta_summary = requests.get(url_summary).json()
    dados = resposta_summary.get('result', [])
    
    # Criamos o DataFrame garantindo que não seja um objeto nulo
    df = pd.DataFrame(dados)
    
    if df.empty:
        return df, preco_spot
    
    # 3. Extração e Limpeza Técnica
    df['strike'] = df['instrument_name'].str.split('-').str[2].astype(float)
    df['tipo'] = df['instrument_name'].str.split('-').str[3]
    
    # --- CORREÇÃO DO ERRO 'int' object has no attribute 'fillna' ---
    # Forçamos a conversão para numérico ANTES de qualquer preenchimento
    colunas_alvo = ['gamma', 'delta', 'open_interest']
    for col in colunas_alvo:
        if col in df.columns:
            # Garantimos que a coluna é uma Series do Pandas
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
        else:
            # Se a coluna nem existir, criamos ela com zeros
            df[col] = 0.0
    
    return df, preco_spot

# --- INTERFACE ---
st.title("📊 GEX & DEX Vertical Exposure")

moeda = st.sidebar.selectbox("Selecione a Moeda", ["BTC", "ETH", "SOL"])
metrica = st.sidebar.radio("Métrica para Cor/Direção", ["GEX (Gamma)", "DEX (Delta)"])
raio = st.sidebar.slider("Raio de Strikes (%)", 5, 50, 20)

if st.sidebar.button("Atualizar Dashboard"):
    try:
        df_opcoes, preco_spot = buscar_dados_deribit(moeda)
        
        if df_opcoes.empty:
            st.warning("A API não retornou dados para esta moeda no momento.")
        else:
            # Filtro de strikes ao redor do preço
            margem = preco_spot * (raio / 100)
            df_filt = df_opcoes[(df_opcoes['strike'] > preco_spot - margem) & 
                               (df_opcoes['strike'] < preco_spot + margem)].copy()

            if df_filt.empty:
                st.warning("Aumente o Raio de Strikes para visualizar os dados.")
            else:
                # Cálculo de Exposição - Usando OI como multiplicador de volume
                if metrica == "GEX (Gamma)":
                    df_filt['exposicao'] = df_filt['gamma'] * df_filt['open_interest'] * (preco_spot**2)
                else:
                    df_filt['exposicao'] = df_filt['delta'] * df_filt['open_interest'] * preco_spot

                # Agrupamento por Strike para o visual de colunas lado a lado
                calls = df_filt[df_filt['tipo'] == 'C'].groupby('strike')['exposicao'].sum().reset_index()
                puts = df_filt[df_filt['tipo'] == 'P'].groupby('strike')['exposicao'].sum().reset_index()

                # --- GRÁFICO (Visual Estilo Deribit) ---
                fig = go.Figure()

                fig.add_trace(go.Bar(
                    x=calls['strike'],
                    y=calls['exposicao'],
                    name='Calls',
                    marker_color='#2E64FE' # Azul
                ))

                fig.add_trace(go.Bar(
                    x=puts['strike'],
                    y=puts['exposicao'],
                    name='Puts',
                    marker_color='#F4D03F' # Amarelo[cite: 1]
                ))

                fig.add_vline(x=preco_spot, line_dash="dash", line_color="red", 
                              annotation_text=f"SPOT: {preco_spot:,.0f}")

                fig.update_layout(
                    template="plotly_dark",
                    barmode='group',
                    height=600,
                    xaxis=dict(title="Strike Price", type='category', tickangle=45), # Eixo categórico para barras iguais[cite: 1]
                    yaxis=dict(title=f"Notional {metrica}"),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
                    bargap=0.1,
                    bargroupgap=0.1
                )

                st.plotly_chart(fig, use_container_width=True)
                st.success(f"Dashboard Atualizado para {moeda}!")

    except Exception as e:
        st.error(f"Erro ao processar: {e}")
else:
    st.info("Utilize o menu lateral para carregar os dados.")
