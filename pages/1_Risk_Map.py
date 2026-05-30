"""
pages/1_Risk_Map.py — Interactive Risk Map
Pipe segments coloured by predicted break probability, with SHAP explainability.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import plotly.graph_objects as go
import numpy as np

st.set_page_config(
    page_title="Risk Map · CityNerve",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded",
)

from app_styles import inject_css, section_title, risk_badge
from data_utils  import get_pipes, get_shap, RISK_COLORS

inject_css()

df = get_pipes()

# ── Sidebar filters ─────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        """
        <div style="padding:.8rem 0 .4rem">
            <div style="font-family:'Barlow Condensed',sans-serif;font-size:1.4rem;
                        font-weight:900;color:#e0eaf6">
                CITY<span style="color:#1de9b6">NERVE</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.divider()

    st.markdown('<div class="sidebar-label">Risk Filter</div>', unsafe_allow_html=True)
    risk_filter = st.multiselect(
        "Risk Level", options=["Critical", "High", "Medium", "Low"],
        default=["Critical", "High", "Medium", "Low"],
        label_visibility="collapsed",
    )

    st.markdown('<div class="sidebar-label">Material</div>', unsafe_allow_html=True)
    mat_filter = st.multiselect(
        "Material", options=sorted(df["material"].unique()),
        default=sorted(df["material"].unique()),
        label_visibility="collapsed",
    )

    st.markdown('<div class="sidebar-label">Ward</div>', unsafe_allow_html=True)
    ward_filter = st.multiselect(
        "Ward", options=sorted(df["ward"].unique()),
        default=sorted(df["ward"].unique()),
        label_visibility="collapsed",
    )

    st.markdown('<div class="sidebar-label">Min Risk Score</div>', unsafe_allow_html=True)
    min_risk = st.slider("Min risk", 0, 100, 0, label_visibility="collapsed")

    st.divider()
    st.markdown('<div class="sidebar-label">Legend</div>', unsafe_allow_html=True)
    for lvl, col in RISK_COLORS.items():
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:.5rem;margin:.25rem 0">'
            f'<div style="width:12px;height:12px;border-radius:50%;background:{col}"></div>'
            f'<span style="font-size:.8rem;color:#8faabf">{lvl}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

# ── Filter data ──────────────────────────────────────────────────────────────
mask = (
    df["risk_level"].isin(risk_filter) &
    df["material"].isin(mat_filter) &
    df["ward"].isin(ward_filter) &
    (df["risk_score"] >= min_risk)
)
fdf = df[mask]

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div class="cn-header">
        <div class="cn-wordmark">🗺️  RISK <span>MAP</span></div>
        <span class="cn-badge">PREDICTIVE</span>
        <div class="cn-tagline">
            Pipe segments coloured by 12-month break probability · Click a segment for SHAP explainability
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Stats row
s1, s2, s3, s4 = st.columns(4)
s1.metric("Segments Shown", f"{len(fdf):,}")
s2.metric("Critical", int((fdf["risk_level"] == "Critical").sum()))
s3.metric("High", int((fdf["risk_level"] == "High").sum()))
s4.metric("Avg Risk Score", f"{fdf['risk_score'].mean():.1f}" if len(fdf) else "—")

st.markdown("<br>", unsafe_allow_html=True)

# ── Map ───────────────────────────────────────────────────────────────────────
map_col, detail_col = st.columns([3, 1], gap="large")

