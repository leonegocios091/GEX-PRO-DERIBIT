import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Deribit Options Chain Monitor", layout="wide")

def buscar_dados_completos(moeda):
    # 1. Busca Preço Spot
    url_preco = f"https://www.deribit.com/api/v2/public/get_index_price?index_name={moeda.lower()}_usd"
    res_preco = requests.get(url_preco).json()
    preco_spot = float(res_preco['result']['index_price'])
    
    # 2. Busca Resumo da Cadeia
    url_chain = f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={moeda}&kind=option"
    res_chain = requests.get(url_chain).json()
    dados = res_chain.get('result', [])
    
    if not dados:
        return pd.DataFrame(), preco_spot
        
    df = pd.DataFrame(dados)
    
    # 3. Processamento e Limpeza (Blindagem contra erros de tipo)
    df['strike'] = df['instrument_name'].str.split('-').str[2].astype(float)
    df['tipo'] = df['instrument_name'].str.split('-').str[3]
    
    # Garante que as colunas existam e sejam floats antes de qualquer operação
    for col in ['open_interest', 'gamma', 'delta']:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
        
    # 4. Cálculos de Exposição (Notional)
    df['GEX'] = df['gamma'] * df['open_interest'] * (preco_spot**2)
    df['DEX'] = df['delta'] * df['open_interest'] * preco_spot
    df['OI'] = df['open_interest']
    
    return df, preco_spot

# --- INTERFACE STREAMLIT ---
st.title("📈 Deribit Options Chain: OI, GEX & DEX")

moeda = st.sidebar.selectbox("Ativo", ["BTC", "ETH", "SOL"])
metrica_visual = st.sidebar.radio("Selecione a Métrica do Gráfico", ["OI", "GEX", "DEX"])
raio_pct = st.sidebar.slider("Raio de Strikes (%)", 5, 50, 20)

if st.sidebar.button("Atualizar Dados"):
    try:
        df, spot = buscar_dados_completos(moeda)
        
        if df.empty:
            st.error("Não foi possível obter dados da Deribit.")
        else:
            # Filtro de Strikes
            margem = spot * (raio_pct / 100)
            df_filt = df[(df['strike'] > spot - margem) & (df['strike'] < spot + margem)].copy()
            
            # Agrupamento por Strike e Tipo
            chain = df_filt.groupby(['strike', 'tipo'])[metrica_visual].sum().unstack().fillna(0)
            chain.columns = ['Calls', 'Puts']
            chain = chain.reset_index()

            # --- CONSTRUÇÃO DO GRÁFICO DE LINHAS/ÁREAS ---
            fig = go.Figure()

            # Linha de Calls (Azul com preenchimento)
            fig.add_trace(go.Scatter(
                x=chain['strike'], y=chain['Calls'],
                mode='lines', name='Calls',
                line=dict(color='#2E64FE', width=3),
                fill='tozeroy' # Preenchimento até o eixo zero
            ))

            # Linha de Puts (Amarela com preenchimento)
            fig.add_trace(go.Scatter(
                x=chain['strike'], y=chain['Puts'],
                mode='lines', name='Puts',
                line=dict(color='#F4D03F', width=3),
                fill='tozeroy'
            ))

            # Marcador do Preço Spot Atual
            fig.add_vline(x=spot, line_dash="dash", line_color="red", 
                          annotation_text=f"SPOT: {spot:,.0f}", annotation_position="top")

            fig.update_layout(
                template="plotly_dark",
                height=600,
                title=f"Distribuição de {metrica_visual} por Strike - {moeda}",
                xaxis_title="Strike Price",
                yaxis_title=f"Valor de {metrica_visual}",
                hovermode="x unified"
            )

            st.plotly_chart(fig, use_container_width=True)

            # --- TABELA DE RESUMO ---
            st.subheader("Resumo da Cadeia")
            col1, col2, col3 = st.columns(3)
            col1.metric("Total OI Calls", f"{df_filt[df_filt['tipo']=='C']['OI'].sum():,.2f}")
            col2.metric("Total OI Puts", f"{df_filt[df_filt['tipo']=='P']['OI'].sum():,.2f}")
            col3.metric("Net GEX", f"{df_filt['GEX'].sum():,.2f}")

    except Exception as e:
        st.error(f"Erro inesperado: {e}")
else:
    st.info("Clique em 'Atualizar Dados' no menu lateral.")
