"""
map_viz.py — Uber-style geospatial maps (deck.gl + Mapbox via pydeck).

Mapbox dark-v10 is used for 3D buildings:
  - pydeck bundles Mapbox GL JS v2, which renders fill-extrusion from dark-v10 correctly.
  - dark-v11 switched to Mapbox's new v3 slot-based building system (GL JS v3 only) so
    buildings silently fail inside pydeck/Streamlit — hence we pin to dark-v10.
  - Mapbox Standard is NOT used (requires GL JS v3, crashes pydeck).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

import pandas as pd
import pydeck as pdk

# Map style options — all work with Mapbox GL JS v2 (bundled in pydeck).
# Only dark-v10 and night-v1 include fill-extrusion buildings.
# Carto Dark Matter is the absolute darkest but has no 3D buildings.
MAP_STYLES: dict[str, tuple[str, str, bool]] = {
    # label: (url, provider, has_buildings)
    "Dark":            ("mapbox://styles/mapbox/dark-v10",                                    "mapbox", True),
    "Night":           ("mapbox://styles/mapbox/navigation-night-v1",                         "mapbox", True),
    "Satellite":       ("mapbox://styles/mapbox/satellite-streets-v12",                       "mapbox", False),
    "Carto (darkest)": ("https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",  "carto",  False),
}
MAPBOX_DARK = MAP_STYLES["Dark"][0]     # default
CARTO_DARK  = MAP_STYLES["Carto (darkest)"][0]

TORONTO_CENTER = (43.70, -79.38)
DEFAULT_ZOOM = 11.0
# Buildings in dark-v10 begin rendering at zoom ≥ 14 with pitch > 0.
BUILDINGS_MIN_ZOOM = 14.0
DEFAULT_PITCH_3D = 52
DEFAULT_PITCH_FLAT = 0
DEFAULT_PITCH_ANGLED = 30
DEFAULT_BEARING = -12

RISK_LINE_WIDTHS = {"Critical": 5, "High": 4, "Medium": 3, "Low": 2}
TYPE_LINE_WIDTHS = {"Transmission": 5, "Distribution": 3, "Synthetic": 3}

SELECT_OUTLINE_RGBA = [232, 244, 253, 200]
SELECT_ACCENT_RGBA = [255, 79, 216, 255]

PIPE_TOOLTIP = {
    "html": (
        "<b style='color:#1de9b6'>{pipe_id}</b><br/>"
        "Risk <b>{risk_score}</b> · {risk_level}<br/>"
        "{material} · {age} yrs · {ward}"
    ),
    "style": {
        "backgroundColor": "#0d1b2a",
        "color": "#e0eaf6",
        "fontSize": "12px",
    },
}

CASCADE_TOOLTIP = {
    "html": "<b>{pipe_id}</b><br/>Wave {wave}",
    "style": {
        "backgroundColor": "#0d1b2a",
        "color": "#e0eaf6",
        "fontSize": "12px",
    },
}


@dataclass
class MapViewOptions:
    show_buildings: bool = True
    view_3d: bool = True
    zoom: float = DEFAULT_ZOOM
    map_style_name: str = "Dark"


def _valid_mapbox_token(val: str) -> str | None:
    val = val.strip().strip('"').strip("'")
    if val.startswith("pk.") and "your_mapbox" not in val:
        return val
    return None


def mapbox_token() -> str | None:
    """Resolve Mapbox token from env or .streamlit/secrets.toml."""
    for key in ("MAPBOX_API_KEY", "MapboxAccessToken"):
        tok = _valid_mapbox_token(os.environ.get(key, ""))
        if tok:
            return tok

    try:
        import streamlit as st

        if hasattr(st, "secrets"):
            for key in ("MAPBOX_API_KEY", "MAPBOX_TOKEN"):
                if key in st.secrets:
                    tok = _valid_mapbox_token(str(st.secrets[key]))
                    if tok:
                        return tok
            if "mapbox" in st.secrets:
                raw = st.secrets["mapbox"]
                if isinstance(raw, dict):
                    tok = _valid_mapbox_token(str(raw.get("token", "")))
                else:
                    tok = _valid_mapbox_token(str(raw))
                if tok:
                    return tok
    except Exception:
        pass
    return None


def has_mapbox() -> bool:
    return mapbox_token() is not None


def _sanitize(val: Any) -> Any:
    """Convert numpy scalars to native Python for deck.gl JSON."""
    if hasattr(val, "item"):
        try:
            return val.item()
        except Exception:
            pass
    if isinstance(val, float) and val != val:
        return 0
    return val


def _pitch_and_bearing(view_3d: bool) -> tuple[float, float]:
    if view_3d:
        return DEFAULT_PITCH_3D, DEFAULT_BEARING
    return DEFAULT_PITCH_FLAT, 0


def hex_to_rgba(hex_color: str, alpha: int = 220) -> list[int]:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return [r, g, b, alpha]


def _line_records(
    sub: pd.DataFrame,
    *,
    color: list[int],
    meta_cols: Sequence[str] | None = None,
) -> list[dict]:
    """One dict per segment: source/target for LineLayer, full path for PathLayer."""
    if sub.empty:
        return []
    pick_cols = list(meta_cols or ["pipe_id", "risk_score", "material", "age", "ward", "risk_level"])
    present   = [c for c in pick_cols if c in sub.columns]
    has_path  = "path" in sub.columns

    out: list[dict] = []
    for r in sub.to_dict("records"):
        src = [float(r["lon0"]), float(r["lat0"])]
        tgt = [float(r["lon1"]), float(r["lat1"])]
        rec: dict = {
            "source": src,
            "target": tgt,
            "color":  color,
        }
        if has_path and r.get("path"):
            rec["path"] = r["path"]   # full intermediate vertices
        for c in present:
            rec[c] = _sanitize(r[c])
        out.append(rec)
    return out


def _line_layer(
    data: list[dict],
    *,
    width_px: float = 2,
    pickable: bool = True,
) -> pdk.Layer:
    """LineLayer — the most stable deck.gl layer for 2-endpoint pipe segments."""
    return pdk.Layer(
        "LineLayer",
        data=data,
        get_source_position="source",
        get_target_position="target",
        get_color="color",
        get_width=width_px,
        width_min_pixels=1,
        pickable=pickable and bool(data),
        auto_highlight=False,
    )


def _path_layer(
    data: list[dict],
    *,
    width_px: float = 2,
    pickable: bool = True,
) -> pdk.Layer:
    """PathLayer for multi-vertex polylines (real GeoJSON routes)."""
    return pdk.Layer(
        "PathLayer",
        data=data,
        get_path="path",
        get_color="color",
        get_width=width_px,
        width_units="pixels",
        width_min_pixels=1,
        pickable=pickable and bool(data),
        auto_highlight=False,
    )


def _create_deck(
    layers: list[pdk.Layer],
    center_lat: float,
    center_lon: float,
    *,
    zoom: float = DEFAULT_ZOOM,
    view_3d: bool = True,
    tooltip: dict | bool = True,
    map_style_name: str = "Dark",
) -> pdk.Deck:
    token = mapbox_token()
    pitch, bearing = _pitch_and_bearing(view_3d)

    view = pdk.ViewState(
        latitude=float(center_lat),
        longitude=float(center_lon),
        zoom=float(zoom),
        pitch=float(pitch),
        bearing=float(bearing),
    )

    style_url, provider, _ = MAP_STYLES.get(map_style_name, MAP_STYLES["Dark"])

    # Carto styles don't need a token; Mapbox styles fall back to Carto when no token.
    if provider == "carto" or not token:
        fallback_url = style_url if provider == "carto" else CARTO_DARK
        return pdk.Deck(
            layers=layers,
            initial_view_state=view,
            map_style=fallback_url,
            map_provider="carto",
            tooltip=tooltip,
        )

    return pdk.Deck(
        layers=layers,
        initial_view_state=view,
        map_style=style_url,
        map_provider="mapbox",
        api_keys={"mapbox": token},
        tooltip=tooltip,
    )


def map_view_toolbar(key_prefix: str = "map", *, zoom: float = DEFAULT_ZOOM) -> MapViewOptions:
    import streamlit as st

    vk  = f"{key_prefix}_view3d"
    bk  = f"{key_prefix}_buildings"
    zk  = f"{key_prefix}_zoom"
    sk  = f"{key_prefix}_style"
    token_ok = has_mapbox()

    style_names = list(MAP_STYLES.keys())
    # Styles that actually have buildings (only available with Mapbox token)
    _HAS_BLD = {name for name, (_, _, has_bld) in MAP_STYLES.items() if has_bld}

    # Initialise session state
    if zk not in st.session_state:
        st.session_state[zk] = zoom
    if bk not in st.session_state:
        st.session_state[bk] = token_ok
    if sk not in st.session_state:
        st.session_state[sk] = "Dark"

    st.markdown('<div class="cn-map-toolbar-wrap">', unsafe_allow_html=True)
    c1, c2, c3, c4, c5 = st.columns([1.1, 1.3, 1.4, 0.8, 1.8])

    with c1:
        view_3d = st.toggle(
            "3D tilt",
            value=True,
            key=vk,
            help="Pitch camera to 52° so buildings appear in perspective.",
        )

    with c2:
        show_bld = st.toggle(
            "🏙 3D buildings",
            key=bk,
            disabled=not token_ok,
            help=(
                "Tilt + zoom ≥14 to see Mapbox fill-extrusion buildings. Requires API key."
            ) if token_ok else "Add MAPBOX_API_KEY to .streamlit/secrets.toml to enable buildings.",
        )

    with c3:
        # Only show Mapbox styles when token is available; always include Carto fallback
        available = style_names if token_ok else ["Carto (darkest)"]
        chosen_style = st.selectbox(
            "Map style",
            options=available,
            index=available.index(st.session_state[sk]) if st.session_state[sk] in available else 0,
            key=sk,
            label_visibility="collapsed",
            help="Dark — charcoal  |  Night — deep navy  |  Satellite — aerial  |  Carto — near-black (no buildings)",
        )

    with c4:
        if st.button("Reset", key=f"{key_prefix}_reset", use_container_width=True):
            st.session_state[zk] = zoom
            st.session_state[vk] = True
            st.session_state[bk] = token_ok
            st.session_state[sk] = "Dark"
            st.rerun()

    with c5:
        current_z   = float(st.session_state[zk])
        style_has_bld = chosen_style in _HAS_BLD
        if token_ok:
            if show_bld and style_has_bld and current_z >= BUILDINGS_MIN_ZOOM:
                badge = '<span class="cn-map-badge cn-map-badge-ok">3D buildings ON</span>'
            elif show_bld and not style_has_bld:
                badge = '<span class="cn-map-badge cn-map-badge-warn">Style has no buildings</span>'
            elif show_bld:
                badge = '<span class="cn-map-badge cn-map-badge-warn">Zoom ≥ 14 for buildings</span>'
            else:
                badge = f'<span class="cn-map-badge cn-map-badge-ok">Mapbox · {chosen_style}</span>'
        else:
            badge = '<span class="cn-map-badge cn-map-badge-warn">Carto · add MAPBOX_API_KEY for buildings</span>'
        st.markdown(badge, unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    current_zoom = float(st.session_state[zk])
    if show_bld and current_zoom < BUILDINGS_MIN_ZOOM:
        current_zoom = BUILDINGS_MIN_ZOOM
        st.session_state[zk] = current_zoom

    return MapViewOptions(
        show_buildings=token_ok and show_bld and style_has_bld and current_zoom >= BUILDINGS_MIN_ZOOM,
        view_3d=view_3d,
        zoom=current_zoom,
        map_style_name=chosen_style,
    )


def build_risk_map_deck(
    fdf: pd.DataFrame,
    *,
    color_mode: str = "Risk Level",
    has_layers: bool = False,
    risk_colors: dict[str, str],
    type_colors: dict[str, str],
    type_widths: dict[str, float] | None = None,
    selected_ids: Iterable[str] | None = None,
    center_lat: float = TORONTO_CENTER[0],
    center_lon: float = TORONTO_CENTER[1],
    zoom: float = DEFAULT_ZOOM,
    view_3d: bool = True,
    show_buildings: bool = True,
    map_style_name: str = "Dark",
) -> pdk.Deck:
    type_widths = type_widths or TYPE_LINE_WIDTHS
    layers: list[pdk.Layer] = []

    if color_mode == "Pipe Type" and has_layers:
        for ptype in ["Distribution", "Transmission"]:
            sub = fdf[fdf["pipe_type"] == ptype]
            if sub.empty:
                continue
            recs = _line_records(sub, color=hex_to_rgba(type_colors.get(ptype, "#8faabf")))
            layers.append(_line_layer(recs, width_px=type_widths.get(ptype, 2)))
    else:
        for level in ["Critical", "High", "Medium", "Low"]:
            color  = hex_to_rgba(risk_colors.get(level, "#8faabf"))
            base_w = RISK_LINE_WIDTHS.get(level, 3)
            if has_layers:
                for ptype in ["Distribution", "Transmission"]:
                    sub = fdf[(fdf["risk_level"] == level) & (fdf["pipe_type"] == ptype)]
                    if not sub.empty:
                        recs = _line_records(sub, color=color)
                        layers.append(_line_layer(recs, width_px=base_w + (1 if ptype == "Transmission" else 0)))
            else:
                sub = fdf[fdf["risk_level"] == level]
                if not sub.empty:
                    recs = _line_records(sub, color=color)
                    layers.append(_line_layer(recs, width_px=base_w))

    selected_ids = list(selected_ids or [])
    if selected_ids and not fdf.empty:
        sel = fdf[fdf["pipe_id"].isin(selected_ids)]
        if not sel.empty:
            outline = _line_records(sel, color=SELECT_OUTLINE_RGBA)
            layers.append(_line_layer(outline, width_px=9, pickable=False))
            accent = _line_records(sel, color=SELECT_ACCENT_RGBA)
            layers.append(_line_layer(accent, width_px=5, pickable=False))

    return _create_deck(
        layers,
        center_lat,
        center_lon,
        zoom=zoom,
        view_3d=view_3d,
        tooltip=PIPE_TOOLTIP if layers else False,
        map_style_name=map_style_name,
    )


def build_cascade_map_deck(
    df: pd.DataFrame,
    nearby: pd.DataFrame,
    source: pd.Series,
    *,
    selected_id: str,
    wave_colors: dict[int, str],
    show_pressure: bool = False,
    deg_radius: float = 0.012,
    view_3d: bool = True,
    show_buildings: bool = True,
    map_style_name: str = "Dark",
) -> pdk.Deck:
    layers: list[pdk.Layer] = []

    unaffected = df[~df["pipe_id"].isin(nearby["pipe_id"]) & (df["pipe_id"] != selected_id)]
    if not unaffected.empty:
        sample = unaffected.sample(min(200, len(unaffected)), random_state=42)
        recs = _line_records(sample, color=[26, 46, 74, 140])
        layers.append(_line_layer(recs, width_px=1, pickable=False))

    for wave in [4, 3, 2, 1]:
        sub = nearby[nearby["wave"] == wave]
        if not sub.empty:
            recs = _line_records(sub, color=hex_to_rgba(wave_colors.get(wave, "#ffa726")),
                                 meta_cols=["pipe_id", "wave", "pressure_psi"])
            layers.append(_line_layer(recs, width_px=3.0 + (4 - wave) * 0.8))

    # Broken pipe highlight
    src_recs = [{
        "source": [float(source["lon0"]), float(source["lat0"])],
        "target": [float(source["lon1"]), float(source["lat1"])],
        "color":  [255, 0, 0, 255],
        "pipe_id": selected_id,
    }]
    layers.append(_line_layer(src_recs, width_px=7))

    if show_pressure:
        import numpy as np
        for ring_frac, opacity in [(0.25, 60), (0.5, 45), (0.75, 30), (1.0, 20)]:
            n = 60
            theta  = np.linspace(0, 2 * np.pi, n)
            r_lats = source["lat"] + deg_radius * ring_frac * np.cos(theta)
            r_lons = source["lon"] + deg_radius * ring_frac * np.sin(theta) * 1.4
            ring   = [
                {"source": [float(r_lons[i]), float(r_lats[i])],
                 "target": [float(r_lons[(i+1) % n]), float(r_lats[(i+1) % n])],
                 "color":  [255, 61, 61, opacity]}
                for i in range(n)
            ]
            layers.append(_line_layer(ring, width_px=1, pickable=False))

    return _create_deck(
        layers,
        float(source["lat"]),
        float(source["lon"]),
        zoom=13.2,
        view_3d=view_3d,
        tooltip=CASCADE_TOOLTIP,
        map_style_name=map_style_name,
    )


def build_grouped_line_map_deck(
    groups: list[tuple[str, pd.DataFrame, str, float]],
    *,
    center_lat: float = TORONTO_CENTER[0],
    center_lon: float = TORONTO_CENTER[1],
    zoom: float = 11.0,
    view_3d: bool = True,
    show_buildings: bool = True,
    map_style_name: str = "Dark",
) -> pdk.Deck:
    layers: list[pdk.Layer] = []
    for _name, grp, color_hex, width_px in groups:
        if grp.empty:
            continue
        recs = _line_records(grp, color=hex_to_rgba(color_hex))
        layers.append(_line_layer(recs, width_px=width_px))

    return _create_deck(
        layers,
        center_lat,
        center_lon,
        zoom=zoom,
        view_3d=view_3d,
        tooltip=PIPE_TOOLTIP,
        map_style_name=map_style_name,
    )


def render_map(deck: pdk.Deck, *, height: int = 530) -> None:
    """Display deck.gl map in Streamlit."""
    import streamlit as st

    st.markdown('<div class="cn-map-frame">', unsafe_allow_html=True)
    # Use width="stretch" (Streamlit 1.40+); fall back to use_container_width for older builds
    try:
        st.pydeck_chart(deck, width="stretch", height=height)
    except TypeError:
        st.pydeck_chart(deck, use_container_width=True, height=height)
    st.markdown("</div>", unsafe_allow_html=True)
