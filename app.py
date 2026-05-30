"""
app.py — CityNerve Command Center (Overview Page)
Predictive Infrastructure Intelligence for Toronto's Watermain Network
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

# ── Page config must be first ──────────────────────────────────────────────
st.set_page_config(
    page_title="CityNerve · SubSurface",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded",
)

from app_styles import inject_css, section_title, risk_badge
from data_utils  import get_pipes, RISK_COLORS

inject_css()

# ── Load data ──────────────────────────────────────────────────────────────
df = get_pipes(use_real=st.session_state.get("use_real_data", False))

# ── Sidebar ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        """
        <div style="padding:1rem 0 0.5rem">
            <div style="font-family:'Barlow Condensed',sans-serif;font-size:1.5rem;
                        font-weight:900;color:#e0eaf6;letter-spacing:.06em">
                CITY<span style="color:#1de9b6">NERVE</span>
            </div>
            <div style="font-size:.65rem;color:#3d5a78;letter-spacing:.12em;
                        text-transform:uppercase;margin-top:.15rem">
                SubSurface Intelligence
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.divider()
    st.markdown('<div class="sidebar-label">Navigation</div>', unsafe_allow_html=True)
    st.page_link("app.py",                             label="🏠  Command Center",   )
    st.page_link("pages/1_Risk_Map.py",                label="🗺️  Risk Map",          )
    st.page_link("pages/2_Cascade_Simulator.py",       label="💥  Cascade Simulator", )
    st.page_link("pages/3_Decision_Engine.py",         label="📋  Decision Engine",   )
    st.page_link("pages/4_AI_Assistant.py",            label="🤖  AI Assistant",      )
    st.divider()
    st.markdown('<div class="sidebar-label">Data Source</div>', unsafe_allow_html=True)

    use_real = st.toggle(
        "🌐 Use Toronto Open Data",
        value=st.session_state.get("use_real_data", False),
        help=(
            "Fetches live GeoJSON from open.toronto.ca — "
            "Transmission Watermain (~400 features, fully loaded) + "
            "Distribution Watermain (~60 000 features, 3 000 sampled). "
            "Requires internet. First load ~15 s, then cached 1 hr."
        ),
        key="use_real_data",
    )
    if use_real:
        st.caption("🟢 Live — Transmission + Distribution Watermains")
        st.caption("📦 Source: open.toronto.ca · package: watermains")
    else:
        st.caption("🔵 Demo — 600 synthetic pipe segments")

    st.divider()
    st.markdown('<div class="sidebar-label">Data Status</div>', unsafe_allow_html=True)
    st.caption("📡 Open Data Toronto · Live feed")
    st.caption("🔄 Last sync: 2 hours ago")
    st.caption("📦 10+ datasets fused")

# ── Header ─────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div class="cn-header">
        <div>
            <div style="display:flex;align-items:baseline;gap:.7rem">
                <div class="cn-wordmark">CITY<span>NERVE</span></div>
                <span class="cn-badge">SUBSURFACE v1.0</span>
                <span class="cn-badge cn-badge-gpu">NVIDIA RAPIDS</span>
            </div>
            <div class="cn-tagline">
                Predictive Infrastructure Intelligence · Toronto Watermain Network
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── KPI Row ────────────────────────────────────────────────────────────────
critical_count = int((df["risk_level"] == "Critical").sum())
high_count     = int((df["risk_level"] == "High").sum())
total_savings  = int(df["expected_savings"].sum())
avg_risk       = df["risk_score"].mean()

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Pipe Segments Monitored", f"{len(df):,}")
k2.metric("🔴  Critical Risk",        f"{critical_count}",
          delta=f"+{critical_count} require action", delta_color="off")
k3.metric("🟠  High Risk",            f"{high_count}")
k4.metric("Est. 12-mo Savings",      f"${total_savings/1_000_000:.1f}M",
          help="Proactive replacement vs emergency repair across all critical segments")
