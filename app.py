# =========================
# HEATMAP PROFISSIONAL (CORRIGIDO)
# =========================
if not hist.empty:

    st.subheader("🔥 GEX Heatmap (Pro)")

    pivot = hist.pivot_table(
        index='strike',
        columns='time',
        values='gex',
        aggfunc='sum'
    ).fillna(0)

    pivot = pivot.sort_index()

    # pega preço atual com segurança
    if "price" in hist.columns:
        spot = hist["price"].iloc[-1]
    else:
        spot = pivot.index.mean()

    # zoom região relevante
    range_min = spot * 0.9
    range_max = spot * 1.1
    pivot = pivot[(pivot.index >= range_min) & (pivot.index <= range_max)]

    # proteção contra dataset pequeno
    if pivot.shape[0] < 5 or pivot.shape[1] < 2:
        st.warning("Poucos dados ainda para heatmap.")
    else:

        # suavização
        pivot_smooth = pivot.rolling(3, axis=0, min_periods=1).mean()

        z = pivot_smooth.values

        # normalização robusta
        max_abs = np.percentile(np.abs(z), 95)
        if max_abs == 0:
            max_abs = 1

        z = np.clip(z, -max_abs, max_abs)

        fig = go.Figure(data=go.Heatmap(
            z=z,
            x=pivot_smooth.columns,
            y=pivot_smooth.index,
            colorscale=[
                [0.0, "#8B0000"],
                [0.5, "#111111"],
                [1.0, "#00FFFF"]
            ],
            zmid=0,
            colorbar=dict(title="GEX"),
        ))

        fig.add_hline(
            y=spot,
            line_color="white",
            line_width=2,
            annotation_text="SPOT"
        )

        fig.update_layout(
            template="plotly_dark",
            height=650,
            xaxis=dict(title="Tempo", tickangle=45),
            yaxis=dict(title="Strike")
        )

        st.plotly_chart(fig, use_container_width=True)

else:
    st.info("Ainda sem histórico suficiente para heatmap.")
