"""
pages/5_Distribution_Watermain.py — Toronto Watermain Explorer
Loads Distribution and/or Transmission Watermain GeoJSON layers from
Toronto Open Data and renders an interactive map with filters.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np

st.set_page_config(
    page_title="Toronto Watermains · CityNerve",
    page_icon="🚰",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from app_styles import inject_css, section_title
from api_client import get_watermains_layer_api
from data_utils import RISK_COLORS
from frontend.nav import render_top_nav

inject_css()

if "use_real_dist_data" not in st.session_state:
    st.session_state.use_real_dist_data = True
render_top_nav("watermains", use_real_key="use_real_dist_data")

# ── Material colour palette ────────────────────────────────────────────────────
MAT_COLORS: dict[str, str] = {
    "Cast Iron":        "#ff7043",
    "Asbestos Cement":  "#ab47bc",
    "Concrete":         "#78909c",
    "Ductile Iron":     "#26c6da",
    "PVC":              "#66bb6a",
}
DEFAULT_MAT_COLOR = "#90a4ae"
TYPE_COLORS: dict[str, str] = {
    "Transmission": "#1de9b6",
    "Distribution": "#4fc3f7",
}

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(section_title("🚰 Toronto Watermain Explorer"), unsafe_allow_html=True)
st.markdown(
    '<p style="color:#8faabf;margin-top:-0.5rem;margin-bottom:1.2rem;">'
    "Live GeoJSON · Toronto Open Data · WGS84"
    "</p>",
    unsafe_allow_html=True,
)

# ── Fetch data ────────────────────────────────────────────────────────────────
use_real = st.session_state.get("use_real_dist_data", True)
if use_real:
    layer_mode = st.radio(
        "Layer",
        ["Distribution", "Transmission", "Both"],
        horizontal=True,
        key="dm_layer_mode",
    )
else:
    layer_mode = "Synthetic"

@st.cache_data(show_spinner=False)
def _load_dist(use_real_flag: bool, layer_mode_flag: str) -> tuple[pd.DataFrame, str]:
    """Return (df, source_label). Falls back to synthetic if not in real-data mode."""
    selected_mode = layer_mode_flag if use_real_flag else "Synthetic"
    df = get_watermains_layer_api(
        use_real=use_real_flag,
        layer_mode=selected_mode,
        max_features=None,
    )
    labels = {
        "Distribution": "Toronto Open Data · Distribution Watermain GeoJSON",
        "Transmission": "Toronto Open Data · Transmission Watermain GeoJSON",
        "Both": "Toronto Open Data · Distribution + Transmission GeoJSON",
        "Synthetic": "Synthetic demo data (enable Toronto Open Data toggle for live feed)",
    }
    return df, labels.get(selected_mode, "Watermain data")


with st.spinner(f"Loading {layer_mode.lower()} watermain data…"):
    try:
        df, data_source = _load_dist(use_real, layer_mode)
    except Exception as exc:
        st.error(f"⚠️ Could not load data: {exc}")
        st.stop()

# ── KPI strip ─────────────────────────────────────────────────────────────────
n_total   = len(df)
n_mats    = df["material"].nunique()
avg_age   = int(df["age"].mean()) if "age" in df.columns else "—"
avg_diam  = int(df["diameter_mm"].mean()) if "diameter_mm" in df.columns else "—"
n_critical = int((df["risk_level"] == "Critical").sum()) if "risk_level" in df.columns else "—"

k1, k2, k3, k4, k5 = st.columns(5)
for col, label, val, unit in [
    (k1, "Segments loaded",    f"{n_total:,}",    ""),
    (k2, "Unique materials",   str(n_mats),        "types"),
    (k3, "Avg pipe age",       str(avg_age),       "yrs"),
    (k4, "Avg diameter",       str(avg_diam),      "mm"),
    (k5, "Critical risk segs", str(n_critical),    ""),
]:
    col.markdown(
        f"""
        <div style="background:#0d2137;border:1px solid #1e3a54;border-radius:10px;
                    padding:0.9rem 1.1rem;text-align:center;">
            <div style="color:#8faabf;font-size:0.72rem;text-transform:uppercase;
                        letter-spacing:.08em;margin-bottom:0.3rem;">{label}</div>
            <div style="color:#e8f4fd;font-size:1.55rem;font-weight:700;line-height:1;">
                {val}
            </div>
            <div style="color:#4fc3f7;font-size:0.72rem;margin-top:0.2rem;">{unit}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)

# ── Filters ───────────────────────────────────────────────────────────────────
fc1, fc2, fc3, fc4 = st.columns([2, 2, 2, 2])

with fc1:
    all_mats = sorted(df["material"].unique())
    mat_filter = st.multiselect("Material", all_mats, default=all_mats, key="dm_mat")

with fc2:
    diam_min = int(df["diameter_mm"].min())
    diam_max = int(df["diameter_mm"].max())
    diam_range = st.slider(
        "Diameter (mm)", diam_min, max(diam_max, diam_min + 1),
        (diam_min, diam_max), key="dm_diam",
    )