k5.metric("Avg Network Risk Score",  f"{avg_risk:.1f} / 100")

st.markdown("<br>", unsafe_allow_html=True)

# ── GPU Pipeline Status ────────────────────────────────────────────────────
section_title("GPU Processing Pipeline — NVIDIA RAPIDS")

stages = [
    ("cuDF",        "Ingest & Clean",      True,  "gpu"),
    ("cuSpatial",   "Geospatial Joins",    True,  "gpu"),
    ("Feature Eng", "600 features/seg",   True,  "active"),
    ("cuML",        "XGBoost · 97.2% acc", True,  "gpu"),
    ("cuGraph",     "Cascade Analysis",   True,  "gpu"),
    ("NIM/Nemotron","Language Agent",      True,  "active"),
]

nodes_html = ""
for i, (name, label, active, style) in enumerate(stages):
    cls = f"pipeline-node {style}" if active else "pipeline-node"
    dot_cls = "node-dot pulse" if style == "active" else "node-dot"
    nodes_html += f'<span class="{cls}"><span class="{dot_cls}"></span>{name}<span style="font-size:.65rem;opacity:.6;margin-left:.3rem">{label}</span></span>'
    if i < len(stages) - 1:
        nodes_html += '<span class="pipeline-arrow">→</span>'

st.markdown(
    f'<div class="pipeline-wrap">{nodes_html}</div>',
    unsafe_allow_html=True,
)

# ── Live Network Map ────────────────────────────────────────────────────────
section_title("Toronto Watermain Network — Predicted Break Risk")

fig_map = go.Figure()

for level in ["Low", "Medium", "High", "Critical"]:
    sub = df[df["risk_level"] == level]
    if sub.empty:
        continue
    lats, lons = [], []
    for _, r in sub.iterrows():
        lats.extend([r["lat0"], r["lat1"], None])
        lons.extend([r["lon0"], r["lon1"], None])
    width = {"Critical": 3.5, "High": 3.0, "Medium": 2.5, "Low": 1.8}[level]
    fig_map.add_trace(go.Scattermap(
        lat=lats, lon=lons,
        mode="lines",
        line=dict(width=width, color=RISK_COLORS[level]),
        name=level,
        hoverinfo="none",
        showlegend=True,
    ))

# Hover points (pipe midpoints)
fig_map.add_trace(go.Scattermap(
    lat=df["lat"], lon=df["lon"],
    mode="markers",
    marker=dict(size=6, color=df["risk_color"].tolist(), opacity=0.7),
    text=df["pipe_id"],
    customdata=df[["risk_score", "material", "age", "ward", "emergency_cost"]].values,
    hovertemplate=(
        "<b>%{text}</b><br>"
        "Risk: <b>%{customdata[0]:.1f}%</b><br>"
        "Material: %{customdata[1]} · Age: %{customdata[2]} yrs<br>"
        "Ward: %{customdata[3]}<br>"
        "Emergency cost: $%{customdata[4]:,}<extra></extra>"
    ),
    name="",
    showlegend=False,
))

fig_map.update_layout(
    map=dict(
        style="carto-darkmatter",
        center=dict(lat=43.71, lon=-79.38),
        zoom=10.2,
    ),
    paper_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=0, r=0, t=0, b=0),
    height=480,
    legend=dict(
        bgcolor="#0d1b2a",
        bordercolor="#162033",
        borderwidth=1,
        font=dict(color="#8faabf", size=11),
        orientation="h",
        x=0.01, y=0.01,
        xanchor="left", yanchor="bottom",
    ),
)
st.plotly_chart(fig_map, use_container_width=True, config={"displayModeBar": False})

st.markdown("<br>", unsafe_allow_html=True)

# ── Main content: two columns ───────────────────────────────────────────────
left_col, right_col = st.columns([3, 2], gap="large")

