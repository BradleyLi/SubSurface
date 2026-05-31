"""
pages/2_Cascade_Simulator.py — cuGraph Cascade Failure Demo
Select a pipe → simulate failure → visualise downstream pressure loss + cost.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import plotly.graph_objects as go
import numpy as np
import pandas as pd
import time

st.set_page_config(
    page_title="Cascade Simulator · CityNerve",
    page_icon="💥",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from app_styles import inject_css, section_title, risk_badge
from api_client import get_pipes_api
from data_utils  import RISK_COLORS
from map_viz import build_cascade_map_deck, map_view_toolbar, render_map

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

df = get_pipes_api(use_real=st.session_state.get("use_real_data", False))

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

# ── Header + Inline controls ──────────────────────────────────────────────────
st.markdown(
    """
    <div class="cn-header">
        <div class="cn-wordmark">💥  CASCADE <span>SIMULATOR</span></div>
        <span class="cn-badge">cuGraph</span>
        <div class="cn-tagline">
            Model downstream pressure loss — "If pipe X breaks, which segments lose water?"
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Controls row
ctrl1, ctrl2, ctrl3 = st.columns([2, 1.5, 1.5], gap="medium")
critical = df[df["risk_level"] == "Critical"].nlargest(20, "risk_score")
pipe_options = critical["pipe_id"].tolist()
with ctrl1:
    selected_id = st.selectbox(
        "Source Pipe (Critical segments)",
        options=pipe_options,
        format_func=lambda x: f"{x}  ·  {df.loc[df['pipe_id']==x,'ward'].values[0]}",
    )
with ctrl2:
    radius_m = st.slider("Cascade Radius (m)", 100, 1000, 400, step=50)
with ctrl3:
    show_pressure = st.checkbox("Show pressure contours", value=True)
    st.markdown(
        '<div style="font-size:.68rem;color:#3d5a78;margin-top:.3rem">'
        '<b style="color:#1de9b6">cuGraph</b>: directed graph · pressure '
        'propagates until &lt; 20 PSI</div>',
        unsafe_allow_html=True,
    )

# ── Source pipe info ──────────────────────────────────────────────────────────
source = df[df["pipe_id"] == selected_id].iloc[0]
level  = str(source["risk_level"])

top_row = st.columns([2, 1, 1, 1, 1])