with fc3:
    yr_min = int(df["install_year"].min())
    yr_max = int(df["install_year"].max())
    yr_range = st.slider(
        "Install Year", yr_min, max(yr_max, yr_min + 1),
        (yr_min, yr_max), key="dm_yr",
    )

with fc4:
    color_options = ["Material", "Risk Level", "Diameter", "Age"]
    if "pipe_type" in df.columns and df["pipe_type"].nunique() > 1:
        color_options.insert(1, "Pipe Type")
    color_by = st.selectbox(
        "Color by",
        color_options,
        key="dm_color",
    )

type_options = sorted(df["pipe_type"].unique()) if "pipe_type" in df.columns else []
type_filter = type_options
if len(type_options) > 1:
    type_filter = st.multiselect(
        "Pipe Type",
        type_options,
        default=type_options,
        key="dm_type",
    )

# Apply filters
mask = (
    df["material"].isin(mat_filter) &
    df["diameter_mm"].between(*diam_range) &
    df["install_year"].between(*yr_range)
)
if len(type_options) > 1 and type_filter:
    mask = mask & df["pipe_type"].isin(type_filter)
dff = df[mask]

st.markdown(
    f"<p style='color:#8faabf;font-size:0.82rem;margin-bottom:0.5rem;'>"
    f"Showing <b style='color:#4fc3f7'>{len(dff):,}</b> of {n_total:,} segments · "
    f"<span style='color:#8faabf'>{data_source}</span></p>",
    unsafe_allow_html=True,
)

# ── Build map traces ───────────────────────────────────────────────────────────
fig = go.Figure()

if color_by == "Material":
    groups = dff.groupby("material")
    for mat, grp in groups:
        color = MAT_COLORS.get(mat, DEFAULT_MAT_COLOR)
        lats, lons = [], []
        for _, row in grp.iterrows():
            lats += [row["lat0"], row["lat1"], None]
            lons += [row["lon0"], row["lon1"], None]
        fig.add_trace(go.Scattermapbox(
            lat=lats, lon=lons,
            mode="lines",
            line=dict(color=color, width=1.6),
            name=mat,
            hoverinfo="name",
        ))

elif color_by == "Pipe Type":
    for ptype in ["Distribution", "Transmission"]:
        grp = dff[dff["pipe_type"] == ptype]
        if grp.empty:
            continue
        color = TYPE_COLORS.get(ptype, DEFAULT_MAT_COLOR)
        width = 2.0 if ptype == "Distribution" else 3.0
        lats, lons = [], []
        for _, row in grp.iterrows():
            lats += [row["lat0"], row["lat1"], None]
            lons += [row["lon0"], row["lon1"], None]
        fig.add_trace(go.Scattermapbox(
            lat=lats, lon=lons,
            mode="lines",
            line=dict(color=color, width=width),
            name=ptype,
            hoverinfo="name",
        ))

elif color_by == "Risk Level":
    for lvl in ["Critical", "High", "Medium", "Low"]:
        grp = dff[dff["risk_level"] == lvl]
        if grp.empty:
            continue
        color = RISK_COLORS.get(lvl, "#90a4ae")
        lats, lons = [], []
        for _, row in grp.iterrows():
            lats += [row["lat0"], row["lat1"], None]
            lons += [row["lon0"], row["lon1"], None]
        fig.add_trace(go.Scattermapbox(
            lat=lats, lon=lons,
            mode="lines",
            line=dict(color=color, width=1.6),
            name=lvl,
            hoverinfo="name",
        ))

elif color_by == "Diameter":
    # Bin into 3 bands: small / medium / large
    d33 = dff["diameter_mm"].quantile(0.33)
    d66 = dff["diameter_mm"].quantile(0.66)
    bands = [
        (f"≤{int(d33)} mm",  dff[dff["diameter_mm"] <= d33],              "#4fc3f7"),
        (f"{int(d33)+1}–{int(d66)} mm", dff[(dff["diameter_mm"] > d33) & (dff["diameter_mm"] <= d66)], "#1de9b6"),
        (f">{int(d66)} mm",  dff[dff["diameter_mm"] > d66],               "#ffa726"),
    ]
    for label, grp, color in bands:
        if grp.empty:
            continue
        lats, lons = [], []
        for _, row in grp.iterrows():
            lats += [row["lat0"], row["lat1"], None]
            lons += [row["lon0"], row["lon1"], None]
        fig.add_trace(go.Scattermapbox(
            lat=lats, lon=lons,
            mode="lines",
            line=dict(color=color, width=1.6),
            name=label,
            hoverinfo="name",
        ))

