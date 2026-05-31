"""
pages/1_Risk_Map.py — Interactive Risk Map
Pipe segments coloured by predicted break probability, with SHAP explainability.
Supports two colour modes when real data is loaded:
  • Color by Risk Level  — teal/amber/red by break probability
  • Color by Pipe Type   — Transmission (teal) vs Distribution (sky-blue)
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
    initial_sidebar_state="collapsed",
)

from app_styles import inject_css, section_title, risk_badge
from agent.voice_pipe_match import find_pipe_for_latest_transcript
from api_client import get_pipes_api, get_workflow2_health_api, post_analysis_run_api
from data_utils  import get_shap, RISK_COLORS
from frontend.nav import render_top_nav, w2_session_key

inject_css()

use_real = render_top_nav("risk_map")
df = get_pipes_api(use_real=use_real)

pipe_types_available = sorted(df["pipe_type"].unique()) if "pipe_type" in df.columns else []
has_layers = len(pipe_types_available) > 1
TYPE_COLORS = {"Transmission": "#1de9b6", "Distribution": "#4fc3f7", "Synthetic": "#8faabf"}
TYPE_WIDTHS = {"Transmission": 3.5, "Distribution": 1.8, "Synthetic": 2.0}

# ── Filters now live in-page (see map_col / filter_col below) ─────────────────
if has_layers:
    type_filter = pipe_types_available
    color_mode  = "Risk Level"
else:
    type_filter = pipe_types_available or ["Synthetic"]
    color_mode  = "Risk Level"

risk_filter = ["Critical", "High", "Medium", "Low"]
mat_filter  = sorted(df["material"].unique())
ward_filter = sorted(df["ward"].unique())
min_risk    = 0

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div class="cn-header">
        <div class="cn-wordmark">🗺️  RISK <span>MAP</span></div>
        <span class="cn-badge">PREDICTIVE</span>
        <div class="cn-tagline">
            Pipe segments coloured by 12-month break probability · SHAP explainability
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
<style>
@keyframes voice-pulse {
  0%,100% { opacity: 1; border-left-color: #f97316; box-shadow: 0 0 6px rgba(249,115,22,.6); }
  50%      { opacity: .6; border-left-color: #fbbf24; box-shadow: 0 0 14px rgba(251,191,36,.4); }
}
.voice-alert {
  animation: voice-pulse 1.4s ease-in-out infinite;
  border-left: 3px solid #f97316;
  background: rgba(249,115,22,.08);
  border-radius: 6px;
  padding: .6rem .85rem;
  font-size: .82rem;
  color: #e8d5b0;
  margin-bottom: .6rem;
}
.voice-dot {
  display: inline-block; width: 9px; height: 9px;
  border-radius: 50%; background: #f97316;
  animation: voice-pulse 1.4s ease-in-out infinite;
  margin-right: 6px; vertical-align: middle;
}
</style>
""",
    unsafe_allow_html=True,
)

# ── Map + inline filter panel + detail ────────────────────────────────────────
map_col, filter_col, detail_col = st.columns([3, 1, 1], gap="medium")

with filter_col:
    st.markdown('<div class="filter-panel">', unsafe_allow_html=True)
    section_title("Filters")
    risk_filter = st.multiselect(
        "Risk Level", options=["Critical", "High", "Medium", "Low"],
        default=["Critical", "High", "Medium", "Low"],
    )
    mat_filter = st.multiselect(
        "Material", options=sorted(df["material"].unique()),
        default=sorted(df["material"].unique()),
    )
    ward_filter = st.multiselect(
        "Ward", options=sorted(df["ward"].unique()),
        default=sorted(df["ward"].unique()),
    )
    min_risk = st.slider("Min Risk Score", 0, 100, 0)
    if has_layers:
        st.divider()
        type_filter = st.multiselect(
            "Pipe Type", options=pipe_types_available,
            default=pipe_types_available,
        )
        color_mode = st.radio("Color by", ["Risk Level", "Pipe Type"], horizontal=True)
    st.divider()
    section_title("Legend")
    for lvl, col in RISK_COLORS.items():
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:.5rem;margin:.2rem 0">'
            f'<div style="width:10px;height:10px;border-radius:50%;background:{col};flex-shrink:0"></div>'
            f'<span style="font-size:.78rem;color:#8faabf">{lvl}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
    st.markdown('</div>', unsafe_allow_html=True)

# Apply filters
mask = (
    df["risk_level"].isin(risk_filter) &
    df["material"].isin(mat_filter) &
    df["ward"].isin(ward_filter) &
    (df["risk_score"] >= min_risk)
)
if has_layers and type_filter:
    mask = mask & df["pipe_type"].isin(type_filter)