with map_col:
    section_title("Toronto Watermain Network — Predicted Risk")

    fig = go.Figure()

    # One line trace per risk level (NaN-separated segments)
    for level in ["Critical", "High", "Medium", "Low"]:
        sub = fdf[fdf["risk_level"] == level]
        if sub.empty:
            continue
        lats, lons = [], []
        for _, r in sub.iterrows():
            lats.extend([r["lat0"], r["lat1"], None])
            lons.extend([r["lon0"], r["lon1"], None])
        width = {"Critical": 3.5, "High": 3.0, "Medium": 2.5, "Low": 2.0}[level]
        fig.add_trace(go.Scattermap(
            lat=lats, lon=lons,
            mode="lines",
            line=dict(width=width, color=RISK_COLORS[level]),
            name=level,
            hoverinfo="none",
            showlegend=True,
        ))

    # Hover-able midpoints
    if not fdf.empty:
        fig.add_trace(go.Scattermap(
            lat=fdf["lat"], lon=fdf["lon"],
            mode="markers",
            marker=dict(
                size=fdf["diameter_mm"].apply(lambda d: max(5, d / 40)).tolist(),
                color=fdf["risk_color"].tolist(),
                opacity=0.0,
            ),
            text=fdf["pipe_id"],
            customdata=fdf[["risk_score", "material", "age", "ward",
                            "risk_level", "diameter_mm", "emergency_cost"]].values,
            hovertemplate=(
                "<b>%{text}</b><br>"
                "Risk Score: <b>%{customdata[0]:.1f}%</b><br>"
                "Material: %{customdata[1]}<br>"
                "Age: %{customdata[2]} years<br>"
                "Ward: %{customdata[3]}<br>"
                "Diameter: %{customdata[5]}mm<br>"
                "Emergency Cost: $%{customdata[6]:,}<extra></extra>"
            ),
            name="hover",
            showlegend=False,
        ))

    fig.update_layout(
        map=dict(
            style="carto-darkmatter",
            center=dict(lat=43.70, lon=-79.38),
            zoom=10.5,
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=0, b=0),
        height=560,
        legend=dict(
            bgcolor="#0d1b2a",
            bordercolor="#162033",
            borderwidth=1,
            font=dict(color="#8faabf", size=11),
            orientation="v",
            x=0.01, y=0.99,
            xanchor="left", yanchor="top",
        ),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

# DETAIL PANEL
with detail_col:
    section_title("Segment Details")

    pipe_options = fdf.sort_values("risk_score", ascending=False)["pipe_id"].tolist()
    if not pipe_options:
        st.info("No segments match current filters.")
    else:
        selected_id = st.selectbox(
            "Select pipe",
            options=pipe_options,
            format_func=lambda x: x,
            label_visibility="collapsed",
        )

        row = fdf[fdf["pipe_id"] == selected_id].iloc[0]
        level = str(row["risk_level"])
        score = row["risk_score"]

        # Score gauge via plotly
        gauge_color = RISK_COLORS.get(level, "#888")
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=score,
            number=dict(
                suffix="",
                font=dict(family="Barlow Condensed", size=38, color=gauge_color),
            ),
            gauge=dict(
                axis=dict(
                    range=[0, 100],
                    tickcolor="#162033",
                    tickfont=dict(color="#5a7a9a", size=9),
                ),
                bar=dict(color=gauge_color, thickness=0.22),
                bgcolor="#07101f",
                borderwidth=0,
                steps=[
                    dict(range=[0, 25],  color="#0d1b2a"),
                    dict(range=[25, 50], color="#0d1b2a"),
                    dict(range=[50, 75], color="#0d1b2a"),
                    dict(range=[75, 100],color="#0d1b2a"),
                ],
                threshold=dict(
                    line=dict(color=gauge_color, width=2),
                    thickness=0.7,
                    value=score,
                ),
            ),
        ))
        fig_gauge.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=10, r=10, t=10, b=5),
            height=150,
        )
        st.plotly_chart(fig_gauge, use_container_width=True,
                        config={"displayModeBar": False})

        st.markdown(
            f"""
            <div class="cn-card">
                <div class="cn-card-title">Pipe Profile</div>
                <table style="width:100%;border-collapse:collapse;font-size:.8rem">
                    <tr><td style="color:#5a7a9a;padding:.2rem 0">ID</td>
                        <td style="color:#c9d8ea;font-family:'IBM Plex Mono',monospace">{row['pipe_id']}</td></tr>
                    <tr><td style="color:#5a7a9a">Ward</td>
                        <td style="color:#c9d8ea">{row['ward']}</td></tr>
                    <tr><td style="color:#5a7a9a">Material</td>
                        <td style="color:#c9d8ea">{row['material']}</td></tr>
                    <tr><td style="color:#5a7a9a">Age</td>
                        <td style="color:#c9d8ea">{row['age']} yrs ({row['install_year']})</td></tr>
                    <tr><td style="color:#5a7a9a">Diameter</td>
                        <td style="color:#c9d8ea">{row['diameter_mm']} mm</td></tr>
                    <tr><td style="color:#5a7a9a">Length</td>
                        <td style="color:#c9d8ea">{row['length_m']} m</td></tr>
                    <tr><td style="color:#5a7a9a">Risk</td>
                        <td>{risk_badge(level)}</td></tr>
                    <tr><td style="color:#5a7a9a">Properties</td>
                        <td style="color:#c9d8ea">{row['properties_affected']:,}</td></tr>
                    <tr><td style="color:#5a7a9a">Emergency $</td>
                        <td style="color:#ffa726;font-family:'IBM Plex Mono',monospace">${row['emergency_cost']:,}</td></tr>
                </table>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # SHAP waterfall chart
        st.markdown(
            '<div class="section-title" style="margin-top:1rem">SHAP — Risk Drivers</div>',
            unsafe_allow_html=True,
        )
        shap = get_shap(row)
        shap_sorted = sorted(shap.items(), key=lambda x: x[1])
        names  = [s[0] for s in shap_sorted]
        values = [s[1] for s in shap_sorted]
        colors = ["#1de9b6" if v < 5 else "#ffa726" if v < 12 else "#ff3d3d" for v in values]

        fig_shap = go.Figure(go.Bar(
            y=names, x=values,
            orientation="h",
            marker=dict(color=colors, line=dict(width=0)),
            text=[f"+{v:.1f}" for v in values],
            textposition="outside",
            textfont=dict(family="IBM Plex Mono", size=9, color="#8faabf"),
            hovertemplate="<b>%{y}</b><br>Contribution: +%{x:.1f}<extra></extra>",
        ))
        fig_shap.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=0, r=35, t=5, b=5),
            height=220,
            xaxis=dict(
                tickfont=dict(color="#5a7a9a", size=9),
                gridcolor="#162033",
                title=dict(text="Risk contribution", font=dict(color="#3d5a78", size=9)),
            ),
            yaxis=dict(
                tickfont=dict(family="DM Sans", color="#8faabf", size=9),
            ),
        )
        st.plotly_chart(fig_shap, use_container_width=True,
                        config={"displayModeBar": False})

        if st.button("💥 Simulate Cascade Failure →"):
            st.switch_page("pages/2_Cascade_Simulator.py")