else:  # Age
    a33 = dff["age"].quantile(0.33)
    a66 = dff["age"].quantile(0.66)
    bands = [
        (f"<{int(a33)} yrs",           dff[dff["age"] < a33],                          "#66bb6a"),
        (f"{int(a33)}–{int(a66)} yrs", dff[(dff["age"] >= a33) & (dff["age"] < a66)],  "#ffa726"),
        (f">{int(a66)} yrs",           dff[dff["age"] >= a66],                          "#ff5252"),
    ]
    for label, grp, color in bands:
        if grp.empty:
            continue
        lats, lons = [], []
        for _, row in grp.iterrows():
            lats += [row["lat0"], row["lat1"], None]
            lons += [row["lon0"], row["lon1"], None]
        fig.add_trace(go.Scattermapbox(
            lat=lats, lon=lons,
            mode="lines",
            line=dict(color=color, width=1.6),
            name=label,
            hoverinfo="name",
        ))

center_lat = float(dff["lat"].mean()) if not dff.empty else 43.70
center_lon = float(dff["lon"].mean()) if not dff.empty else -79.42

fig.update_layout(
    mapbox=dict(
        style="carto-darkmatter",
        center=dict(lat=center_lat, lon=center_lon),
        zoom=11,
    ),
    paper_bgcolor="#061624",
    plot_bgcolor="#061624",
    margin=dict(l=0, r=0, t=0, b=0),
    height=560,
    legend=dict(
        bgcolor="rgba(6,22,36,0.85)",
        bordercolor="#1e3a54",
        borderwidth=1,
        font=dict(color="#e8f4fd", size=11),
        orientation="v",
        x=0.01, y=0.99,
        xanchor="left", yanchor="top",
    ),
    uirevision="dist-map",
)

st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

# ── Material breakdown table ──────────────────────────────────────────────────
st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
tb1, tb2 = st.columns([1, 1])

with tb1:
    st.markdown(section_title("📊 Material Breakdown"), unsafe_allow_html=True)
    mat_stats = (
        dff.groupby("material")
        .agg(
            Segments=("pipe_id", "count"),
            Avg_Age=("age", "mean"),
            Avg_Diameter=("diameter_mm", "mean"),
            Total_Length_km=("length_m", lambda x: round(x.sum() / 1000, 1)),
        )
        .rename(columns={"Avg_Age": "Avg Age (yrs)", "Avg_Diameter": "Avg Ø (mm)", "Total_Length_km": "Length (km)"})
        .sort_values("Segments", ascending=False)
        .reset_index()
    )
    mat_stats["Avg Age (yrs)"] = mat_stats["Avg Age (yrs)"].round(0).astype(int)
    mat_stats["Avg Ø (mm)"]    = mat_stats["Avg Ø (mm)"].round(0).astype(int)

    st.dataframe(
        mat_stats,
        use_container_width=True,
        hide_index=True,
        column_config={
            "material":      st.column_config.TextColumn("Material"),
            "Segments":      st.column_config.NumberColumn("Segments", format="%d"),
            "Avg Age (yrs)": st.column_config.NumberColumn("Avg Age (yrs)"),
            "Avg Ø (mm)":    st.column_config.NumberColumn("Avg Ø (mm)"),
            "Length (km)":   st.column_config.NumberColumn("Length (km)"),
        },
    )

with tb2:
    st.markdown(section_title("⚠️ Risk Distribution"), unsafe_allow_html=True)
    if "risk_level" in dff.columns:
        risk_stats = (
            dff.groupby("risk_level", observed=True)
            .agg(
                Segments=("pipe_id", "count"),
                Avg_Score=("risk_score", "mean"),
            )
            .rename(columns={"Avg_Score": "Avg Risk Score"})
            .reindex(["Critical", "High", "Medium", "Low"])
            .dropna(subset=["Segments"])
            .reset_index()
        )
        risk_stats["Segments"]       = risk_stats["Segments"].astype(int)
        risk_stats["Avg Risk Score"]  = risk_stats["Avg Risk Score"].round(1)
        risk_stats["% of Shown"]      = (risk_stats["Segments"] / risk_stats["Segments"].sum() * 100).round(1)

        st.dataframe(
            risk_stats,
            use_container_width=True,
            hide_index=True,
            column_config={
                "risk_level":      st.column_config.TextColumn("Risk Level"),
                "Segments":        st.column_config.NumberColumn("Segments", format="%d"),
                "Avg Risk Score":  st.column_config.NumberColumn("Avg Score", format="%.1f"),
                "% of Shown":      st.column_config.ProgressColumn("% of Total", min_value=0, max_value=100, format="%.1f%%"),
            },
        )
    else:
        st.info("Risk data not available.")

# ── Raw data explorer ─────────────────────────────────────────────────────────
with st.expander("🔍 Raw segment data", expanded=False):
    display_cols = [c for c in [
        "pipe_id", "pipe_type", "ward", "material", "diameter_mm", "length_m",
        "install_year", "age", "risk_level", "risk_score", "street",
    ] if c in dff.columns]
    st.dataframe(
        dff[display_cols].sort_values("risk_score", ascending=False)
            .head(500).reset_index(drop=True),
        use_container_width=True,
        hide_index=True,
    )
    if len(dff) > 500:
        st.caption(f"Showing first 500 of {len(dff):,} filtered rows.")