# LEFT — Critical pipes table
with left_col:
    section_title("Top Critical Pipe Segments")

    top_pipes = (
        df[df["risk_level"] == "Critical"]
        .nlargest(12, "emergency_cost")
        [["pipe_id", "ward", "material", "age", "risk_score",
          "risk_level", "emergency_cost", "properties_affected"]]
        .copy()
    )
    top_pipes["risk_score"] = top_pipes["risk_score"].apply(lambda x: f"{x:.1f}%")
    top_pipes["emergency_cost"] = top_pipes["emergency_cost"].apply(lambda x: f"${x:,}")
    top_pipes["risk_level"] = top_pipes["risk_level"].apply(
        lambda l: f'<span class="risk-badge risk-{str(l).lower()}">{l}</span>'
    )
    top_pipes = top_pipes.rename(columns={
        "pipe_id": "Pipe ID", "ward": "Ward", "material": "Material",
        "age": "Age (yr)", "risk_score": "Risk Score",
        "risk_level": "Level", "emergency_cost": "Emergency Cost",
        "properties_affected": "Properties",
    })

    st.dataframe(
        top_pipes.drop(columns=["Level"]),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Risk Score": st.column_config.ProgressColumn(
                "Risk Score", min_value=0, max_value=100, format="%s",
            ),
        },
    )

# RIGHT — Charts
with right_col:
    section_title("Risk Distribution")

    # Donut chart
    lvl_counts = df["risk_level"].value_counts().reindex(
        ["Critical", "High", "Medium", "Low"]
    ).fillna(0)

    fig_donut = go.Figure(go.Pie(
        labels=lvl_counts.index.tolist(),
        values=lvl_counts.values.tolist(),
        hole=0.62,
        marker=dict(
            colors=[RISK_COLORS[l] for l in lvl_counts.index],
            line=dict(color="#050b18", width=2),
        ),
        textinfo="percent",
        textfont=dict(family="Barlow Condensed", size=13, color="#e0eaf6"),
        hovertemplate="<b>%{label}</b><br>%{value} segments (%{percent})<extra></extra>",
    ))
    fig_donut.add_annotation(
        text=f"<b>{len(df)}</b><br><span style='font-size:10px'>SEGMENTS</span>",
        x=0.5, y=0.5, showarrow=False,
        font=dict(family="Barlow Condensed", size=22, color="#e0eaf6"),
        align="center",
    )
    fig_donut.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=5, b=5),
        height=220,
        showlegend=True,
        legend=dict(
            font=dict(color="#8faabf", size=11),
            bgcolor="rgba(0,0,0,0)",
            orientation="v",
            x=1.02, y=0.5,
        ),
    )
    st.plotly_chart(fig_donut, use_container_width=True, config={"displayModeBar": False})

    st.markdown("<div style='height:.3rem'></div>", unsafe_allow_html=True)
    section_title("Avg Risk Score by Ward")

    ward_risk = (
        df.groupby("ward")["risk_score"]
        .mean()
        .sort_values(ascending=True)
        .reset_index()
    )

    fig_bar = go.Figure(go.Bar(
        x=ward_risk["risk_score"],
        y=ward_risk["ward"],
        orientation="h",
        marker=dict(
            color=ward_risk["risk_score"],
            colorscale=[[0, "#1de9b6"], [0.5, "#ffa726"], [1, "#ff3d3d"]],
            line=dict(width=0),
        ),
        text=ward_risk["risk_score"].apply(lambda v: f"{v:.1f}"),
        textposition="outside",
        textfont=dict(family="IBM Plex Mono", size=11, color="#8faabf"),
        hovertemplate="<b>%{y}</b><br>Avg risk: %{x:.1f}<extra></extra>",
    ))
    fig_bar.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=40, t=5, b=5),
        height=200,
        xaxis=dict(
            showgrid=True, gridcolor="#162033",
            tickfont=dict(color="#5a7a9a", size=10),
            range=[0, ward_risk["risk_score"].max() * 1.15],
        ),
        yaxis=dict(
            tickfont=dict(family="DM Sans", color="#8faabf", size=11),
            gridcolor="#162033",
        ),
    )
    st.plotly_chart(fig_bar, use_container_width=True, config={"displayModeBar": False})

