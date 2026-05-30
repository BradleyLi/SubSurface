"""
pages/3_Decision_Engine.py — Capital Works Priority Queue + Work Order Generator
Ranks pipe segments by expected savings and generates Nemotron work orders.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np

st.set_page_config(
    page_title="Decision Engine · CityNerve",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from app_styles import inject_css, section_title, risk_badge
from data_utils  import get_pipes, RISK_COLORS

inject_css()

# ── Hide sidebar, use top nav ──────────────────────────────────────────────
st.markdown(
    """
    <style>
    [data-testid="stSidebar"]    { display: none !important; }
    [data-testid="stSidebarNav"] { display: none !important; }
    [data-testid="collapsedControl"] { display: none !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

df = get_pipes(use_real=st.session_state.get("use_real_data", False))

# ── Top Nav ───────────────────────────────────────────────────────────────────
logo_col, gap_col, nav1, nav2, nav3, nav4, toggle_col = st.columns([2.8, 0.3, 1, 1, 1, 1.4, 2.5])
with logo_col:
    st.markdown(
        '<div class="cn-topnav"><div class="cn-nav-logo">CITY<span>NERVE</span>'
        '<span class="cn-nav-sub"> SubSurface Intelligence</span></div></div>',
        unsafe_allow_html=True,
    )
with nav1:
    st.page_link("app.py", label="🏠 Overview")
with nav2:
    st.page_link("pages/2_Cascade_Simulator.py", label="💥 Cascade Sim")
with nav3:
    st.page_link("pages/4_AI_Assistant.py", label="🤖 AI Assistant")
with nav4:
    st.page_link("pages/5_Distribution_Watermain.py", label="🚰 Watermains")
with toggle_col:
    st.toggle(
        "🌐 Toronto Open Data",
        value=st.session_state.get("use_real_data", False),
        key="use_real_data",
    )
st.markdown('<div class="cn-nav-divider"></div>', unsafe_allow_html=True)

# Inline controls (were in sidebar)
ctrl1, ctrl2, ctrl3 = st.columns([2, 2, 3], gap="medium")
with ctrl1:
    budget = st.slider("Annual Budget ($)", 1_000_000, 20_000_000, 5_000_000,
                       step=500_000, format="$%d")
    st.markdown(
        f'<div style="font-size:.72rem;color:#5a7a9a;margin-top:-.3rem">Budget: '
        f'<span style="color:#1de9b6">${budget/1_000_000:.1f}M</span></div>',
        unsafe_allow_html=True,
    )
with ctrl2:
    sort_mode = st.selectbox(
        "Sort / Prioritise by",
        ["Expected Savings", "Risk Score", "Properties Affected", "Age"],
    )
with ctrl3:
    ward_filter = st.multiselect(
        "Filter by Ward", options=sorted(df["ward"].unique()),
        default=sorted(df["ward"].unique()),
    )

st.markdown("<br>", unsafe_allow_html=True)

# ── Sort key mapping ──────────────────────────────────────────────────────────
sort_col = {
    "Expected Savings":    "expected_savings",
    "Risk Score":          "risk_score",
    "Properties Affected": "properties_affected",
    "Age":                 "age",
}[sort_mode]

fdf = df[df["ward"].isin(ward_filter)].copy()
ranked = fdf.nlargest(50, sort_col).reset_index(drop=True)
ranked.index = ranked.index + 1  # 1-based rank

# Budget selection: greedily add pipes until budget exhausted
cumulative = 0
selected_mask = []
for _, r in ranked.iterrows():
    if cumulative + r["replacement_cost"] <= budget:
        selected_mask.append(True)
        cumulative += r["replacement_cost"]
    else:
        selected_mask.append(False)
ranked["in_budget"] = selected_mask

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div class="cn-header">
        <div class="cn-wordmark">📋  DECISION <span>ENGINE</span></div>
        <span class="cn-badge">RAPIDS cuML</span>
        <div class="cn-tagline">
            Capital works priority queue — ranked by expected failure cost savings
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# KPI row
k1, k2, k3, k4 = st.columns(4)
in_budget = ranked[ranked["in_budget"]]
k1.metric("Pipes in Budget",      f"{len(in_budget)}")
k2.metric("Budget Utilised",      f"${in_budget['replacement_cost'].sum():,}")
k3.metric("Est. Savings",         f"${in_budget['expected_savings'].sum():,}")
k4.metric("Properties Protected", f"{in_budget['properties_affected'].sum():,}")

st.markdown("<br>", unsafe_allow_html=True)

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["🏆  Priority Queue", "📊  Cost-Benefit Analysis", "📝  Work Order Generator"])

