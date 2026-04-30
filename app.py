# --- CRIAÇÃO DO GRÁFICO (Estilo Profissional) ---
    fig = go.Figure()

    # 1. Adicionando a Área de GEX Absoluto (a sombra roxa ao fundo)
    df_abs = df.groupby('strike')['open_interest'].sum().reset_index()
    fig.add_trace(go.Scatter(
        x=df_abs['strike'], 
        y=df_abs['open_interest'],
        fill='tozeroy',
        mode='none',
        fillcolor='rgba(100, 50, 200, 0.2)', # Roxo transparente
        name='Abs GEX'
    ))

    # 2. Adicionando as barras de Net GEX (Verde e Vermelho)
    fig.add_trace(go.Bar(
        x=gex_por_strike['strike'],
        y=gex_por_strike['gex'],
        marker_color=['#00ffbb' if val > 0 else '#ff4444' for val in gex_por_strike['gex']],
        name="Net GEX"
    ))

    # 3. Pegar o preço atual (Spot) para a linha vertical
    preco_spot = df['estimated_delivery_price'].iloc[0]

    # Configuração de Estética e Linha Spot
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#111727", # Fundo escuro igual ao App
        plot_bgcolor="#111727",
        title=f"SPX | Net GEX {moeda_escolhida}",
        xaxis=dict(title="STRIKE", gridcolor='#222'),
        yaxis=dict(title="GEX", gridcolor='#222'),
        showlegend=True,
        bargap=0.05
    )

    # Adicionando a linha do Preço Spot (Laranja)
    fig.add_vline(x=preco_spot, line_width=2, line_dash="solid", line_color="orange")
    fig.add_annotation(x=preco_spot, text=f"Spot: {preco_spot}", showarrow=False, yref="paper", y=1.05, font_color="orange")

    st.plotly_chart(fig, use_container_width=True)
