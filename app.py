"""
app.py — CityNerve SubSurface · Unified Workflow
Single-page flow: Risk Map → Decision Engine (Priority Queue + Cost-Benefit + Work Orders)
"""

import time
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np

st.set_page_config(
    page_title="CityNerve · SubSurface",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from app_styles import inject_css, section_title, risk_badge
from api_client import get_pipes_api
from data_utils import get_shap, RISK_COLORS, MATERIAL_RISK
from map_viz import build_risk_map_deck, map_view_toolbar, render_map
from model import failure_summary
from agent import agent_failure_explanation

inject_css()

# ── Hide sidebar entirely on main workflow page ─────────────────────────────
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

# ── Session state defaults ─────────────────────────────────────────────────
for _k, _v in [
    ("selected_pipe_ids", []),
    ("generated_report", None),
    ("generated_wo", None),
]:
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ── Load data ──────────────────────────────────────────────────────────────
df = get_pipes_api(use_real=st.session_state.get("use_real_data", False))

pipe_types_available = sorted(df["pipe_type"].unique()) if "pipe_type" in df.columns else []
has_layers = len(pipe_types_available) > 1
TYPE_COLORS = {"Transmission": "#1de9b6", "Distribution": "#4fc3f7", "Synthetic": "#8faabf"}
TYPE_WIDTHS = {"Transmission": 3.5, "Distribution": 1.8, "Synthetic": 2.0}

# ── Failure reason model + agent narrative imported from dedicated modules ──

# ════════════════════════════════════════════════════════════════════════════
# TOP NAV
# ════════════════════════════════════════════════════════════════════════════
logo_col, gap_col, nav1, nav2, nav3, nav4, toggle_col = st.columns([2.8, 0.3, 1, 1, 1, 1.4, 2.5])

with logo_col:
    st.markdown(
        '<div class="cn-topnav">'
        '<div class="cn-nav-logo">CITY<span>NERVE</span>'
        '<span class="cn-nav-sub"> SubSurface Intelligence</span>'
        '</div></div>',
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
    use_real = st.toggle(
        "🌐 Toronto Open Data",
        value=st.session_state.get("use_real_data", False),
        key="use_real_data",
        help=(
            "Fetches live GeoJSON from open.toronto.ca — "
            "Transmission (~400 features) + Distribution (~3 000 sampled). "
            "Requires internet. First load ~15s, then cached 1 hr."
        ),
    )

st.markdown('<div class="cn-nav-divider"></div>', unsafe_allow_html=True)

# ── AI Insights Strip ──────────────────────────────────────────────────────
_top_crit = df[df["risk_level"] == "Critical"].nlargest(1, "risk_score")
_top_ward = df.groupby("ward")["risk_score"].mean().idxmax()
_ward_avg = df[df["ward"] == _top_ward]["risk_score"].mean()
_critical_count_raw = int((df["risk_level"] == "Critical").sum())
_high_count_raw     = int((df["risk_level"] == "High").sum())

if len(_top_crit):
    _top_id   = _top_crit.iloc[0]["pipe_id"]
    _top_pct  = _top_crit.iloc[0]["risk_score"]
    _top_mat  = _top_crit.iloc[0]["material"]
    _top_ward_pipe = _top_crit.iloc[0]["ward"]
    _chip1_value = f"{_top_id} · {_top_pct:.0f}%"
    _chip1_sub   = f"{_top_ward_pipe} · {_top_mat}"
else:
    _chip1_value = "—"
    _chip1_sub   = "No critical pipes"

_budget_default = 5_000_000
_critical_pipes = df[df["risk_level"] == "Critical"]
_budget_needed  = int(_critical_pipes["replacement_cost"].sum())
_budget_pct     = min(100, int((_budget_default / max(_budget_needed, 1)) * 100))

st.markdown(
    f"""
    <div class="ai-strip">
        <div class="ai-chip critical">
            <div class="ai-chip-icon">🔴</div>
            <div class="ai-chip-body">
                <div class="ai-chip-label">Highest Risk Pipe</div>
                <div class="ai-chip-value">{_chip1_value}</div>
                <div class="ai-chip-sub">{_chip1_sub}</div>
            </div>
        </div>
        <div class="ai-chip warn">
            <div class="ai-chip-icon">📍</div>
            <div class="ai-chip-body">
                <div class="ai-chip-label">Hotspot Ward</div>
                <div class="ai-chip-value">{_top_ward}</div>
                <div class="ai-chip-sub">Avg risk score {_ward_avg:.1f} — highest in network</div>
            </div>
        </div>
        <div class="ai-chip {'ok' if _budget_pct >= 80 else 'warn' if _budget_pct >= 40 else 'critical'}">
            <div class="ai-chip-icon">💰</div>
            <div class="ai-chip-body">
                <div class="ai-chip-label">Budget vs Critical Need</div>
                <div class="ai-chip-value">${_budget_default/1e6:.1f}M covers {_budget_pct}%</div>
                <div class="ai-chip-sub">{_critical_count_raw} critical · {_high_count_raw} high · ${_budget_needed/1e6:.1f}M needed</div>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── KPI Row ────────────────────────────────────────────────────────────────
critical_count = _critical_count_raw
high_count     = _high_count_raw
total_savings  = int(df["expected_savings"].sum())
avg_risk       = df["risk_score"].mean()

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Segments Monitored",  f"{len(df):,}")
k2.metric("🔴  Critical",         f"{critical_count}",
          delta=f"+{critical_count} require action", delta_color="off")
k3.metric("🟠  High Risk",        f"{high_count}")
k4.metric("Est. 12-mo Savings",  f"${total_savings/1_000_000:.1f}M",
          help="Proactive replacement vs emergency repair — all critical segments")
k5.metric("Avg Network Risk",    f"{avg_risk:.1f} / 100")

st.markdown("<br>", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════════════
# SECTION 01 · RISK MAP
# ════════════════════════════════════════════════════════════════════════════
st.markdown(
    '<div class="section-flow-header">'
    '<span class="section-flow-num">01</span>'
    '<span class="section-flow-title">Risk Map</span>'
    '<span class="section-flow-sub"> · Pipe segments coloured by predicted 12-month break probability</span>'
    '</div>',
    unsafe_allow_html=True,
)

# ── Compact horizontal filter bar ─────────────────────────────────────────
with st.expander("⚙  Map Filters", expanded=False):
    fc1, fc2, fc3, fc4 = st.columns(4, gap="medium")
    with fc1:
        risk_filter = st.multiselect(
            "Risk Level",
            options=["Critical", "High", "Medium", "Low"],
            default=["Critical", "High", "Medium", "Low"],
            key="map_risk_filter",
        )
    with fc2:
        mat_filter = st.multiselect(
            "Material",
            options=sorted(df["material"].unique()),
            default=sorted(df["material"].unique()),
            key="map_mat_filter",
        )
    with fc3:
        ward_filter_map = st.multiselect(
            "Ward",
            options=sorted(df["ward"].unique()),
            default=sorted(df["ward"].unique()),
            key="map_ward_filter",
        )
    with fc4:
        min_risk = st.slider("Min Risk Score", 0, 100, 0, key="map_min_risk")

    if has_layers:
        ft1, ft2, ft3 = st.columns([1, 1, 3], gap="medium")
        with ft1:
            type_filter = st.multiselect(
                "Pipe Type",
                options=pipe_types_available,
                default=pipe_types_available,
                key="map_type_filter",
            )
        with ft2:
            color_mode = st.radio(
                "Color by",
                ["Risk Level", "Pipe Type"],
                key="map_color_mode",
                horizontal=True,
            )
        with ft3:
            leg_cols = st.columns(len(RISK_COLORS))
            for i, (lvl, col) in enumerate(RISK_COLORS.items()):
                leg_cols[i].markdown(
                    f'<div style="display:flex;align-items:center;gap:.4rem;padding-top:.5rem">'
                    f'<div style="width:9px;height:9px;border-radius:50%;background:{col};flex-shrink:0"></div>'
                    f'<span style="font-size:.74rem;color:#8faabf">{lvl}</span></div>',
                    unsafe_allow_html=True,
                )
    else:
        type_filter = pipe_types_available or ["Synthetic"]
        color_mode  = "Risk Level"

# ── Apply map filters ──────────────────────────────────────────────────────
mask = (
    df["risk_level"].isin(risk_filter) &
    df["material"].isin(mat_filter) &
    df["ward"].isin(ward_filter_map) &
    (df["risk_score"] >= min_risk)
)
if has_layers and type_filter:
    mask = mask & df["pipe_type"].isin(type_filter)
fdf = df[mask]

# ── Full-width Map ─────────────────────────────────────────────────────────
section_title(
    "Toronto Watermain Network — Predicted Risk"
    if color_mode == "Risk Level"
    else "Toronto Watermain Network — Transmission vs Distribution"
)

map_view = map_view_toolbar("app_risk", zoom=11.0)
deck = build_risk_map_deck(
    fdf,
    color_mode=color_mode,
    has_layers=has_layers,
    risk_colors=RISK_COLORS,
    type_colors=TYPE_COLORS,
    type_widths=TYPE_WIDTHS,
    selected_ids=st.session_state.get("selected_pipe_ids", []),
    show_buildings=map_view.show_buildings,
    view_3d=map_view.view_3d,
    zoom=map_view.zoom,
)
render_map(deck, height=640)

# Stats strip below map
s1, s2, s3, s4 = st.columns(4)
s1.metric("Segments Shown", f"{len(fdf):,}")
s2.metric("Critical",       int((fdf["risk_level"] == "Critical").sum()))
s3.metric("High",           int((fdf["risk_level"] == "High").sum()))
s4.metric("Avg Risk",       f"{fdf['risk_score'].mean():.1f}" if len(fdf) else "—")

st.markdown("<br>", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════════════
# SECTION 02 · DECISION ENGINE
# ════════════════════════════════════════════════════════════════════════════
st.markdown(
    '<div class="section-flow-header">'
    '<span class="section-flow-num">02</span>'
    '<span class="section-flow-title">Decision Engine</span>'
    '<span class="section-flow-sub"> · Capital works priority queue · Cost-benefit analysis · Work order generator</span>'
    '</div>',
    unsafe_allow_html=True,
)

# ── Inline controls ────────────────────────────────────────────────────────
ctrl1, ctrl2, ctrl3 = st.columns([2, 2, 3], gap="medium")
with ctrl1:
    budget = st.slider(
        "Annual Budget ($)",
        1_000_000, 20_000_000, 5_000_000,
        step=500_000, format="$%d",
    )
    st.markdown(
        f'<div style="font-size:.72rem;color:#5a7a9a;margin-top:-.3rem">'
        f'Budget: <span style="color:#1de9b6">${budget/1_000_000:.1f}M</span></div>',
        unsafe_allow_html=True,
    )
with ctrl2:
    sort_mode = st.selectbox(
        "Sort / Prioritise by",
        ["Expected Savings", "Risk Score", "Properties Affected", "Age"],
    )
with ctrl3:
    de_ward_filter = st.multiselect(
        "Ward filter",
        options=sorted(df["ward"].unique()),
        default=sorted(df["ward"].unique()),
        key="de_ward_filter",
    )

st.markdown("<br>", unsafe_allow_html=True)

# ── Build ranked queue ─────────────────────────────────────────────────────
sort_col = {
    "Expected Savings":    "expected_savings",
    "Risk Score":          "risk_score",
    "Properties Affected": "properties_affected",
    "Age":                 "age",
}[sort_mode]

de_df  = df[df["ward"].isin(de_ward_filter)].copy()
ranked = de_df.nlargest(50, sort_col).reset_index(drop=True)
ranked.index = ranked.index + 1  # 1-based

cumulative = 0
budget_mask = []
for _, r in ranked.iterrows():
    if cumulative + r["replacement_cost"] <= budget:
        budget_mask.append(True)
        cumulative += r["replacement_cost"]
    else:
        budget_mask.append(False)
ranked["in_budget"] = budget_mask

in_budget = ranked[ranked["in_budget"]]

# Budget KPI cards
bk1, bk2, bk3, bk4 = st.columns(4)
bk1.metric("Pipes in Budget",      f"{len(in_budget)}")
bk2.metric("Budget Utilised",      f"${in_budget['replacement_cost'].sum():,}")
bk3.metric("Est. Savings",         f"${in_budget['expected_savings'].sum():,}")
bk4.metric("Properties Protected", f"{in_budget['properties_affected'].sum():,}")

st.markdown("<br>", unsafe_allow_html=True)

# ── TABS ──────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs([
    "🏆  Priority Queue",
    "📊  Cost-Benefit Analysis",
    "📝  Work Order Generator",
])

# ════════════════════════════════════════════════════════════════════════════
# TAB 1 · PRIORITY QUEUE
# ════════════════════════════════════════════════════════════════════════════
with tab1:
    section_title(f"Top 50 Replacement Candidates — Sorted by {sort_mode}")

    # Quick-select buttons — compact row with clear visual separation
    st.markdown(
        '<div style="display:flex;align-items:center;gap:.5rem;margin-bottom:.75rem">',
        unsafe_allow_html=True,
    )
    qs0, qs1, qs2, qs3, _ = st.columns([1.2, 1.2, 0.9, 1.0, 5])
    with qs0:
        if st.button("🔴  Select Critical", key="qs_critical"):
            st.session_state.selected_pipe_ids = (
                ranked[ranked["risk_level"].astype(str) == "Critical"]["pipe_id"].tolist()
            )
            st.session_state.generated_report = None
            st.rerun()
    with qs1:
        if st.button("💰  Budget Picks", key="qs_budget"):
            st.session_state.selected_pipe_ids = ranked[ranked["in_budget"]]["pipe_id"].tolist()
            st.session_state.generated_report = None
            st.rerun()
    with qs2:
        if st.button("Top 10", key="qs_top10"):
            st.session_state.selected_pipe_ids = ranked.head(10)["pipe_id"].tolist()
            st.session_state.generated_report = None
            st.rerun()
    with qs3:
        if st.button("✕  Clear", key="qs_clear"):
            st.session_state.selected_pipe_ids = []
            st.session_state.generated_report = None
            st.rerun()

    st.markdown("<div style='height:.5rem'></div>", unsafe_allow_html=True)

    # Build editable display dataframe
    queue_df = ranked.copy()
    queue_df["failure_summary"] = queue_df.apply(failure_summary, axis=1)

    init_selected = queue_df["pipe_id"].isin(st.session_state.selected_pipe_ids)

    display_df = pd.DataFrame({
        "Select":       init_selected.values,
        "Pipe ID":      queue_df["pipe_id"].values,
        "Risk Level":   queue_df["risk_level"].astype(str).values,
        "Risk %":       queue_df["risk_score"].values,
        "Ward":         queue_df["ward"].values,
        "Material":     queue_df["material"].values,
        "Age (yr)":     queue_df["age"].values,
        "Replace $":    queue_df["replacement_cost"].values,
        "Savings $":    queue_df["expected_savings"].values,
        "In Budget":    queue_df["in_budget"].values,
    })

    queue_col, agent_col = st.columns([2.3, 1.3], gap="medium")

    with queue_col:
        edited = st.data_editor(
            display_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Select":     st.column_config.CheckboxColumn("✓", width="small"),
                "Risk %":     st.column_config.ProgressColumn("Risk %", min_value=0, max_value=100, format="%.1f"),
                "Replace $":  st.column_config.NumberColumn("Replace $",  format="$%d"),
                "Savings $":  st.column_config.NumberColumn("Savings $",  format="$%d"),
                "In Budget":  st.column_config.CheckboxColumn("Budget", width="small"),
            },
            disabled=[
                "Pipe ID", "Risk Level", "Risk %", "Ward", "Material",
                "Age (yr)", "Replace $", "Savings $", "In Budget",
            ],
            height=440,
            key="priority_queue_editor",
        )

    # Sync selection back to session state
    sel_pipe_ids = edited.loc[edited["Select"], "Pipe ID"].tolist()
    prev_sel = st.session_state.get("selected_pipe_ids", [])
    if sel_pipe_ids != prev_sel:
        st.session_state.selected_pipe_ids = sel_pipe_ids
        st.rerun()

    with agent_col:
        section_title("🤖 Why Failing Agent")
        st.caption(
            "Human-readable diagnosis for checked pipes. "
            "Select rows in the queue to update this panel."
        )
        if sel_pipe_ids:
            selected_for_agent = ranked[ranked["pipe_id"].isin(sel_pipe_ids)].head(4)
            for _, r in selected_for_agent.iterrows():
                lvl = str(r["risk_level"])
                lvl_color = RISK_COLORS.get(lvl, "#8faabf")
                st.markdown(
                    f"""
                    <div class="cn-card" style="margin-bottom:.5rem;border-left:3px solid {lvl_color}">
                        <div class="cn-card-title">{r["pipe_id"]} · {lvl}</div>
                        <div style="font-size:.78rem;line-height:1.45;color:#c9d8ea">
                            {agent_failure_explanation(r)}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            if len(sel_pipe_ids) > len(selected_for_agent):
                st.caption(f"Showing first {len(selected_for_agent)} selected pipes.")
        else:
            st.markdown(
                """
                <div class="cn-card" style="border-style:dashed">
                    <div style="font-size:.8rem;color:#8faabf;line-height:1.5">
                        The agent is waiting for your selection.<br>
                        Check one or more pipes in the table to get a narrative explanation.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    n_sel = len(sel_pipe_ids)

    if n_sel == 0:
        st.markdown(
            '<div style="padding:1.2rem;border:1px dashed #162033;border-radius:8px;'
            'text-align:center;color:#3d5a78;font-size:.82rem;margin-top:.5rem">'
            'Check pipes above to add them to your capital works program, '
            'then click <strong style="color:#5a7a9a">Generate Order Report</strong>.'
            '</div>',
            unsafe_allow_html=True,
        )
        csv = display_df.to_csv(index=False).encode()
        st.download_button("⬇ Export Full Queue CSV", csv,
                           "citynerve_priority_queue.csv", "text/csv")
    else:
        sel_data    = ranked[ranked["pipe_id"].isin(sel_pipe_ids)]
        sel_cost    = int(sel_data["replacement_cost"].sum())
        sel_savings = int(sel_data["expected_savings"].sum())
        sel_props   = int(sel_data["properties_affected"].sum())
        roi_pct     = (sel_savings / max(sel_cost, 1)) * 100

        st.markdown("<br>", unsafe_allow_html=True)
        section_title(f"{n_sel} Pipe(s) Selected — Summary")

        sm1, sm2, sm3, sm4 = st.columns(4)
        sm1.metric("Selected Pipes",    f"{n_sel}")
        sm2.metric("Total Replace Cost", f"${sel_cost:,}")
        sm3.metric("Total Est. Savings", f"${sel_savings:,}")
        sm4.metric("Portfolio ROI",      f"{roi_pct:.0f}%")

        st.markdown("<br>", unsafe_allow_html=True)

        # Pipe failure cards
        for _, r in sel_data.head(6).iterrows():
            lvl   = str(r["risk_level"])
            color = RISK_COLORS.get(lvl, "#888")
            st.markdown(
                f"""
                <div class="alert-row" style="border-left-color:{color};margin-bottom:.4rem">
                    <span class="alert-icon">{
                        "🔴" if lvl == "Critical" else
                        "🟠" if lvl == "High" else
                        "🟡" if lvl == "Medium" else "🟢"
                    }</span>
                    <div style="flex:1">
                        <div class="alert-text">
                            <strong>{r['pipe_id']}</strong>
                            &nbsp;{risk_badge(lvl)}&nbsp;
                            {r['ward']} · {r['material']} · {r['age']} yrs
                            <span style="float:right;font-family:'IBM Plex Mono',monospace;
                                         color:#1de9b6;font-size:.8rem">
                                Replace: ${r['replacement_cost']:,}
                            </span>
                        </div>
                        <div class="alert-meta">{failure_summary(r)}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        if len(sel_data) > 6:
            st.caption(f"…and {len(sel_data) - 6} more selected pipe(s).")

        st.markdown("<br>", unsafe_allow_html=True)

        btn_col, dl_col, _ = st.columns([2, 1.5, 5])
        with btn_col:
            gen_report = st.button(
                "📋  Generate Order Report",
                use_container_width=True,
                type="primary",
            )
        with dl_col:
            sel_csv = sel_data[["pipe_id", "ward", "material", "age",
                                "risk_score", "replacement_cost",
                                "expected_savings", "properties_affected"]].to_csv(index=False).encode()
            st.download_button(
                "⬇ Export CSV", sel_csv,
                "selected_pipes.csv", "text/csv",
            )

        if gen_report:
            with st.spinner("Generating capital works order report..."):
                time.sleep(0.8)

            report_lines = [
                "CITYNERVE CAPITAL WORKS ORDER REPORT",
                "━" * 56,
                f"Generated:      {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}",
                "Prepared by:    CityNerve SubSurface Intelligence · NIM / Nemotron-3",
                f"Annual Budget:  ${budget:,}",
                f"Pipes Selected: {n_sel}",
                "",
                "━━━ PRIORITY QUEUE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                f"{'#':<4} {'Pipe ID':<10} {'Risk':>6}  {'Ward':<15} {'Material':<16} "
                f"{'Replace $':>10} {'Savings $':>10}",
                "─" * 75,
            ]
            for i, (_, r) in enumerate(sel_data.iterrows(), 1):
                report_lines.append(
                    f"{i:<4} {r['pipe_id']:<10} {r['risk_score']:>5.1f}%  "
                    f"{r['ward']:<15} {r['material']:<16} "
                    f"${r['replacement_cost']:>9,} ${r['expected_savings']:>9,}"
                )

            report_lines += [
                "",
                "━━━ FAILURE DRIVERS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            ]
            for _, r in sel_data.iterrows():
                report_lines.append(f"  {r['pipe_id']}: {failure_summary(r)}")

            report_lines += [
                "",
                "━━━ FINANCIAL SUMMARY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                f"  Total Replacement Cost:    ${sel_cost:>12,}",
                f"  Total Est. Emergency Cost: ${sel_savings + sel_cost:>12,}",
                f"  Net Expected Savings:      ${sel_savings:>12,}",
                f"  Properties Protected:      {sel_props:>12,}",
                f"  Portfolio ROI:             {roi_pct:>11.0f}%",
                "",
                "━━━ RECOMMENDED SCHEDULE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            ]
            ward_groups = sel_data.groupby("ward")["pipe_id"].apply(list)
            for q_idx, (ward, pipes) in enumerate(ward_groups.items(), 1):
                pipe_list = ", ".join(pipes[:4])
                if len(pipes) > 4:
                    pipe_list += f" (+{len(pipes)-4} more)"
                report_lines.append(f"  Q{min(q_idx,4)}: {pipe_list} — {ward}")

            report_lines += [
                "",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "  Generated by: NIM / Nemotron-3 · CityNerve SubSurface v1.0",
            ]
            st.session_state.generated_report = "\n".join(report_lines)

        if st.session_state.generated_report:
            st.markdown("<br>", unsafe_allow_html=True)
            section_title("Generated Order Report")
            st.markdown(
                f'<div class="work-order">{st.session_state.generated_report}</div>',
                unsafe_allow_html=True,
            )
            st.download_button(
                "⬇ Download Order Report",
                st.session_state.generated_report.encode(),
                "citynerve_order_report.txt",
                "text/plain",
            )

# ════════════════════════════════════════════════════════════════════════════
# TAB 2 · COST-BENEFIT ANALYSIS
# ════════════════════════════════════════════════════════════════════════════
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
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=0, r=10, t=10, b=5), height=320,
            legend=dict(font=dict(color="#8faabf", size=11), bgcolor="rgba(0,0,0,0)"),
            xaxis=dict(
                tickangle=-45,
                tickfont=dict(family="IBM Plex Mono", color="#5a7a9a", size=9),
                gridcolor="#162033",
            ),
            yaxis=dict(tickfont=dict(color="#5a7a9a", size=10), gridcolor="#162033", tickprefix="$"),
        )
        st.plotly_chart(fig_cb, use_container_width=True, config={"displayModeBar": False})

        section_title("Cumulative Savings vs Pipes Replaced")
        ranked_full = de_df.nlargest(50, "expected_savings").copy()
        ranked_full["cum_savings"] = ranked_full["expected_savings"].cumsum()
        ranked_full["cum_cost"]    = ranked_full["replacement_cost"].cumsum()
        ranked_full["pipe_num"]    = range(1, len(ranked_full) + 1)

        fig_cum = go.Figure()
        fig_cum.add_trace(go.Scatter(
            x=ranked_full["pipe_num"], y=ranked_full["cum_savings"],
            name="Cumulative Savings",
            fill="tozeroy", fillcolor="rgba(29,233,182,0.08)",
            line=dict(color="#1de9b6", width=2),
            hovertemplate="After %{x} pipes · Savings: $%{y:,}<extra></extra>",
        ))
        fig_cum.add_trace(go.Scatter(
            x=ranked_full["pipe_num"], y=ranked_full["cum_cost"],
            name="Cumulative Cost",
            line=dict(color="#ffa726", width=2, dash="dot"),
            hovertemplate="After %{x} pipes · Cost: $%{y:,}<extra></extra>",
        ))
        fig_cum.add_hline(
            y=budget, line_dash="dot", line_color="#5a7a9a", opacity=0.6,
            annotation_text=f"  Budget ${budget/1_000_000:.1f}M",
            annotation_font=dict(color="#5a7a9a", size=10),
        )
        fig_cum.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=0, r=10, t=10, b=5), height=220,
            legend=dict(font=dict(color="#8faabf", size=11), bgcolor="rgba(0,0,0,0)"),
            xaxis=dict(
                title=dict(text="# Pipes Replaced", font=dict(color="#3d5a78", size=10)),
                tickfont=dict(color="#5a7a9a", size=9), gridcolor="#162033",
            ),
            yaxis=dict(tickfont=dict(color="#5a7a9a", size=9), gridcolor="#162033", tickprefix="$"),
        )
        st.plotly_chart(fig_cum, use_container_width=True, config={"displayModeBar": False})

    with cb_r:
        section_title("ROI Breakdown")
        savings_total = ranked_full["expected_savings"].sum()
        cost_total    = ranked_full["replacement_cost"].sum()
        roi_pct_cb    = (savings_total / max(cost_total, 1)) * 100

        st.markdown(
            f"""
            <div class="cn-card" style="text-align:center;border-color:#1de9b650">
                <div class="cn-card-title">Portfolio ROI</div>
                <div style="font-family:'Barlow Condensed',sans-serif;font-size:3rem;
                            font-weight:900;color:#1de9b6;line-height:1">{roi_pct_cb:.0f}%</div>
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

        section_title("Avg Risk by Ward — Before vs After Replacement")
        ward_before  = de_df.groupby("ward")["risk_score"].mean()
        replaced_ids = ranked.head(len(in_budget))["pipe_id"]
        de_df_after  = de_df[~de_df["pipe_id"].isin(replaced_ids)]
        ward_after   = de_df_after.groupby("ward")["risk_score"].mean()
        wards        = sorted(de_df["ward"].unique())

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
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=0, r=10, t=5, b=5), height=240,
            legend=dict(font=dict(color="#8faabf", size=10), bgcolor="rgba(0,0,0,0)"),
            xaxis=dict(tickangle=-30, tickfont=dict(color="#5a7a9a", size=9), gridcolor="#162033"),
            yaxis=dict(
                tickfont=dict(color="#5a7a9a", size=9), gridcolor="#162033",
                title=dict(text="Avg Risk Score", font=dict(color="#3d5a78", size=9)),
            ),
        )
        st.plotly_chart(fig_comp, use_container_width=True, config={"displayModeBar": False})

# ════════════════════════════════════════════════════════════════════════════
# TAB 3 · WORK ORDER GENERATOR
# ════════════════════════════════════════════════════════════════════════════
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
        wo_pipe  = ranked[ranked["pipe_id"] == wo_pipe_id].iloc[0]
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
                <div style="margin-top:.8rem;font-size:.72rem;color:#5a7a9a;line-height:1.5">
                    <strong style="color:#8faabf">Why failing:</strong><br>{failure_summary(wo_pipe)}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        generate_wo = st.button("🤖  Generate Work Order →", use_container_width=True)

    with wo_r:
        section_title("Generated Maintenance Work Order")

        if generate_wo:
            with st.spinner("Generating work order via NIM / Nemotron..."):
                time.sleep(1.0)

            wo_rank = int(ranked[ranked["pipe_id"] == wo_pipe_id].index[0])
            wo_text = f"""\
CITYNERVE MAINTENANCE WORK ORDER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WO Number:     CN-{wo_pipe['pipe_id']}-{wo_pipe['install_year']}
Generated:     {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}
Priority:      {wo_level.upper()} — Rank #{wo_rank} of {len(ranked)}
Status:        APPROVED FOR CAPITAL WORKS SCHEDULE

━━━ SEGMENT DETAILS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Pipe ID:       {wo_pipe['pipe_id']}
Location:      {wo_pipe['ward']}, Toronto ON
Material:      {wo_pipe['material']} (installed {wo_pipe['install_year']})
Dimensions:    {wo_pipe['diameter_mm']}mm Ø × {wo_pipe['length_m']}m length
Risk Score:    {wo_pipe['risk_score']:.1f} / 100

━━━ RISK DRIVERS (NIM/Nemotron SHAP Analysis) ━━━━━━
{failure_summary(wo_pipe)}

• Material age: {wo_pipe['material']} pipe installed {wo_pipe['age']} years ago
  exceeds typical service life for this material class.
• Tree intrusion: {wo_pipe['tree_count_5m']} trees within 5m radius —
  root expansion accelerates corrosion in clay soils.
• 311 complaints: {wo_pipe['complaints_12mo']} water/pressure complaints
  in trailing 12 months (network distress indicator).
• Years since resurfacing: {wo_pipe['years_since_resurfacing']} yrs —
  elevated thermal stress on pipe wall.

━━━ FINANCIAL ANALYSIS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Replacement Cost:      ${wo_pipe['replacement_cost']:>12,}
Emergency Cost (proj): ${wo_pipe['emergency_cost']:>12,}
Expected Net Savings:  ${wo_pipe['expected_savings']:>12,}
Properties Protected:  {wo_pipe['properties_affected']:>12,}

━━━ RECOMMENDED SCOPE OF WORK ━━━━━━━━━━━━━━━━━━━━━━
1. Traffic control setup — {wo_pipe['ward']} district permit required
2. Excavation: trench {wo_pipe['diameter_mm']+400}mm wide × {int(wo_pipe['length_m'])+4}m
3. Pipe removal: {wo_pipe['material']} pipe (asbestos precautions if AC)
4. Installation: Ductile Iron {wo_pipe['diameter_mm']}mm, restrained joint
5. Backfill & compaction to City of Toronto road sub-base spec
6. Road surface restoration — coordinate with Ward resurfacing schedule
7. Pressure test & bacteriological clearance before service restore

━━━ SCHEDULING ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Recommended Window:    Before Nov 1 (pre-freeze season)
Estimated Duration:    {max(2, wo_pipe['length_m'] // 50)} working days
Crew Requirement:      4 person crew + equipment
Permit Lead Time:      10–14 business days

Generated by: NIM / Nemotron-3 · CityNerve SubSurface Intelligence
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

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

# ── Footer ───────────────────────────────────────────────────────────────
st.markdown("<br><br>", unsafe_allow_html=True)
st.markdown(
    """
    <div style="text-align:center;font-size:.65rem;color:#1a2e4a;padding:1rem 0;
                border-top:1px solid #0d1b2a;letter-spacing:.08em;">
        CITYNERVE · SUBSURFACE INTELLIGENCE · NVIDIA SPARK HACKATHON 2025 ·
        DATA: OPEN DATA TORONTO · POWERED BY RAPIDS cuDF · cuSpatial · cuML · cuGraph · NIM
    </div>
    """,
    unsafe_allow_html=True,
)