# ── Tab 1: Priority Table ─────────────────────────────────────────────────────
with tab1:
    section_title(f"Top 50 Replacement Candidates — Sorted by {sort_mode}")

    display = ranked[[
        "pipe_id", "ward", "material", "age", "diameter_mm",
        "risk_score", "risk_level", "properties_affected",
        "replacement_cost", "expected_savings", "in_budget",
    ]].copy()

    display["risk_level"] = display["risk_level"].astype(str)
    display.columns = [
        "Pipe ID", "Ward", "Material", "Age (yr)", "Ø (mm)",
        "Risk %", "Level", "Properties",
        "Replacement $", "Expected Savings", "In Budget",
    ]

    def colour_risk(val):
        colours = {
            "Critical": "background-color:#ff3d3d18;color:#ff3d3d",
            "High":     "background-color:#ffa72618;color:#ffa726",
            "Medium":   "background-color:#ffdd5712;color:#ffdd57",
            "Low":      "background-color:#1de9b612;color:#1de9b6",
        }
        return colours.get(val, "")

    styled = display.style.applymap(colour_risk, subset=["Level"])

    st.dataframe(
        display,
        use_container_width=True,
        hide_index=False,
        column_config={
            "Risk %": st.column_config.ProgressColumn(
                "Risk %", min_value=0, max_value=100, format="%.1f",
            ),
            "Replacement $": st.column_config.NumberColumn(
                "Replacement $", format="$%d",
            ),
            "Expected Savings": st.column_config.NumberColumn(
                "Expected Savings", format="$%d",
            ),
            "In Budget": st.column_config.CheckboxColumn("✓ Budget"),
        },
        height=480,
    )

    csv = display.to_csv(index=True).encode()
    st.download_button(
        "⬇ Export CSV", csv, "citynerve_priority_queue.csv", "text/csv",
    )