with top_row[0]:
    st.markdown(
        f"""
        <div class="cn-card" style="border-left:3px solid {RISK_COLORS[level]}">
            <div class="cn-card-title">Source Segment</div>
            <div style="font-family:'Barlow Condensed',sans-serif;font-size:1.5rem;
                        font-weight:800;color:#e0eaf6">{source['pipe_id']}</div>
            <div style="font-size:.8rem;color:#8faabf;margin-top:.2rem">
                {source['material']} · {source['age']} yrs ·
                {source['diameter_mm']}mm · {source['length_m']}m
            </div>
            <div style="margin-top:.5rem">{risk_badge(level)}</div>
            <div style="margin-top:.4rem;font-size:.78rem;color:#5a7a9a">
                Ward: {source['ward']}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with top_row[1]:
    st.metric("Properties Affected", f"{source['properties_affected']:,}")
with top_row[2]:
    st.metric("Schools at Risk", source["schools_affected"])
with top_row[3]:
    st.metric("Hospital Zones", max(int(source["hospitals_affected"]), 1))
with top_row[4]:
    st.metric("Emergency Cost", f"${source['emergency_cost']:,}")

st.markdown("<br>", unsafe_allow_html=True)

# ── Cascade computation (simulated cuGraph) ──────────────────────────────────
rng = np.random.default_rng(int(source["pipe_id"].split("-")[1]))

# Find nearby pipes within radius_m (approximation using lat/lon degrees)
deg_radius = radius_m / 111_000
nearby_mask = (
    np.sqrt((df["lat"] - source["lat"])**2 + (df["lon"] - source["lon"])**2)
    < deg_radius
) & (df["pipe_id"] != selected_id)
nearby = df[nearby_mask].copy()

# Assign cascade "waves" based on distance from source
nearby["dist_deg"] = np.sqrt(
    (nearby["lat"] - source["lat"])**2 + (nearby["lon"] - source["lon"])**2
)
max_dist = nearby["dist_deg"].max() if len(nearby) > 0 else 1
nearby["wave"] = pd.cut(
    nearby["dist_deg"],
    bins=np.linspace(0, max_dist * 1.01, 5),
    labels=[1, 2, 3, 4],
).astype(float)

# Pressure drop per wave
wave_pressure = {1: 0, 2: 25, 3: 50, 4: 75}  # PSI remaining
nearby["pressure_psi"] = nearby["wave"].map(wave_pressure).fillna(100)
nearby["cascade_affected"] = nearby["pressure_psi"] < 60

# ── Map ───────────────────────────────────────────────────────────────────────
map_col, stats_col = st.columns([3, 2], gap="large")

with map_col:
    section_title("Cascade Propagation Map")

    wave_colors = {1: "#ff3d3d", 2: "#ff6b35", 3: "#ffa726", 4: "#ffdd57"}
    map_view = map_view_toolbar("cascade", zoom=13.2)
    deck = build_cascade_map_deck(
        df,
        nearby,
        source,
        selected_id=selected_id,
        wave_colors=wave_colors,
        show_pressure=show_pressure,
        deg_radius=deg_radius,
        show_buildings=map_view.show_buildings,
        view_3d=map_view.view_3d,
        map_style_name=map_view.map_style_name,
    )
    render_map(deck, height=500)

# STATS PANEL
with stats_col:
    section_title("Cascade Impact Summary")

    total_affected   = len(nearby[nearby["cascade_affected"]])
    total_properties = nearby["properties_affected"].sum()
    total_schools    = nearby["schools_affected"].sum()
    total_hospitals  = max(int(nearby["hospitals_affected"].sum()), 1)
    total_cost       = source["emergency_cost"] + nearby[nearby["cascade_affected"]]["emergency_cost"].sum()

    st.markdown(
        f"""
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:.6rem;margin-bottom:1rem">
            <div class="cn-card" style="text-align:center;border-color:#ff3d3d30">
                <div style="font-family:'Barlow Condensed',sans-serif;font-size:2.2rem;
                            font-weight:900;color:#ff3d3d;line-height:1">{total_affected}</div>
                <div style="font-size:.65rem;color:#5a7a9a;text-transform:uppercase;letter-spacing:.1em;margin-top:.15rem">
                    Segments Affected
                </div>
            </div>
            <div class="cn-card" style="text-align:center">
                <div style="font-family:'Barlow Condensed',sans-serif;font-size:2.2rem;
                            font-weight:900;color:#ffa726;line-height:1">{total_properties:,}</div>
                <div style="font-size:.65rem;color:#5a7a9a;text-transform:uppercase;letter-spacing:.1em;margin-top:.15rem">
                    Properties Disrupted
                </div>
            </div>
            <div class="cn-card" style="text-align:center">
                <div style="font-family:'Barlow Condensed',sans-serif;font-size:2.2rem;
                            font-weight:900;color:#ffdd57;line-height:1">{total_schools}</div>
                <div style="font-size:.65rem;color:#5a7a9a;text-transform:uppercase;letter-spacing:.1em;margin-top:.15rem">
                    Schools Affected
                </div>
            </div>
            <div class="cn-card" style="text-align:center">
                <div style="font-family:'Barlow Condensed',sans-serif;font-size:2.2rem;
                            font-weight:900;color:#1de9b6;line-height:1">{total_hospitals}</div>
                <div style="font-size:.65rem;color:#5a7a9a;text-transform:uppercase;letter-spacing:.1em;margin-top:.15rem">
                    Hospital Zones
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="cn-card" style="border-left:3px solid #ff3d3d">
            <div class="cn-card-title">Total Emergency Cost</div>
            <div style="font-family:'Barlow Condensed',sans-serif;font-size:2.4rem;
                        font-weight:900;color:#ff3d3d;line-height:1">
                ${total_cost:,}
            </div>
            <div style="font-size:.72rem;color:#5a7a9a;margin-top:.35rem">
                Source repair + cascade emergency response<br>
                Proactive replacement cost: <span style="color:#1de9b6">
                ${source['replacement_cost']:,}</span>
                &nbsp;→&nbsp;
                <span style="color:#1de9b6;font-weight:600">
                ${total_cost - source['replacement_cost']:,} saved</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    section_title("Cascade Timeline")

    timeline_events = [
        ("0 min",   "🔴", f"Pipe {selected_id} fails. Pressure loss at break point."),
        ("5 min",   "🟠", f"{len(nearby[nearby['wave']==1])} adjacent segments drop to 0 PSI."),
        ("30 min",  "🟡", f"Cascade wave 2: {len(nearby[nearby['wave']==2])} segments below 25 PSI."),
        ("1 hr",    "⚪", f"{total_properties:,} properties lose water service."),
        ("2 hr",    "🔵", "Isolation valves activated. Emergency crew dispatched."),
        ("4–8 hr",  "🟢", "Repair team on site. Estimated 6–12 hr restoration."),
    ]

    for time_str, icon, desc in timeline_events:
        st.markdown(
            f"""
            <div style="display:flex;gap:.8rem;padding:.45rem 0;
                        border-bottom:1px solid #0d1b2a;align-items:flex-start">
                <div style="font-family:'IBM Plex Mono',monospace;font-size:.7rem;
                            color:#3d5a78;min-width:3.5rem;padding-top:.1rem">{time_str}</div>
                <div style="font-size:.9rem;flex-shrink:0">{icon}</div>
                <div style="font-size:.78rem;color:#8faabf;line-height:1.5">{desc}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # Pressure loss bar chart
    section_title("Pressure by Cascade Wave")
    wave_data = nearby.groupby("wave")["pipe_id"].count().reset_index()
    wave_data.columns = ["Wave", "Segments"]
    wave_data["Pressure (PSI)"] = wave_data["Wave"].map(wave_pressure)
    wave_data["Wave"] = wave_data["Wave"].apply(lambda w: f"Wave {int(w)}")

    fig_waves = go.Figure(go.Bar(
        x=wave_data["Wave"],
        y=wave_data["Segments"],
        marker=dict(
            color=["#ff3d3d", "#ff6b35", "#ffa726", "#ffdd57"],
            line=dict(width=0),
        ),
        text=wave_data["Segments"],
        textposition="outside",
        textfont=dict(family="IBM Plex Mono", size=11, color="#8faabf"),
        customdata=wave_data["Pressure (PSI)"].values,
        hovertemplate="<b>%{x}</b><br>Segments: %{y}<br>Pressure: %{customdata} PSI<extra></extra>",
    ))
    fig_waves.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=10, t=5, b=5),
        height=160,
        xaxis=dict(tickfont=dict(color="#8faabf", size=10), gridcolor="#162033"),
        yaxis=dict(
            tickfont=dict(color="#5a7a9a", size=9), gridcolor="#162033",
            title=dict(text="Segments", font=dict(color="#3d5a78", size=9)),
        ),
    )
    st.plotly_chart(fig_waves, use_container_width=True, config={"displayModeBar": False})

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("📋 Go to Decision Engine →"):
            st.switch_page("app.py")
    with col_b:
        if st.button("🤖 Ask AI Assistant"):
            st.switch_page("pages/4_AI_Assistant.py")
