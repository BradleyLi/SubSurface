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
    initial_sidebar_state="expanded",
)

from app_styles import inject_css, section_title, risk_badge
from data_utils  import get_pipes, RISK_COLORS

inject_css()

df = get_pipes()

# ── Sidebar ──────────────────────────────────────────────────────────────────
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
    st.markdown('<div class="sidebar-label">Select Source Pipe</div>',
                unsafe_allow_html=True)

    # Default to highest-risk pipe
    critical = df[df["risk_level"] == "Critical"].nlargest(20, "risk_score")
    pipe_options = critical["pipe_id"].tolist()
    selected_id = st.selectbox(
        "Pipe", options=pipe_options,
        format_func=lambda x: f"{x}  ·  {df.loc[df['pipe_id']==x,'ward'].values[0]}",
        label_visibility="collapsed",
    )

    st.divider()
    st.markdown('<div class="sidebar-label">Simulation Settings</div>',
                unsafe_allow_html=True)
    radius_m = st.slider("Cascade Radius (m)", 100, 1000, 400, step=50)
    show_pressure = st.checkbox("Show pressure contours", value=True)

    st.divider()
    st.markdown(
        """
        <div style="font-size:.72rem;color:#3d5a78;line-height:1.6">
        <b style="color:#1de9b6">cuGraph</b> models the pipe network as a
        directed graph — if segment X breaks, which downstream nodes lose
        pressure?<br><br>
        Each edge carries flow capacity proportional to diameter².<br>
        Cascade propagates until pressure drops below 20 PSI.
        </div>
        """,
        unsafe_allow_html=True,
    )

# ── Header ───────────────────────────────────────────────────────────────────
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

    fig = go.Figure()

    # Background network (unaffected — grey)
    unaffected = df[~df["pipe_id"].isin(nearby["pipe_id"]) & (df["pipe_id"] != selected_id)]
    un_lats, un_lons = [], []
    for _, r in unaffected.sample(min(200, len(unaffected)), random_state=42).iterrows():
        un_lats.extend([r["lat0"], r["lat1"], None])
        un_lons.extend([r["lon0"], r["lon1"], None])
    fig.add_trace(go.Scattermap(
        lat=un_lats, lon=un_lons,
        mode="lines",
        line=dict(width=1, color="#1a2e4a"),
        name="Network",
        hoverinfo="none",
        showlegend=True,
    ))

    # Cascade rings (wave 4 → wave 1, so critical renders on top)
    wave_colors = {1: "#ff3d3d", 2: "#ff6b35", 3: "#ffa726", 4: "#ffdd57"}
    wave_labels = {1: "Critical loss (0 PSI)", 2: "Severe (25 PSI)", 3: "Moderate (50 PSI)", 4: "Minor (75 PSI)"}
    for wave in [4, 3, 2, 1]:
        sub = nearby[nearby["wave"] == wave]
        if sub.empty:
            continue
        lats, lons = [], []
        for _, r in sub.iterrows():
            lats.extend([r["lat0"], r["lat1"], None])
            lons.extend([r["lon0"], r["lon1"], None])
        fig.add_trace(go.Scattermap(
            lat=lats, lon=lons,
            mode="lines",
            line=dict(width=3.0 + (4 - wave) * 0.5, color=wave_colors[wave]),
            name=wave_labels[wave],
            hoverinfo="none",
            showlegend=True,
        ))

    # Source pipe — highlight
    fig.add_trace(go.Scattermap(
        lat=[source["lat0"], source["lat1"]],
        lon=[source["lon0"], source["lon1"]],
        mode="lines",
        line=dict(width=6, color="#ff0000"),
        name="⚡ BROKEN PIPE",
        showlegend=True,
    ))

    # Source marker (pulsing icon)
    fig.add_trace(go.Scattermap(
        lat=[source["lat"]], lon=[source["lon"]],
        mode="markers+text",
        marker=dict(size=18, color="#ff3d3d", symbol="circle"),
        text=["💥"],
        textposition="middle center",
        name="Break Point",
        showlegend=False,
        hovertemplate=f"<b>BREAK POINT</b><br>{selected_id}<br>"
                      f"Risk: {source['risk_score']:.1f}%<br>"
                      f"Emergency cost: ${source['emergency_cost']:,}<extra></extra>",
    ))

    # Pressure contour rings
    if show_pressure:
        for ring_r_deg, psi, opacity in [
            (deg_radius * 0.25, "0 PSI",  0.25),
            (deg_radius * 0.5,  "25 PSI", 0.18),
            (deg_radius * 0.75, "50 PSI", 0.12),
            (deg_radius,        "75 PSI", 0.08),
        ]:
            n_pts = 60
            theta  = np.linspace(0, 2 * np.pi, n_pts)
            r_lats = source["lat"] + ring_r_deg * np.cos(theta)
            r_lons = source["lon"] + ring_r_deg * np.sin(theta) * 1.4
            fig.add_trace(go.Scattermap(
                lat=r_lats.tolist() + [r_lats[0]],
                lon=r_lons.tolist() + [r_lons[0]],
                mode="lines",
                line=dict(width=1, color=f"rgba(255,61,61,{opacity})"),
                name=psi,
                showlegend=False,
                hoverinfo="none",
            ))

    fig.update_layout(
        map=dict(
            style="carto-darkmatter",
            center=dict(lat=source["lat"], lon=source["lon"]),
            zoom=13.5,
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=0, b=0),
        height=500,
        legend=dict(
            bgcolor="#0d1b2a",
            bordercolor="#162033",
            borderwidth=1,
            font=dict(color="#8faabf", size=10),
            x=0.01, y=0.99,
            xanchor="left", yanchor="top",
        ),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

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
        if st.button("📋 Generate Work Order"):
            st.switch_page("pages/3_Decision_Engine.py")
    with col_b:
        if st.button("🤖 Ask AI Assistant"):
            st.switch_page("pages/4_AI_Assistant.py")
