import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Deribit Multi-Expiry Analytics", layout="wide")

def limpar_e_converter_coluna(df, nome_coluna):
    if nome_coluna in df.columns:
        return pd.to_numeric(df[nome_coluna].astype(str).str.replace('-', '0'), errors='coerce').fillna(0.0)
    return pd.Series(0.0, index=df.index)

def processar_arquivo_deribit(caminho):
    df = pd.read_csv(caminho)
    
    # Extração de Dados do Instrumento (Ex: BTC-30APR26-69000-C)
    partes = df['Instrument'].str.split('-')
    df['expiracao'] = partes.str[1] # Extrai a data (ex: 30APR26)
    df['strike'] = partes.str[2].astype(float)
    df['tipo'] = partes.str[3]
    
    # Limpeza das colunas
    df['open_interest'] = limpar_e_converter_coluna(df, 'Open')
    df['gamma'] = limpar_e_converter_coluna(df, 'Gamma')
    df['delta'] = limpar_e_converter_coluna(df, 'Δ|Delta')
    
    return df

# --- INTERFACE ---
st.title("📊 GEX & DEX Analytics - Multi-Expiry")

try:
    arquivo_nome = 'BTC-30APR26-export.csv'
    df_raw = processar_arquivo_deribit(arquivo_nome)
    
    # --- MENU LATERAL ---
    st.sidebar.header("Filtros")
    
    # Seleção de Expirações (Multi-select)
    expiracoes_disponiveis = sorted(df_raw['expiracao'].unique())
    expiracoes_selecionadas = st.sidebar.multiselect(
        "Selecione as Datas de Expiração",
        options=expiracoes_disponiveis,
        default=expiracoes_disponiveis
    )
    
    metrica = st.sidebar.radio("Escolha a Métrica", ["OI", "GEX", "DEX"])
    spot_ref = st.sidebar.number_input("Preço Spot de Referência", value=77000.0)
    raio_pct = st.sidebar.slider("Raio de Strikes (%)", 5, 50, 20)

    # --- FILTRAGEM ---
    # Filtra pelas datas selecionadas e pelo raio de preço
    df_filt = df_raw[df_raw['expiracao'].isin(expiracoes_selecionadas)].copy()
    
    margem = spot_ref * (raio_pct / 100)
    df_filt = df_filt[(df_filt['strike'] > spot_ref - margem) & 
                     (df_filt['strike'] < spot_ref + margem)]

    # --- CÁLCULOS ---
    df_filt['GEX_calc'] = df_filt['gamma'] * df_filt['open_interest'] * (spot_ref**2)
    df_filt['DEX_calc'] = df_filt['delta'] * df_filt['open_interest'] * spot_ref
    df_filt['OI_calc'] = df_filt['open_interest']

    mapa_metrica = {"OI": "OI_calc", "GEX": "GEX_calc", "DEX": "DEX_calc"}
    col_alvo = mapa_metrica[metrica]

    if not df_filt.empty:
        # Agrupamento (Soma os dados de todas as expirações selecionadas por strike)
        pivot = df_filt.groupby(['strike', 'tipo'])[col_alvo].sum().unstack().fillna(0)
        for t in ['C', 'P']:
            if t not in pivot.columns: pivot[t] = 0
        pivot = pivot.reset_index()

        # --- GRÁFICO ---
        fig = go.Figure()

        fig.add_trace(go.Bar(
            x=pivot['strike'], y=pivot['C'],
            name='Calls', marker_color='#2E64FE'
        ))

        fig.add_trace(go.Bar(
            x=pivot['strike'], y=pivot['P'],
            name='Puts', marker_color='#F4D03F'
        ))

        fig.add_vline(x=spot_ref, line_dash="dash", line_color="red", 
                      annotation_text=f"SPOT: {spot_ref:,.0f}")

        fig.update_layout(
            template="plotly_dark",
            barmode='group',
            xaxis=dict(title="Strike Price", type='category'),
            yaxis=dict(title=f"{metrica} Total (Expirações Selecionadas)"),
            height=600,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)
        )

        st.plotly_chart(fig, use_container_width=True)
        
        # Detalhamento
        st.write(f"Exibindo dados para: {', '.join(expiracoes_selecionadas)}")
    else:
        st.warning("Nenhum dado encontrado para os filtros selecionados.")

except Exception as e:
    st.error(f"Erro: {e}")
