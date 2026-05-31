"""
real_data.py — Fetch live data from Toronto Open Data (CKAN API)
and produce a DataFrame with the same schema as data_utils.get_pipes().

Fetches two watermain layers from the "watermains" package:
  • Transmission Watermain  (~400 features, always loaded in full)
  • Distribution Watermain  (~60 000+ features, sampled for performance)

Follows the Toronto Open Data CKAN API pattern:
  https://ckan0.cf.opendata.inter.prod-toronto.ca

For non-datastore_active resources (GeoJSON files), the resource's "url"
field is resolved via resource_show to get the actual download link.
"""

from __future__ import annotations
import json
import urllib.request
from typing import Optional
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st

# ── Constants ─────────────────────────────────────────────────────────────────

BASE_URL   = "https://ckan0.cf.opendata.inter.prod-toronto.ca"
CKAN_BASE  = BASE_URL + "/api/3/action"
DATASET_ID = "watermains"

# Max features to sample from the large Distribution layer.
# Transmission is small and always fully loaded.
# Set to None to load all ~60 000 Distribution features (30–60 s first load).
MAX_DIST_FEATURES = 3_000

from materials import normalize_material_code

RISK_COLORS: dict[str, str] = {
    "Critical": "#ff3d3d",
    "High":     "#ffa726",
    "Medium":   "#ffdd57",
    "Low":      "#1de9b6",
}


# ── CKAN helpers ──────────────────────────────────────────────────────────────

def _ckan_get(endpoint: str, params: dict) -> dict:
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url   = f"{CKAN_BASE}/{endpoint}?{query}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read())


def _resolve_resource_url(resource: dict) -> str:
    """
    Return the download URL for a resource.

    For non-datastore_active resources (GeoJSON files), the resource record
    already carries a direct "url" field. We call resource_show as a fallback
    to get the freshest URL in case it was updated on the portal.
    """
    if resource.get("datastore_active"):
        # Datastore table — use the dump endpoint for a full CSV download
        return BASE_URL + "/datastore/dump/" + resource["id"]

    # Non-datastore file resource — prefer url from the record itself,
    # then confirm via resource_show (mirrors the Open Data sample code).
    direct_url = resource.get("url", "")
    if direct_url:
        return direct_url

    meta = _ckan_get("resource_show", {"id": resource["id"]})
    return meta["result"]["url"]


def _find_geojson_url(resources: list[dict], name_fragment: str) -> str:
    """
    Iterate the package's resources (exactly as in the Open Data sample code)
    and return the download URL for the best-matching GeoJSON resource.

    Preference order:
      1. GeoJSON with name_fragment + "4326" (native WGS84 — no reprojection)
      2. Any GeoJSON with name_fragment
    """
    fragment = name_fragment.lower()
    candidates: list[dict] = []

    for resource in resources:
        name = resource.get("name", "").lower()
        fmt  = resource.get("format", "").upper()
        if fragment in name and fmt == "GEOJSON":
            candidates.append(resource)

    if not candidates:
        raise RuntimeError(
            f"No GeoJSON resource found containing '{name_fragment}' "
            f"in the '{DATASET_ID}' package. "
            f"Available resources: {[r.get('name') for r in resources]}"
        )

    # Prefer the 4326 (WGS84) variant
    for r in candidates:
        if "4326" in r.get("name", ""):
            return _resolve_resource_url(r)

    # Fall back to any matching GeoJSON
    return _resolve_resource_url(candidates[0])