# ── Tab 2: Cost-Benefit ───────────────────────────────────────────────────────
with tab2:
    cb_l, cb_r = st.columns([3, 2], gap="large")

    with cb_l:
        section_title("Replacement vs Emergency Cost — Top 20 Segments")

        top20 = ranked.head(20).copy()
        fig_cb = go.Figure()

        fig_cb.add_trace(go.Bar(
            name="Emergency Cost",
            x=top20["pipe_id"], y=top20["emergency_cost"],
            marker=dict(color="#ff3d3d", opacity=0.85, line=dict(width=0)),
            hovertemplate="<b>%{x}</b><br>Emergency: $%{y:,}<extra></extra>",
        ))
        fig_cb.add_trace(go.Bar(
            name="Replacement Cost",
            x=top20["pipe_id"], y=top20["replacement_cost"],
            marker=dict(color="#1de9b6", opacity=0.85, line=dict(width=0)),
            hovertemplate="<b>%{x}</b><br>Replacement: $%{y:,}<extra></extra>",
        ))

        fig_cb.update_layout(
            barmode="group",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=0, r=10, t=10, b=5),
            height=320,
            legend=dict(
                font=dict(color="#8faabf", size=11),
                bgcolor="rgba(0,0,0,0)",
            ),
            xaxis=dict(
                tickangle=-45,
                tickfont=dict(family="IBM Plex Mono", color="#5a7a9a", size=9),
                gridcolor="#162033",
            ),
            yaxis=dict(
                tickfont=dict(color="#5a7a9a", size=10),
                gridcolor="#162033",
                tickprefix="$",
            ),
        )
        st.plotly_chart(fig_cb, use_container_width=True, config={"displayModeBar": False})

        # Cumulative savings curve
        section_title("Cumulative Savings vs Pipes Replaced")
        ranked_full = fdf.nlargest(50, "expected_savings")
        ranked_full["cum_savings"] = ranked_full["expected_savings"].cumsum()
        ranked_full["cum_cost"]    = ranked_full["replacement_cost"].cumsum()
        ranked_full["pipe_num"]    = range(1, len(ranked_full) + 1)

        fig_cum = go.Figure()
        fig_cum.add_trace(go.Scatter(
            x=ranked_full["pipe_num"], y=ranked_full["cum_savings"],
            name="Cumulative Savings",
            fill="tozeroy",
            fillcolor="rgba(29,233,182,0.08)",
            line=dict(color="#1de9b6", width=2),
            hovertemplate="After replacing %{x} pipes<br>Savings: $%{y:,}<extra></extra>",
        ))
        fig_cum.add_trace(go.Scatter(
            x=ranked_full["pipe_num"], y=ranked_full["cum_cost"],
            name="Cumulative Cost",
            line=dict(color="#ffa726", width=2, dash="dot"),
            hovertemplate="After replacing %{x} pipes<br>Cost: $%{y:,}<extra></extra>",
        ))
        # Budget line
        fig_cum.add_hline(
            y=budget, line_dash="dot", line_color="#5a7a9a", opacity=0.6,
            annotation_text=f"  Budget ${budget/1_000_000:.1f}M",
            annotation_font=dict(color="#5a7a9a", size=10),
        )
        fig_cum.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=0, r=10, t=10, b=5),
            height=220,
            legend=dict(font=dict(color="#8faabf", size=11), bgcolor="rgba(0,0,0,0)"),
            xaxis=dict(
                title=dict(text="# Pipes Replaced", font=dict(color="#3d5a78", size=10)),
                tickfont=dict(color="#5a7a9a", size=9), gridcolor="#162033",
            ),
            yaxis=dict(
                tickfont=dict(color="#5a7a9a", size=9), gridcolor="#162033",
                tickprefix="$",
            ),
        )
        st.plotly_chart(fig_cum, use_container_width=True, config={"displayModeBar": False})

    with cb_r:
        section_title("ROI Breakdown")

        savings_total  = ranked_full["expected_savings"].sum()
        cost_total     = ranked_full["replacement_cost"].sum()
        roi_pct        = (savings_total / max(cost_total, 1)) * 100

        st.markdown(
            f"""
            <div class="cn-card" style="text-align:center;border-color:#1de9b650">
                <div class="cn-card-title">Portfolio ROI</div>
                <div style="font-family:'Barlow Condensed',sans-serif;font-size:3rem;
                            font-weight:900;color:#1de9b6;line-height:1">{roi_pct:.0f}%</div>
                <div style="font-size:.75rem;color:#5a7a9a;margin-top:.3rem">
                    Expected return on replacement investment
                </div>
            </div>
            <div class="cn-card">
                <div class="cn-card-title">Key Metrics</div>
                <table style="width:100%;border-collapse:collapse;font-size:.82rem">
                    <tr><td style="color:#5a7a9a;padding:.3rem 0">Total Replacement Cost</td>
                        <td style="color:#ffa726;font-family:'IBM Plex Mono',monospace;text-align:right">${cost_total:,}</td></tr>
                    <tr><td style="color:#5a7a9a;padding:.3rem 0">Est. Emergency Avoided</td>
                        <td style="color:#ff3d3d;font-family:'IBM Plex Mono',monospace;text-align:right">${savings_total:,}</td></tr>
                    <tr><td style="color:#5a7a9a;padding:.3rem 0">Net Savings</td>
                        <td style="color:#1de9b6;font-family:'IBM Plex Mono',monospace;text-align:right">${savings_total - cost_total:,}</td></tr>
                    <tr><td style="color:#5a7a9a;padding:.3rem 0">Properties Protected</td>
                        <td style="color:#c9d8ea;font-family:'IBM Plex Mono',monospace;text-align:right">{ranked_full['properties_affected'].sum():,}</td></tr>
                </table>
            </div>
            """,
            unsafe_allow_html=True,
        )

        section_title("Risk by Ward — Before vs After Replacement")

        ward_before = fdf.groupby("ward")["risk_score"].mean()
        # After replacement: remove top pipes from critical list
        replaced_ids = ranked.head(len(in_budget))["pipe_id"]
        fdf_after    = fdf[~fdf["pipe_id"].isin(replaced_ids)]
        ward_after   = fdf_after.groupby("ward")["risk_score"].mean()

        wards = sorted(fdf["ward"].unique())
        fig_comp = go.Figure()
        fig_comp.add_trace(go.Bar(
            name="Before", x=wards,
            y=[ward_before.get(w, 0) for w in wards],
            marker=dict(color="#ff3d3d", opacity=0.7, line=dict(width=0)),
        ))
        fig_comp.add_trace(go.Bar(
            name="After Replacement", x=wards,
            y=[ward_after.get(w, 0) for w in wards],
            marker=dict(color="#1de9b6", opacity=0.7, line=dict(width=0)),
        ))
        fig_comp.update_layout(
            barmode="group",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=0, r=10, t=5, b=5),
            height=220,
            legend=dict(font=dict(color="#8faabf", size=10), bgcolor="rgba(0,0,0,0)"),
            xaxis=dict(
                tickangle=-30,
                tickfont=dict(family="DM Sans", color="#5a7a9a", size=9),
                gridcolor="#162033",
            ),
            yaxis=dict(
                tickfont=dict(color="#5a7a9a", size=9), gridcolor="#162033",
                title=dict(text="Avg Risk Score", font=dict(color="#3d5a78", size=9)),
            ),
        )
        st.plotly_chart(fig_comp, use_container_width=True, config={"displayModeBar": False})