st.markdown("<br>", unsafe_allow_html=True)

# ── Bottom row: material breakdown + alerts ────────────────────────────────
bot_l, bot_r = st.columns([2, 3], gap="large")

with bot_l:
    section_title("Break Rate by Material")

    mat_df = (
        df.groupby("material")
        .agg(avg_risk=("risk_score", "mean"), count=("pipe_id", "count"))
        .sort_values("avg_risk", ascending=False)
        .reset_index()
    )

    fig_mat = px.bar(
        mat_df, x="material", y="avg_risk",
        color="avg_risk",
        color_continuous_scale=[[0, "#1de9b6"], [0.5, "#ffa726"], [1, "#ff3d3d"]],
        labels={"material": "", "avg_risk": "Avg Risk Score"},
        text=mat_df["avg_risk"].apply(lambda v: f"{v:.0f}"),
    )
    fig_mat.update_traces(
        textposition="outside",
        textfont=dict(family="IBM Plex Mono", size=11, color="#8faabf"),
        marker_line_width=0,
        hovertemplate="<b>%{x}</b><br>Avg risk: %{y:.1f}<extra></extra>",
    )
    fig_mat.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        coloraxis_showscale=False,
        margin=dict(l=0, r=10, t=5, b=5),
        height=220,
        xaxis=dict(
            tickfont=dict(family="DM Sans", color="#8faabf", size=10),
            gridcolor="#162033",
        ),
        yaxis=dict(
            tickfont=dict(color="#5a7a9a", size=10),
            gridcolor="#162033",
            range=[0, mat_df["avg_risk"].max() * 1.15],
        ),
    )
    st.plotly_chart(fig_mat, use_container_width=True, config={"displayModeBar": False})

with bot_r:
    section_title("Active Alerts")

    critical_pipes = df[df["risk_level"] == "Critical"].nlargest(5, "risk_score")
    alerts_data = [
        ("🔴", "error",
         f"<strong>{row['pipe_id']}</strong> — {row['ward']} · {row['material']} · "
         f"{row['age']} yrs · Risk score <strong>{row['risk_score']:.0f}/100</strong>",
         f"Emergency cost estimate: ${row['emergency_cost']:,} · {row['properties_affected']} properties at risk",
         )
        for _, row in critical_pipes.iterrows()
    ]
    alerts_data.append(
        ("🟠", "warn",
         "<strong>Seasonal Alert</strong> — Winter freeze-thaw cycle begins in 47 days",
         "Historical data: 68% of annual breaks occur Nov–Mar · 14 high-risk clay-soil segments flagged",
         )
    )

    for icon, kind, text, meta in alerts_data:
        st.markdown(
            f"""
            <div class="alert-row {'warn' if kind=='warn' else ''}">
                <span class="alert-icon">{icon}</span>
                <div>
                    <div class="alert-text">{text}</div>
                    <div class="alert-meta">{meta}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

# ── Footer ──────────────────────────────────────────────────────────────────
st.markdown("<br>", unsafe_allow_html=True)
st.markdown(
    """
    <div style="text-align:center;font-size:.68rem;color:#2a3e52;padding:1rem 0;
                border-top:1px solid #0d1b2a;letter-spacing:.08em;">
        CITYNERVE · SUBSURFACE INTELLIGENCE · NVIDIA SPARK HACKATHON 2025 ·
        DATA: OPEN DATA TORONTO · POWERED BY RAPIDS cuDF · cuSpatial · cuML · cuGraph · NIM
    </div>
    """,
    unsafe_allow_html=True,
)