def _fetch_geojson(url: str, max_features: Optional[int] = None) -> list[dict]:
    """Download a GeoJSON file and return up to max_features features."""
    with urllib.request.urlopen(url, timeout=120) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    data     = json.loads(raw)
    features = data.get("features", [])

    if max_features and len(features) > max_features:
        # Sample evenly across the file to preserve geographic coverage
        step     = max(1, len(features) // max_features)
        features = features[::step][:max_features]

    return features


# ── GeoJSON → row parsing ─────────────────────────────────────────────────────

def _coords_from_geom(geom: dict) -> Optional[tuple[float, float, float, float]]:
    """Return (lat0, lon0, lat1, lon1) from a LineString or MultiLineString."""
    gtype = geom.get("type", "")
    raw   = geom.get("coordinates", [])

    if gtype == "LineString" and len(raw) >= 2:
        pts = raw
    elif gtype == "MultiLineString":
        pts = [p for seg in raw for p in seg]
    else:
        return None

    if len(pts) < 2:
        return None

    # GeoJSON coordinates are [lon, lat]
    lon0, lat0 = float(pts[0][0]),  float(pts[0][1])
    lon1, lat1 = float(pts[-1][0]), float(pts[-1][1])
    return lat0, lon0, lat1, lon1


def _street_to_ward(lat: float, lon: float) -> str:
    """Approximate Toronto ward from lat/lon — coarse bounding boxes."""
    if lat > 43.74:
        return "North York" if lon < -79.35 else "Scarborough"
    elif lon < -79.50:
        return "Etobicoke"
    elif lat < 43.67:
        return "Downtown Core"
    elif lon > -79.34:
        return "East York"
    else:
        return "York"


def _parse_features(features: list[dict], pipe_type: str) -> list[dict]:
    """Convert raw GeoJSON features into row dicts for the DataFrame."""
    rows: list[dict] = []
    for feat in features:
        props = feat.get("properties") or {}
        geom  = feat.get("geometry")  or {}

        coords = _coords_from_geom(geom)
        if not coords:
            continue

        lat0, lon0, lat1, lon1 = coords

        # Sanity-check: skip anything outside greater Toronto bounds
        if not (43.5 < lat0 < 44.1 and -80.0 < lon0 < -79.0):
            continue

        material = normalize_material_code(props.get("Watermain Material"))

        raw_yr = props.get("Watermain Construction Year")
        try:
            install_year = int(raw_yr) if raw_yr else 1960
        except (ValueError, TypeError):
            install_year = 1960
        if not (1850 <= install_year <= 2026):
            install_year = 1960

        try:
            diameter = int(props.get("Watermain Diameter") or 150)
        except (ValueError, TypeError):
            diameter = 150

        try:
            length_m = int(props.get("Watermain Measured Length") or 100)
        except (ValueError, TypeError):
            length_m = 100

        asset_id = (
            props.get("Watermain Asset Identification")
            or props.get("ASSET_ID")
            or props.get("_id")
            or len(rows)
        )
        street = str(props.get("Watermain Location Description") or "")

        rows.append({
            "pipe_id":      f"WM-{asset_id}",
            "ward":         _street_to_ward(lat0, lon0),
            "material":     material,
            "install_year": install_year,
            "diameter_mm":  diameter,
            "length_m":     length_m,
            "pipe_type":    pipe_type,
            "street":       street,
            "lat0": lat0, "lon0": lon0,
            "lat1": lat1, "lon1": lon1,
            "lat":  (lat0 + lat1) / 2,
            "lon":  (lon0 + lon1) / 2,
        })
    return rows


# ── Schema placeholders (risk filled by ML enrichment only) ───────────────────

def _add_supplemental_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add canonical columns for join/UI; do not compute heuristic risk scores."""
    df = df.copy()
    df["age"] = (datetime.now().year - df["install_year"]).abs()
    df["tree_count_5m"] = 0
    df["complaints_12mo"] = 0
    df["utility_cuts_18mo"] = 0
    df["lead_exceedance_pct"] = 0.0
    df["years_since_resurfacing"] = 0
    df["break_count_10yr"] = 0
    df["properties_affected"] = (df["length_m"] * 0.5).astype(int)
    df["schools_affected"] = 0
    df["hospitals_affected"] = 0
    df["risk_score"] = np.nan
    df["risk_level"] = pd.NA
    df["risk_color"] = pd.NA
    df["emergency_cost"] = 0
    df["replacement_cost"] = (df["diameter_mm"] * df["length_m"] * 1.3).astype(int)
    df["expected_savings"] = 0
    df["priority_rank"] = 0
    return df


# ── Public API ────────────────────────────────────────────────────────────────

@st.cache_data(
    show_spinner="📡 Fetching Toronto Open Data — Transmission & Distribution Watermains...",
    ttl=3600,
)
def get_real_pipes(max_dist: int = MAX_DIST_FEATURES) -> pd.DataFrame:
    """
    Fetch Transmission Watermain + Distribution Watermain GeoJSON datasets
    from Open Data Toronto (CKAN) and return a DataFrame with geometry and
    attributes. Risk fields are placeholders until ML enrichment.

    Uses the standard CKAN API pattern recommended by Toronto Open Data:
      1. package_show  → discover all resources in the "watermains" package
      2. Iterate resources; for non-datastore_active GeoJSON files, resolve
         the download URL (via resource["url"] or resource_show fallback)
      3. Download, parse, risk-score, and merge both layers

    Parameters
    ----------
    max_dist : int
        Max features sampled from the Distribution layer (default 3 000).
        Transmission is always fully loaded (~400 features).

    Returns
    -------
    pd.DataFrame — same column schema as data_utils._get_synthetic_pipes()
    """
    # Step 1 — Discover all resources in the "watermains" package
    pkg_data = _ckan_get("package_show", {"id": DATASET_ID})
    if not pkg_data.get("success"):
        raise RuntimeError(f"CKAN package_show failed for '{DATASET_ID}'")

    resources = pkg_data["result"]["resources"]

    # Step 2 — Find the GeoJSON download URLs for each watermain layer
    tx_url   = _find_geojson_url(resources, "Transmission")
    dist_url = _find_geojson_url(resources, "Distribution")

    # Step 3 — Download features
    tx_feats   = _fetch_geojson(tx_url,   max_features=None)      # ~400, load all
    dist_feats = _fetch_geojson(dist_url, max_features=max_dist)  # sampled

    # Step 4 — Parse into rows
    rows  = _parse_features(tx_feats,   pipe_type="Transmission")
    rows += _parse_features(dist_feats, pipe_type="Distribution")

    if not rows:
        raise RuntimeError(
            "No valid pipe features could be parsed from the GeoJSON files. "
            "Check that the Toronto Open Data portal is reachable."
        )

    df = pd.DataFrame(rows)
    return _add_supplemental_columns(df)