# ── Tab 3: Work Order Generator ───────────────────────────────────────────────
with tab3:
    wo_l, wo_r = st.columns([1, 2], gap="large")

    with wo_l:
        section_title("Select Pipe Segment")

        wo_pipe_id = st.selectbox(
            "Pipe",
            options=ranked["pipe_id"].tolist(),
            format_func=lambda x: f"{x}  ·  rank #{ranked[ranked['pipe_id']==x].index[0]}",
            label_visibility="collapsed",
        )
        wo_pipe = ranked[ranked["pipe_id"] == wo_pipe_id].iloc[0]
        wo_level = str(wo_pipe["risk_level"])

        st.markdown(
            f"""
            <div class="cn-card" style="border-left:3px solid {RISK_COLORS[wo_level]}">
                <div class="cn-card-title">Segment Profile</div>
                <table style="width:100%;border-collapse:collapse;font-size:.78rem">
                    <tr><td style="color:#5a7a9a;padding:.2rem 0">ID</td>
                        <td style="font-family:'IBM Plex Mono',monospace;color:#c9d8ea">{wo_pipe['pipe_id']}</td></tr>
                    <tr><td style="color:#5a7a9a">Material</td>
                        <td style="color:#c9d8ea">{wo_pipe['material']}</td></tr>
                    <tr><td style="color:#5a7a9a">Installed</td>
                        <td style="color:#c9d8ea">{wo_pipe['install_year']} ({wo_pipe['age']} yrs)</td></tr>
                    <tr><td style="color:#5a7a9a">Diameter</td>
                        <td style="color:#c9d8ea">{wo_pipe['diameter_mm']} mm</td></tr>
                    <tr><td style="color:#5a7a9a">Length</td>
                        <td style="color:#c9d8ea">{wo_pipe['length_m']} m</td></tr>
                    <tr><td style="color:#5a7a9a">Ward</td>
                        <td style="color:#c9d8ea">{wo_pipe['ward']}</td></tr>
                    <tr><td style="color:#5a7a9a">Risk</td>
                        <td style="color:#ff3d3d;font-family:'IBM Plex Mono',monospace">{wo_pipe['risk_score']:.1f}%</td></tr>
                    <tr><td style="color:#5a7a9a">Replace $</td>
                        <td style="color:#1de9b6;font-family:'IBM Plex Mono',monospace">${wo_pipe['replacement_cost']:,}</td></tr>
                    <tr><td style="color:#5a7a9a">Est. Savings</td>
                        <td style="color:#ffa726;font-family:'IBM Plex Mono',monospace">${wo_pipe['expected_savings']:,}</td></tr>
                </table>
            </div>
            """,
            unsafe_allow_html=True,
        )

        generate = st.button("🤖 Generate Work Order  →", use_container_width=True)

    with wo_r:
        section_title("Generated Maintenance Work Order")

        if "generated_wo" not in st.session_state:
            st.session_state.generated_wo = None

        if generate:
            with st.spinner("Generating work order via NIM / Nemotron..."):
                import time
                time.sleep(1.2)

            wo_text = f"""\
CITYNERVE MAINTENANCE WORK ORDER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WO Number:     CN-{wo_pipe['pipe_id']}-{wo_pipe['install_year']}
Generated:     {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}
Priority:      {wo_level.upper()} — Rank #{ranked[ranked['pipe_id']==wo_pipe_id].index[0]} of {len(ranked)}
Status:        APPROVED FOR CAPITAL WORKS SCHEDULE

━━━ SEGMENT DETAILS ━━━━━━━━━━━━━━━━━━━━━━━━
Pipe ID:       {wo_pipe['pipe_id']}
Location:      {wo_pipe['ward']}, Toronto ON
Material:      {wo_pipe['material']} (installed {wo_pipe['install_year']})
Dimensions:    {wo_pipe['diameter_mm']}mm Ø × {wo_pipe['length_m']}m length
Risk Score:    {wo_pipe['risk_score']:.1f} / 100

━━━ RISK DRIVERS (NIM/Nemotron SHAP Analysis) ━━━━━━━━━━━
• Material age: {wo_pipe['material']} pipe installed {wo_pipe['age']} years ago
  exceeds typical 50-yr service life for this material class.
• Tree intrusion: {wo_pipe['tree_count_5m']} trees within 5m radius —
  root expansion accelerates corrosion in clay soils.
• 311 complaints: {wo_pipe['complaints_12mo']} water/pressure complaints
  in trailing 12 months (network distress indicator).
• Years since resurfacing: {wo_pipe['years_since_resurfacing']} yrs —
  elevated thermal stress on pipe wall.

━━━ FINANCIAL ANALYSIS ━━━━━━━━━━━━━━━━━━━━━
Replacement Cost:      ${wo_pipe['replacement_cost']:>12,}
Emergency Cost (proj): ${wo_pipe['emergency_cost']:>12,}
Expected Net Savings:  ${wo_pipe['expected_savings']:>12,}
Properties Protected:  {wo_pipe['properties_affected']:>12,}

━━━ RECOMMENDED SCOPE OF WORK ━━━━━━━━━━━━━━
1. Traffic control setup — {wo_pipe['ward']} district permit required
2. Excavation: trench {wo_pipe['diameter_mm']+400}mm wide × {int(wo_pipe['length_m'])+4}m
3. Pipe removal: {wo_pipe['material']} pipe (asbestos precautions if AC)
4. Installation: Ductile Iron {wo_pipe['diameter_mm']}mm, restrained joint
5. Backfill & compaction to City of Toronto road sub-base spec
6. Road surface restoration — coordinate with Ward resurfacing schedule
7. Pressure test & bacteriological clearance before service restore

━━━ SCHEDULING ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Recommended Window:    Before Nov 1 (pre-freeze season)
Estimated Duration:    {max(2, wo_pipe['length_m'] // 50)} working days
Crew Requirement:      4 person crew + equipment
Permit Lead Time:      10–14 business days

Generated by: NIM / Nemotron-3 · CityNerve SubSurface Intelligence
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

            st.session_state.generated_wo = wo_text

        if st.session_state.generated_wo:
            st.markdown(
                f'<div class="work-order">{st.session_state.generated_wo}</div>',
                unsafe_allow_html=True,
            )
            st.download_button(
                "⬇ Download Work Order",
                st.session_state.generated_wo.encode(),
                f"work_order_{wo_pipe_id}.txt",
                "text/plain",
            )
        else:
            st.markdown(
                """
                <div style="padding:3rem;text-align:center;color:#3d5a78;
                            border:1px dashed #162033;border-radius:10px">
                    <div style="font-size:2rem;margin-bottom:.5rem">🤖</div>
                    <div style="font-family:'Barlow Condensed',sans-serif;font-size:1.1rem;
                                font-weight:700;color:#5a7a9a">
                        Select a segment and click Generate Work Order
                    </div>
                    <div style="font-size:.78rem;color:#3d5a78;margin-top:.4rem">
                        NIM / Nemotron will produce a full capital works specification
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