fdf = df[mask]

_voice_payload, voice_match = find_pipe_for_latest_transcript(df)

# Stats strip
s1, s2, s3, s4 = st.columns(4)
s1.metric("Shown", f"{len(fdf):,}")
s2.metric("Critical", int((fdf["risk_level"] == "Critical").sum()))
s3.metric("High", int((fdf["risk_level"] == "High").sum()))
s4.metric("Avg Risk", f"{fdf['risk_score'].mean():.1f}" if len(fdf) else "—")

st.markdown("<br>", unsafe_allow_html=True)

with map_col:
    section_title(
        "Toronto Watermain Network — Predicted Risk"
        if color_mode == "Risk Level"
        else "Toronto Watermain Network — Transmission vs Distribution"
    )

    fig = go.Figure()

    if color_mode == "Pipe Type" and has_layers:
        # ── Color by Pipe Type ──────────────────────────────────────────────
        # Render Distribution first so Transmission appears on top
        for ptype in ["Distribution", "Transmission"]:
            sub = fdf[fdf["pipe_type"] == ptype]
            if sub.empty:
                continue
            lats, lons = [], []
            for _, r in sub.iterrows():
                lats.extend([r["lat0"], r["lat1"], None])
                lons.extend([r["lon0"], r["lon1"], None])
            fig.add_trace(go.Scattermap(
                lat=lats, lon=lons,
                mode="lines",
                line=dict(width=TYPE_WIDTHS[ptype], color=TYPE_COLORS[ptype]),
                name=ptype,
                hoverinfo="none",
                showlegend=True,
            ))

    else:
        # ── Color by Risk Level (default) ───────────────────────────────────
        # Transmission = thicker lines; Distribution = thinner lines.
        # One legend entry per risk level (using legendgroup to merge Tx/Dist).
        risk_base_widths = {"Critical": 3.5, "High": 3.0, "Medium": 2.5, "Low": 2.0}
        for level in ["Critical", "High", "Medium", "Low"]:
            color      = RISK_COLORS[level]
            base_width = risk_base_widths[level]

            if has_layers:
                # Two sub-traces per risk level — merged in legend via legendgroup
                for idx, ptype in enumerate(["Distribution", "Transmission"]):
                    sub = fdf[(fdf["risk_level"] == level) & (fdf["pipe_type"] == ptype)]
                    if sub.empty:
                        continue
                    lats, lons = [], []
                    for _, r in sub.iterrows():
                        lats.extend([r["lat0"], r["lat1"], None])
                        lons.extend([r["lon0"], r["lon1"], None])
                    width = base_width + (0.8 if ptype == "Transmission" else 0)
                    fig.add_trace(go.Scattermap(
                        lat=lats, lon=lons,
                        mode="lines",
                        line=dict(width=width, color=color),
                        name=level,
                        legendgroup=level,
                        showlegend=(idx == 1),   # show legend entry once (for Transmission)
                        hoverinfo="none",
                    ))
            else:
                sub = fdf[fdf["risk_level"] == level]
                if sub.empty:
                    continue
                lats, lons = [], []
                for _, r in sub.iterrows():
                    lats.extend([r["lat0"], r["lat1"], None])
                    lons.extend([r["lon0"], r["lon1"], None])
                fig.add_trace(go.Scattermap(
                    lat=lats, lon=lons,
                    mode="lines",
                    line=dict(width=base_width, color=color),
                    name=level,
                    hoverinfo="none",
                    showlegend=True,
                ))

    # ── Hover-able midpoints (always shown) ──────────────────────────────────
    if not fdf.empty:
        hover_type = fdf["pipe_type"] if "pipe_type" in fdf.columns else ["—"] * len(fdf)
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
                            "risk_level", "diameter_mm", "emergency_cost",
                            "pipe_type"]].values,
            hovertemplate=(
                "<b>%{text}</b><br>"
                "Type: <b>%{customdata[7]}</b><br>"
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

    if voice_match is not None and voice_match.lat is not None:
        fig.add_trace(go.Scattermap(
            lat=[voice_match.lat], lon=[voice_match.lon], mode="markers",
            marker=dict(size=32, color="#f97316", opacity=0.20),
            hoverinfo="none", showlegend=False,
        ))
        fig.add_trace(go.Scattermap(
            lat=[voice_match.lat], lon=[voice_match.lon], mode="markers",
            marker=dict(size=14, color="#f97316", opacity=0.95, symbol="circle"),
            name="Active Caller Report",
            hovertemplate=(
                f"<b>Active Caller Report</b><br>"
                f"Matched pipe: {voice_match.pipe_id}<br>"
                f"Confidence: {voice_match.confidence:.0%}<extra></extra>"
            ),
            showlegend=True,
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

# ── Detail panel ──────────────────────────────────────────────────────────────
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

        row   = fdf[fdf["pipe_id"] == selected_id].iloc[0]
        level = str(row["risk_level"])
        score = row["risk_score"]

        # Risk gauge
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
                steps=[dict(range=[i * 25, (i + 1) * 25], color="#0d1b2a") for i in range(4)],
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

        # Pipe profile table — extra rows for real data
        pipe_type_val = row.get("pipe_type", "Synthetic")
        street_val    = str(row.get("street", "") or "")
        type_color    = TYPE_COLORS.get(pipe_type_val, "#8faabf")

        extra_rows = ""
        if pipe_type_val in ("Transmission", "Distribution"):
            extra_rows += (
                f'<tr><td style="color:#5a7a9a">Layer</td>'
                f'<td><span style="color:{type_color};font-weight:600">'
                f'{pipe_type_val}</span></td></tr>'
            )
        if street_val:
            extra_rows += (
                f'<tr><td style="color:#5a7a9a;vertical-align:top">Street</td>'
                f'<td style="color:#c9d8ea;font-size:.75rem">{street_val}</td></tr>'
            )

        st.markdown(
            f"""
            <div class="cn-card">
                <div class="cn-card-title">Pipe Profile</div>
                <table style="width:100%;border-collapse:collapse;font-size:.8rem">
                    <tr><td style="color:#5a7a9a;padding:.2rem 0">ID</td>
                        <td style="color:#c9d8ea;font-family:'IBM Plex Mono',monospace">{row['pipe_id']}</td></tr>
                    {extra_rows}
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

        # ── SHAP / Risk Drivers ───────────────────────────────────────────────
        if use_real and pipe_type_val in ("Transmission", "Distribution"):
            # Real data: only material + age are actual signals.
            # Show a simplified chart and label everything clearly.
            st.markdown(
                '<div class="section-title" style="margin-top:1rem">Risk Drivers'
                ' <span style="font-size:.65rem;color:#3d5a78;font-weight:400">'
                '(estimated — material &amp; age only)</span></div>',
                unsafe_allow_html=True,
            )
            from data_utils import MATERIAL_RISK as _MAT_RISK
            m_contrib  = round(_MAT_RISK.get(row["material"], 0.5) * 30, 1)
            age_contrib = round((row["age"] / 106) * 35, 1)
            names  = [f"Material ({row['material']})", "Pipe Age"]
            values = [m_contrib, age_contrib]
            colors = [
                "#ffa726" if m_contrib < 20 else "#ff3d3d",
                "#1de9b6" if age_contrib < 12 else "#ffa726" if age_contrib < 25 else "#ff3d3d",
            ]
        else:
            # Synthetic data: full SHAP breakdown
            st.markdown(
                '<div class="section-title" style="margin-top:1rem">SHAP — Risk Drivers</div>',
                unsafe_allow_html=True,
            )
            shap       = get_shap(row)
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
            height=220 if not use_real else 100,
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

        st.caption(
            "Workflow 1 (Nemotron summaries) runs on the Overview → "
            "Decision Engine **Why Failing Agent** panel when you select pipes in the queue."
        )

        # ── Workflow 2 multi-role analysis (Super) ───────────────────────────
        st.markdown(
            '<div class="section-title" style="margin-top:1.2rem">'
            'Multi-Role Analysis '
            '<span style="font-size:.65rem;color:#3d5a78;font-weight:400">'
            '(Nemotron Super · W2)</span></div>',
            unsafe_allow_html=True,
        )
        w2_health = get_workflow2_health_api()
        w2_ok = w2_health.get("ok", False)
        if not w2_ok:
            st.caption(
                f"Workflow 2 unavailable: {w2_health.get('detail', 'check Ollama :11434')}"
            )

        w2_pipe_id = selected_id
        if voice_match is not None:
            incident = (_voice_payload or {}).get("incident") or {}
            loc = incident.get("location") if isinstance(incident, dict) else None
            addr = (
                loc.get("address", "reported location")
                if isinstance(loc, dict)
                else "reported location"
            )
            st.session_state["voice_pipe_match"] = {
                "pipe_id": voice_match.pipe_id,
                "confidence": voice_match.confidence,
                "method": voice_match.method,
                "address": addr,
                "neighbourhood": voice_match.matched_neighbourhood,
                "lat": voice_match.lat,
                "lon": voice_match.lon,
            }
            where = addr
            if voice_match.matched_neighbourhood:
                where = (
                    f"{addr} · neighbourhood "
                    f"<strong>{voice_match.matched_neighbourhood}</strong>"
                )
            st.markdown(
                f'<div class="voice-alert">'
                f'<span class="voice-dot"></span>'
                f'<strong>Active Caller Report</strong> — {where}<br>'
                f'<span style="color:#9ba8b5;font-size:.76rem">'
                f'Matched to <strong>{voice_match.pipe_id}</strong> · '
                f'{voice_match.confidence:.0%} confidence · {voice_match.method}'
                f'</span></div>',
                unsafe_allow_html=True,
            )
            if voice_match.pipe_id != selected_id:
                use_matched = st.checkbox(
                    f"Use matched caller pipe ({voice_match.pipe_id}) instead of "
                    f"map selection ({selected_id})",
                    value=True,
                    key=f"use_voice_pipe_{selected_id}",
                )
                if use_matched:
                    w2_pipe_id = voice_match.pipe_id
            else:
                w2_pipe_id = voice_match.pipe_id

        run_key = w2_session_key(w2_pipe_id)
        if st.button(
            "Run multi-role analysis (Super)",
            disabled=not w2_ok,
            key=f"btn_w2_{w2_pipe_id}",
        ):
            with st.spinner(
                "Running transcript orchestrator, Engineer, Police, Field, "
                "Operations, and synthesis on Super… (may take several minutes)"
            ):
                try:
                    st.session_state[run_key] = post_analysis_run_api(
                        w2_pipe_id,
                        use_real=use_real,
                        use_latest_voice_transcript=True,
                    )
                except Exception as exc:
                    st.session_state.pop(run_key, None)
                    st.error(f"Workflow 2 failed: {exc}")

        w2_result = st.session_state.get(run_key)
        if w2_result:
            w2_source = w2_result.get("source", "unknown")
            st.caption(
                f"Run `{w2_result.get('run_id', '')}` · source: **{w2_source}** · "
                f"model: `{w2_result.get('models', {}).get('workflow2', 'super')}`"
            )
            role_tabs = st.tabs(
                ["Engineer", "Police", "Field", "Operations", "Final plan"]
            )
            roles_by_name = {r["role"]: r for r in w2_result.get("roles", [])}
            tab_map = [
                ("Engineer", "engineer"),
                ("Police", "police"),
                ("Field", "field"),
                ("Operations", "operations"),
            ]
            for tab, (label, role_key) in zip(role_tabs[:4], tab_map):
                with tab:
                    report = roles_by_name.get(role_key, {})
                    src = report.get("source", "")
                    st.caption(f"{label} · {src}")
                    st.markdown(report.get("markdown", "_No content_"))
                    if role_key == "operations":
                        bom = w2_result.get("bill_of_materials") or {}
                        if bom.get("line_items"):
                            st.markdown("#### Bill of Materials and supplier awards")
                            st.table(
                                [
                                    {
                                        "Item": line.get("description"),
                                        "Qty": line.get("qty"),
                                        "Unit": line.get("unit"),
                                        "Supplier": line.get("chosen_supplier_name"),
                                        "Unit $": line.get("unit_price"),
                                        "Line $": line.get("line_total"),
                                    }
                                    for line in bom.get("line_items", [])
                                ]
                            )
                            st.caption(
                                f"Estimated total with contingency/tax: "
                                f"${bom.get('total_estimate', 0):,.2f} CAD"
                            )
                        if bom.get("contract_awards"):
                            st.markdown("#### Recommended supplier contract awards")
                            st.table(
                                [
                                    {
                                        "Supplier": award.get("supplier_name"),
                                        "Type": award.get("supplier_type"),
                                        "Scope": award.get("scope"),
                                        "Award $": award.get("award_subtotal"),
                                        "Approval": "Required"
                                        if award.get("requires_human_approval", True)
                                        else "Not flagged",
                                    }
                                    for award in bom.get("contract_awards", [])
                                ]
                            )
            with role_tabs[4]:
                st.markdown(w2_result.get("final_markdown", ""))
                bom = w2_result.get("bill_of_materials") or {}
                if bom.get("contract_awards"):
                    st.markdown("#### Recommended supplier contract awards")
                    st.table(
                        [
                            {
                                "Supplier": award.get("supplier_name"),
                                "Type": award.get("supplier_type"),
                                "Scope": award.get("scope"),
                                "Award $": award.get("award_subtotal"),
                            }
                            for award in bom.get("contract_awards", [])
                        ]
                    )
                plan = w2_result.get("action_plan", {})
                with st.expander("Action plan (JSON)"):
                    st.json(plan)

        if st.button("💥 Simulate Cascade Failure →"):
            st.switch_page("pages/3_Cascade_Simulator.py")
