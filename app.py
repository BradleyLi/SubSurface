"""
app.py — CityNerve SubSurface · Unified Workflow
Single-page flow: Risk Map → Decision Engine (Priority Queue + Cost-Benefit + Work Orders)
"""

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

from app_styles import begin_filter_panel, inject_css, section_title, risk_badge
from agent.voice_pipe_match import find_pipe_for_latest_transcript
from api_client import get_pipes_api
from data_utils import RISK_COLORS
from model import failure_summary
from frontend.nav import render_top_nav, reconcile_multiselect_filter
from frontend.order_report_ui import render_order_report_panel
from frontend.report import (
    MAX_NEMOTRON_PIPES,
    build_order_report_view_model,
    build_work_order_text,
)
from frontend.voice_events import render_voice_transcript_rerun_listener
from frontend.workflow1_ui import render_pipe_summaries_panel

inject_css()
render_voice_transcript_rerun_listener(key="overview_voice_transcript_events")

# ── Session state defaults ─────────────────────────────────────────────────
for _k, _v in [
    ("selected_pipe_ids", []),
    ("generated_report", None),
    ("generated_report_vm", None),
    ("report_generating", False),
    ("generated_wo", None),
]:
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ── Top nav + data ─────────────────────────────────────────────────────────
use_real = render_top_nav("overview")
df = get_pipes_api(use_real=use_real)

ml_snapshot_year = None
if use_real and "prediction_date" in df.columns and df["prediction_date"].notna().any():
    ml_snapshot_year = str(df["prediction_date"].iloc[0])[:4]
_snapshot_suffix = (
    f" · {ml_snapshot_year} ML snapshot" if ml_snapshot_year else ""
)

pipe_types_available = sorted(df["pipe_type"].unique()) if "pipe_type" in df.columns else []
has_layers = len(pipe_types_available) > 1
TYPE_COLORS = {"Transmission": "#1de9b6", "Distribution": "#4fc3f7", "Synthetic": "#8faabf"}
TYPE_WIDTHS = {"Transmission": 3.5, "Distribution": 1.8, "Synthetic": 2.0}

# ── Failure reason model + agent narrative imported from dedicated modules ──

# ── KPI Row ────────────────────────────────────────────────────────────────
critical_count = int((df["risk_level"] == "Critical").sum())
high_count     = int((df["risk_level"] == "High").sum())
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

map_col, filter_col = st.columns([3, 1], gap="medium")

