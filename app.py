st.subheader("🔥 GEX Heatmap (Pro)")

# =========================
# PREPARAÇÃO DOS DADOS
# =========================
pivot = hist.pivot_table(
    index='strike',
    columns='time',
    values='gex',
    aggfunc='sum'
).fillna(0)

# ordena corretamente
pivot = pivot.sort_index()

# =========================
# FILTRO DE REGIÃO (ZOOM)
# =========================
spot = hist["price"].iloc[-1]

range_min = spot * 0.9
range_max = spot * 1.1

pivot = pivot[(pivot.index >= range_min) & (pivot.index <= range_max)]

# =========================
# SUAVIZAÇÃO (ANTI-RUÍDO)
# =========================
pivot_smooth = pivot.rolling(3, axis=0, min_periods=1).mean()

# =========================
# NORMALIZAÇÃO (CRUCIAL)
# =========================
z = pivot_smooth.values

max_abs = np.percentile(np.abs(z), 95)
z = np.clip(z, -max_abs, max_abs)

# =========================
# HEATMAP
# =========================
fig = go.Figure(data=go.Heatmap(
    z=z,
    x=pivot_smooth.columns,
    y=pivot_smooth.index,
    colorscale=[
        [0.0, "#8B0000"],   # vermelho escuro
        [0.5, "#111111"],   # neutro
        [1.0, "#00FFFF"]    # azul/ciano
    ],
    zmid=0,
    colorbar=dict(title="GEX"),
))

# =========================
# LINHA DE PREÇO
# =========================
fig.add_hline(
    y=spot,
    line_color="white",
    line_width=2,
    annotation_text="SPOT"
)

# =========================
# LAYOUT
# =========================
fig.update_layout(
    template="plotly_dark",
    height=650,
    margin=dict(t=40, b=40),
    xaxis=dict(
        title="Tempo",
        tickangle=45
    ),
    yaxis=dict(
        title="Strike",
        autorange="reversed"  # opcional (estilo bookmap)
    )
)

st.plotly_chart(fig, use_container_width=True)