# ── Filter panel ───────────────────────────────────────────────────────────
with filter_col:
    begin_filter_panel()
    section_title("Map Filters")

    _mat_options = sorted(df["material"].unique())
    reconcile_multiselect_filter("map_mat_filter", _mat_options)
    _ward_options = sorted(df["ward"].unique())
    reconcile_multiselect_filter("map_ward_filter", _ward_options)
    reconcile_multiselect_filter("map_risk_filter", ["Critical", "High", "Medium", "Low"])

    risk_filter = st.multiselect(
        "Risk Level",
        options=["Critical", "High", "Medium", "Low"],
        default=["Critical", "High", "Medium", "Low"],
        key="map_risk_filter",
    )
    mat_filter = st.multiselect(
        "Material",
        options=_mat_options,
        default=_mat_options,
        key="map_mat_filter",
    )
    ward_filter_map = st.multiselect(
        "Ward",
        options=_ward_options,
        default=_ward_options,
        key="map_ward_filter",
    )
    min_risk = st.slider("Min Risk Score", 0, 100, 0, key="map_min_risk")

    if has_layers:
        st.divider()
        type_filter = st.multiselect(
            "Pipe Type",
            options=pipe_types_available,
            default=pipe_types_available,
            key="map_type_filter",
        )
        color_mode = st.radio(
            "Color by",
            ["Risk Level", "Pipe Type"],
            key="map_color_mode",
            horizontal=True,
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

_voice_payload, _app_voice_match = find_pipe_for_latest_transcript(df)

# ── Map ────────────────────────────────────────────────────────────────────
with map_col:
    section_title(
        "Toronto Watermain Network — Predicted Risk"
        if color_mode == "Risk Level"
        else "Toronto Watermain Network — Transmission vs Distribution"
    )

    fig = go.Figure()
    risk_base_widths = {"Critical": 3.5, "High": 3.0, "Medium": 2.5, "Low": 2.0}

    if color_mode == "Pipe Type" and has_layers:
        for ptype in ["Distribution", "Transmission"]:
            sub = fdf[fdf["pipe_type"] == ptype]
            if sub.empty:
                continue
            lats, lons = [], []
            for _, r in sub.iterrows():
                lats.extend([r["lat0"], r["lat1"], None])
                lons.extend([r["lon0"], r["lon1"], None])
            fig.add_trace(go.Scattermap(
                lat=lats, lon=lons, mode="lines",
                line=dict(width=TYPE_WIDTHS[ptype], color=TYPE_COLORS[ptype]),
                name=ptype, hoverinfo="none", showlegend=True,
            ))
    else:
        for level in ["Critical", "High", "Medium", "Low"]:
            color      = RISK_COLORS[level]
            base_width = risk_base_widths[level]
            if has_layers:
                for idx, ptype in enumerate(["Distribution", "Transmission"]):
                    sub = fdf[(fdf["risk_level"] == level) & (fdf["pipe_type"] == ptype)]
                    if sub.empty:
                        continue
                    lats, lons = [], []
                    for _, r in sub.iterrows():
                        lats.extend([r["lat0"], r["lat1"], None])
                        lons.extend([r["lon0"], r["lon1"], None])
                    fig.add_trace(go.Scattermap(
                        lat=lats, lon=lons, mode="lines",
                        line=dict(width=base_width + (0.8 if ptype == "Transmission" else 0), color=color),
                        name=level, legendgroup=level,
                        showlegend=(idx == 1), hoverinfo="none",
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
                    lat=lats, lon=lons, mode="lines",
                    line=dict(width=base_width, color=color),
                    name=level, hoverinfo="none", showlegend=True,
                ))

    if not fdf.empty:
        fig.add_trace(go.Scattermap(
            lat=fdf["lat"], lon=fdf["lon"], mode="markers",
            marker=dict(size=6, color=fdf["risk_color"].tolist(), opacity=0.0),
            text=fdf["pipe_id"],
            customdata=fdf[["risk_score", "material", "age", "ward",
                            "risk_level", "diameter_mm", "emergency_cost",
                            "pipe_type"]].values,
            hovertemplate=(
                "<b>%{text}</b><br>"
                "Risk Score: <b>%{customdata[0]:.1f}%</b><br>"
                "Material: %{customdata[1]} · Age: %{customdata[2]} yrs<br>"
                "Ward: %{customdata[3]}<br>"
                "Emergency Cost: $%{customdata[6]:,}<extra></extra>"
            ),
            name="", showlegend=False,
        ))

    # Highlight pipes selected in the Priority Queue checkboxes.
    selected_ids = st.session_state.get("selected_pipe_ids", [])
    selected_on_map = fdf[fdf["pipe_id"].isin(selected_ids)] if selected_ids else fdf.iloc[0:0]
    if not selected_on_map.empty:
        sel_lats, sel_lons = [], []
        for _, r in selected_on_map.iterrows():
            sel_lats.extend([r["lat0"], r["lat1"], None])
            sel_lons.extend([r["lon0"], r["lon1"], None])

        # Outer light stroke creates contrast on dark basemap and colored pipes.
        fig.add_trace(go.Scattermap(
            lat=sel_lats, lon=sel_lons,
            mode="lines",
            line=dict(width=8, color="rgba(232,244,253,0.75)"),
            hoverinfo="none",
            showlegend=False,
        ))
        # Inner accent line identifies checked pipes clearly.
        fig.add_trace(go.Scattermap(
            lat=sel_lats, lon=sel_lons,
            mode="lines",
            line=dict(width=4.6, color="#ff4fd8"),
            name=f"Checked Pipes ({len(selected_on_map)})",
            hoverinfo="none",
            showlegend=True,
        ))
        # Visible markers on top so hover works on checked pipes (lines above use hoverinfo=none).
        fig.add_trace(go.Scattermap(
            lat=selected_on_map["lat"],
            lon=selected_on_map["lon"],
            mode="markers",
            marker=dict(size=14, color="#ff4fd8", opacity=0.92),
            text=selected_on_map["pipe_id"],
            customdata=selected_on_map[[
                "risk_score", "material", "age", "ward",
                "risk_level", "diameter_mm", "emergency_cost", "pipe_type",
            ]].values,
            hovertemplate=(
                "<b>%{text}</b> (checked)<br>"
                "Risk Score: <b>%{customdata[0]:.1f}%</b> · %{customdata[4]}<br>"
                "Material: %{customdata[1]} · Age: %{customdata[2]} yrs<br>"
                "Ward: %{customdata[3]} · Type: %{customdata[7]}<br>"
                "Diameter: %{customdata[5]} mm<br>"
                "Emergency Cost: $%{customdata[6]:,}<extra></extra>"
            ),
            name="",
            showlegend=False,
        ))

    if _app_voice_match is not None and _app_voice_match.lat is not None:
        fig.add_trace(go.Scattermap(
            lat=[_app_voice_match.lat], lon=[_app_voice_match.lon], mode="markers",
            marker=dict(size=32, color="#f97316", opacity=0.20),
            hoverinfo="none", showlegend=False,
        ))
        fig.add_trace(go.Scattermap(
            lat=[_app_voice_match.lat], lon=[_app_voice_match.lon], mode="markers",
            marker=dict(size=14, color="#f97316", opacity=0.95, symbol="circle"),
            name="Active Caller Report",
            hovertemplate=(
                f"<b>Active Caller Report</b><br>"
                f"Matched pipe: {_app_voice_match.pipe_id}<br>"
                f"Confidence: {_app_voice_match.confidence:.0%}<extra></extra>"
            ),
            showlegend=True,
        ))

    fig.update_layout(
        map=dict(
            style="carto-darkmatter",
            center=dict(lat=43.70, lon=-79.38),
            zoom=10.2,
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=0, b=0),
        height=530,
        legend=dict(
            bgcolor="#0d1b2a", bordercolor="#162033", borderwidth=1,
            font=dict(color="#8faabf", size=11),
            orientation="v", x=0.01, y=0.99,
            xanchor="left", yanchor="top",
        ),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # Stats strip below map
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Segments Shown", f"{len(fdf):,}")
    s2.metric("Critical",       int((fdf["risk_level"] == "Critical").sum()))
    s3.metric("High",           int((fdf["risk_level"] == "High").sum()))
    s4.metric("Avg Risk",       f"{fdf['risk_score'].mean():.1f}" if len(fdf) else "—")

    checked_ids = st.session_state.get("selected_pipe_ids", [])
    if checked_ids:
        checked_rows = df[df["pipe_id"].isin(checked_ids)].sort_values(
            "risk_score", ascending=False
        )
        on_map_ids = set(fdf["pipe_id"]) if not fdf.empty else set()
        hidden_n = sum(1 for pid in checked_ids if pid not in on_map_ids)
        section_title(f"Checked Pipes ({len(checked_ids)})")
        if hidden_n:
            st.caption(
                f"{hidden_n} checked pipe(s) are hidden by map filters — "
                "widen Risk Level / Ward filters above to see them on the map."
            )
        for _, r in checked_rows.head(6).iterrows():
            lvl = str(r["risk_level"])
            color = RISK_COLORS.get(lvl, "#888")
            on_map = r["pipe_id"] in on_map_ids
            st.markdown(
                f"""
                <div class="alert-row" style="border-left-color:{color};margin-bottom:.35rem">
                    <span class="alert-icon">{
                        "🔴" if lvl == "Critical" else
                        "🟠" if lvl == "High" else
                        "🟡" if lvl == "Medium" else "🟢"
                    }</span>
                    <div style="flex:1">
                        <div class="alert-text">
                            <strong>{r['pipe_id']}</strong>
                            &nbsp;{risk_badge(lvl)}&nbsp;
                            <span style="font-family:'IBM Plex Mono',monospace;color:#1de9b6">
                                {r['risk_score']:.1f}% risk
                            </span>
                            {"&nbsp;<span style='color:#5a7a9a;font-size:.72rem'>· on map</span>"
                             if on_map else
                             "&nbsp;<span style='color:#ffa726;font-size:.72rem'>· filtered off map</span>"}
                        </div>
                        <div class="alert-meta">
                            {r['ward']} · {r['material']} · {int(r['age'])} yrs ·
                            {int(r['diameter_mm'])} mm · {r.get('pipe_type', '—')}
                        </div>
                        <div class="alert-meta">{failure_summary(r)}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        if len(checked_rows) > 6:
            st.caption(f"…and {len(checked_rows) - 6} more checked pipe(s) in the queue below.")

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
    section_title(f"Top 50 Replacement Candidates — Sorted by {sort_mode}{_snapshot_suffix}")

    # Quick-select buttons
    qs0, qs1, qs2, qs3, _ = st.columns([1.1, 1.1, 1.1, 1.0, 4])
    with qs0:
        if st.button("Select Critical", key="qs_critical"):
            st.session_state.selected_pipe_ids = (
                ranked[ranked["risk_level"].astype(str) == "Critical"]["pipe_id"].tolist()
            )
            st.session_state.generated_report = None
            st.session_state.generated_report_vm = None
            st.session_state.report_generating = False
            st.rerun()
    with qs1:
        if st.button("Budget Picks", key="qs_budget"):
            st.session_state.selected_pipe_ids = ranked[ranked["in_budget"]]["pipe_id"].tolist()
            st.session_state.generated_report = None
            st.session_state.generated_report_vm = None
            st.session_state.report_generating = False
            st.rerun()
    with qs2:
        if st.button("Top 10", key="qs_top10"):
            st.session_state.selected_pipe_ids = ranked.head(10)["pipe_id"].tolist()
            st.session_state.generated_report = None
            st.session_state.generated_report_vm = None
            st.session_state.report_generating = False
            st.rerun()
    with qs3:
        if st.button("Clear All", key="qs_clear"):
            st.session_state.selected_pipe_ids = []
            st.session_state.generated_report = None
            st.session_state.generated_report_vm = None
            st.session_state.report_generating = False
            st.rerun()

    st.markdown("<div style='height:.5rem'></div>", unsafe_allow_html=True)

    # Build editable display dataframe
    queue_df = ranked.copy()
    queue_df["failure_summary"] = queue_df.apply(failure_summary, axis=1)

    init_selected = queue_df["pipe_id"].isin(st.session_state.selected_pipe_ids)

    has_ml_risk = (
        "predicted_break_probability" in queue_df.columns
        and queue_df["predicted_break_probability"].notna().any()
    )

    display_cols: dict[str, object] = {
        "Select":     init_selected.values,
        "Pipe ID":    queue_df["pipe_id"].values,
        "Risk Level": queue_df["risk_level"].astype(str).values,
    }
    if has_ml_risk:
        display_cols["Break Prob %"] = (
            queue_df["predicted_break_probability"] * 100
        ).round(1).values
        display_cols["Percentile"] = queue_df["risk_percentile"].round(1).values
    else:
        display_cols["Risk %"] = queue_df["risk_score"].values
    display_cols.update({
        "Ward":      queue_df["ward"].values,
        "Material":  queue_df["material"].values,
        "Age (yr)":  queue_df["age"].values,
        "Replace $": queue_df["replacement_cost"].values,
        "Savings $": queue_df["expected_savings"].values,
        "In Budget": queue_df["in_budget"].values,
    })
    display_df = pd.DataFrame(display_cols)

    risk_column_config: dict[str, st.column_config.Column] = {}
    disabled_risk_cols: list[str] = []
    if has_ml_risk:
        risk_column_config = {
            "Break Prob %": st.column_config.ProgressColumn(
                "Break Prob %", min_value=0, max_value=100, format="%.1f",
                help="12-month predicted break probability from the XGBoost model",
            ),
            "Percentile": st.column_config.ProgressColumn(
                "Percentile", min_value=0, max_value=100, format="%.1f",
                help="Network-wide risk percentile (used for risk level bands)",
            ),
        }
        disabled_risk_cols = ["Break Prob %", "Percentile"]
    else:
        risk_column_config = {
            "Risk %": st.column_config.ProgressColumn(
                "Risk %", min_value=0, max_value=100, format="%.1f",
            ),
        }
        disabled_risk_cols = ["Risk %"]

    if _app_voice_match is not None:
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
        incident = (_voice_payload or {}).get("incident") or {}
        loc = incident.get("location") if isinstance(incident, dict) else None
        addr = (
            loc.get("address", "reported location")
            if isinstance(loc, dict)
            else "reported location"
        )
        st.markdown(
            f'<div class="voice-alert" style="margin-bottom:1rem">'
            f'<span class="voice-dot"></span>'
            f'<strong>Active Caller Report</strong> — {addr}<br>'
            f'<span style="color:#9ba8b5;font-size:.76rem">'
            f'Matched to <strong>{_app_voice_match.pipe_id}</strong> · '
            f'{_app_voice_match.confidence:.0%} · {_app_voice_match.method}'
            f'</span></div>',
            unsafe_allow_html=True,
        )

    queue_col, agent_col = st.columns([2.3, 1.3], gap="medium")

    with queue_col:
        edited = st.data_editor(
            display_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Select":     st.column_config.CheckboxColumn("✓", width="small"),
                **risk_column_config,
                "Replace $":  st.column_config.NumberColumn("Replace $",  format="$%d"),
                "Savings $":  st.column_config.NumberColumn("Savings $",  format="$%d"),
                "In Budget":  st.column_config.CheckboxColumn("Budget", width="small"),
            },
            disabled=[
                "Pipe ID", "Risk Level", *disabled_risk_cols, "Ward", "Material",
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

    n_sel = len(sel_pipe_ids)

    with agent_col:
        section_title("Pipe Summaries")
        st.caption(
            "Workflow 1 · Nemotron Nano (:11436). One summary card per selected pipe; "
            "badge shows ● Nemotron W1 when ready (~20–50s)."
        )
        selected_for_agent = (
            ranked[ranked["pipe_id"].isin(sel_pipe_ids)] if sel_pipe_ids else ranked.iloc[0:0]
        )
        render_pipe_summaries_panel(
            selected_for_agent,
            use_real=use_real,
            df=de_df,
            max_cards=4,
        )

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
        section_title(f"{n_sel} Pipe(s) Selected — Capital Program")
        st.caption(
            "Selection totals and queue detail below. "
            "Per-pipe Nemotron summaries are in **Pipe Summaries** (right). "
            "Click **Generate Order Report** for the full capital works report."
        )

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
            st.session_state.report_generating = True
            st.session_state.generated_report_vm = None
            st.session_state.generated_report = None
            st.rerun()

        if st.session_state.get("report_generating"):
            report_progress = st.empty()
            with report_progress.container():
                with st.status(
                    "Generating capital works order report…",
                    expanded=True,
                ) as report_status:
                    n_w1 = min(n_sel, MAX_NEMOTRON_PIPES)
                    report_status.write(
                        f"Loading Nemotron W1 intelligence for up to {n_w1} pipe(s) "
                        "(cached summaries are reused)…"
                    )
                    _voice_payload, voice_match = find_pipe_for_latest_transcript(df)
                    vm = build_order_report_view_model(
                        sel_data,
                        budget=budget,
                        use_real=use_real,
                        session_state=st.session_state,
                    )
                    report_status.write("Assembling capital program tables and financial summary…")
                    st.session_state.generated_report_vm = vm
                    st.session_state.generated_report = vm["plain_text"]
                    report_status.update(
                        label="Capital works order report ready",
                        state="complete",
                        expanded=False,
                    )
            st.session_state.report_generating = False

        if st.session_state.get("generated_report_vm"):
            st.markdown("<br>", unsafe_allow_html=True)
            section_title("Generated Order Report")
            render_order_report_panel(st.session_state.generated_report_vm)
            st.download_button(
                "⬇ Download plain-text report",
                st.session_state.generated_report_vm["plain_text"].encode(),
                "citynerve_order_report.txt",
                "text/plain",
                key="dl_order_report",
            )
        elif st.session_state.generated_report:
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
            _ranked = ranked.reset_index(drop=True)
            wo_rank = int(_ranked.index[_ranked["pipe_id"] == wo_pipe_id][0]) + 1
            with st.spinner("Fetching Nemotron W1 risk summary for work order…"):
                st.session_state.generated_wo = build_work_order_text(
                    wo_pipe,
                    wo_rank=wo_rank,
                    queue_len=len(ranked),
                    use_real=use_real,
                    session_state=st.session_state,
                )

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
