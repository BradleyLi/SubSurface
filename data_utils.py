"""
data_utils.py — Pipe network data for CityNerve.
Supports two modes:
  • Synthetic (default) — generated locally, always works offline.
  • Real          — fetched live from Toronto Open Data via real_data.py.

Toggle via the sidebar switch or the USE_REAL_DATA env variable.
"""

from __future__ import annotations
import os
import numpy as np
import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WARDS: dict[str, tuple[float, float]] = {
    "North York":   (43.771, -79.411),
    "Scarborough":  (43.768, -79.236),
    "Etobicoke":    (43.641, -79.564),
    "Downtown Core":(43.651, -79.383),
    "East York":    (43.688, -79.331),
    "York":         (43.700, -79.470),
}

MATERIALS       = ["Cast Iron", "Ductile Iron", "PVC", "Concrete", "Asbestos Cement"]
MATERIAL_WEIGHTS= [0.35, 0.30, 0.20, 0.10, 0.05]
MATERIAL_RISK   = {
    "Cast Iron":        0.90,
    "Asbestos Cement":  0.82,
    "Concrete":         0.52,
    "Ductile Iron":     0.28,
    "PVC":              0.08,
}
MATERIAL_INSTALL = {
    "Cast Iron":        (1920, 1969),
    "Asbestos Cement":  (1948, 1980),
    "Concrete":         (1938, 1984),
    "Ductile Iron":     (1958, 2000),
    "PVC":              (1974, 2010),
}

RISK_COLORS = {
    "Critical": "#ff3d3d",
    "High":     "#ffa726",
    "Medium":   "#ffdd57",
    "Low":      "#1de9b6",
}

N_PER_WARD = 100   # 600 total pipe segments


# ---------------------------------------------------------------------------
# Data generation
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def get_pipes(use_real: bool = False) -> pd.DataFrame:
    """
    Return pipe DataFrame in canonical schema.
    Pass use_real=True to fetch live Toronto Open Data, False for synthetic demo.
    The bool argument is part of the cache key, so toggling it fetches fresh data.
    """
    if use_real:
        try:
            from real_data import get_real_pipes
            return get_real_pipes()
        except Exception as e:
            st.warning(f"⚠️ Could not load real data ({e}). Falling back to synthetic data.")

    return _get_synthetic_pipes()


@st.cache_data(show_spinner=False)
def _get_synthetic_pipes() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    rows: list[dict] = []

    for ward, (clat, clon) in WARDS.items():
        for _ in range(N_PER_WARD):
            material = str(rng.choice(MATERIALS, p=MATERIAL_WEIGHTS))
            yr_lo, yr_hi = MATERIAL_INSTALL[material]
            install_year = int(rng.integers(yr_lo, yr_hi + 1))

            lat0 = clat + rng.uniform(-0.024, 0.024)
            lon0 = clon + rng.uniform(-0.034, 0.034)
            seg   = rng.uniform(0.0003, 0.0022)
            angle = rng.uniform(0, 2 * np.pi)
            lat1  = lat0 + seg * np.cos(angle)
            lon1  = lon0 + seg * np.sin(angle)

            rows.append({
                "pipe_id":               f"WM-{len(rows):04d}",
                "ward":                  ward,
                "material":              material,
                "install_year":          install_year,
                "diameter_mm":           int(rng.choice([100, 150, 200, 250, 300, 400],
                                             p=[0.18, 0.30, 0.26, 0.12, 0.10, 0.04])),
                "length_m":              int(rng.uniform(60, 430)),
                "pipe_type":             "Synthetic",
                "street":                "",
                "lat0": lat0, "lon0": lon0, "lat1": lat1, "lon1": lon1,
                "lat":  (lat0 + lat1) / 2,
                "lon":  (lon0 + lon1) / 2,
                "tree_count_5m":         int(rng.poisson(2.4)),
                "complaints_12mo":       int(rng.poisson(1.9)),
                "utility_cuts_18mo":     int(min(rng.poisson(0.7), 7)),
                "lead_exceedance_pct":   float(abs(rng.normal(3.2, 4.0))),
                "years_since_resurfacing": int(rng.integers(0, 44)),
                "break_count_10yr":      int(min(rng.poisson(1.1), 8)),
            })

    df = pd.DataFrame(rows)
    df["age"] = 2024 - df["install_year"]

    # Risk score — weighted composite
    m_risk  = df["material"].map(MATERIAL_RISK)
    age_n   = df["age"] / 104
    tree_n  = df["tree_count_5m"]        / (df["tree_count_5m"].max() + 1)
    comp_n  = df["complaints_12mo"]      / (df["complaints_12mo"].max() + 1)
    lead_n  = df["lead_exceedance_pct"]  / (df["lead_exceedance_pct"].quantile(0.97) + 1)
    surf_n  = df["years_since_resurfacing"] / 44
    cut_n   = df["utility_cuts_18mo"]    / (df["utility_cuts_18mo"].max() + 1)
    brk_n   = df["break_count_10yr"]     / (df["break_count_10yr"].max() + 1)

    raw = (
        0.26 * age_n  +
        0.23 * m_risk +
        0.13 * tree_n +
        0.11 * comp_n +
        0.09 * lead_n +
        0.08 * surf_n +
        0.06 * cut_n  +
        0.04 * brk_n
    )
    noise = rng.normal(0, 0.034, len(df))
    raw   = (raw + noise).clip(0.04, 0.97)

    df["risk_score"] = (raw * 100).round(1)
    df["risk_level"] = pd.cut(
        df["risk_score"],
        bins=[0, 25, 50, 75, 100],
        labels=["Low", "Medium", "High", "Critical"],
    )
    df["risk_color"] = df["risk_level"].map(RISK_COLORS)

    # Impact estimates
    df["properties_affected"] = (df["length_m"] * rng.uniform(0.5, 3.5, len(df))).astype(int)
    df["schools_affected"]    = np.minimum((df["properties_affected"] / 380).astype(int), 5)
    df["hospitals_affected"]  = np.minimum((df["properties_affected"] / 2200).astype(int), 2)

    df["emergency_cost"]   = (
        df["diameter_mm"] * df["length_m"] * df["risk_score"] / 45
        * rng.uniform(0.8, 1.2, len(df))
    ).astype(int)
    df["replacement_cost"] = (
        df["diameter_mm"] * df["length_m"] * 1.3
        * rng.uniform(0.9, 1.1, len(df))
    ).astype(int)
    df["expected_savings"] = (df["emergency_cost"] - df["replacement_cost"]).clip(lower=0)

    # Priority rank (by expected savings, breaking ties with risk_score)
    df["priority_rank"] = df["expected_savings"].rank(ascending=False, method="first").astype(int)

    return df


# ---------------------------------------------------------------------------
# SHAP-style feature contributions
# ---------------------------------------------------------------------------

def get_shap(row: pd.Series) -> dict[str, float]:
    return {
        "Pipe Age":                  round((row["age"] / 104) * 28, 1),
        f"Material ({row['material']})": round(MATERIAL_RISK.get(row["material"], 0.3) * 22, 1),
        "Trees within 5m":           round(row["tree_count_5m"] * 2.8, 1),
        "311 Complaints (12mo)":     round(row["complaints_12mo"] * 2.4, 1),
        "Lead Exceedance %":         round(min(row["lead_exceedance_pct"] * 1.2, 14), 1),
        "Utility Cuts (18mo)":       round(row["utility_cuts_18mo"] * 3.5, 1),
        "Years Since Resurfacing":   round(row["years_since_resurfacing"] * 0.22, 1),
        "Break History (10yr)":      round(row["break_count_10yr"] * 3.0, 1),
    }


# ---------------------------------------------------------------------------
# Simulated Nemotron/NIM AI responses
# ---------------------------------------------------------------------------

RESPONSES = {
    "replace": """\
**Replacement Priority Analysis — CityNerve**

Proactive replacement of the top 10 highest-risk segments would:

- Reduce network-wide failure probability by **~34%** over 12 months
- Avoid an estimated **${savings:,}** in emergency repair costs
- Prevent water disruption for approximately **{properties:,} properties**

**Optimal sequence** balances risk reduction with excavation disruption:

1. Prioritise cast iron segments in North York and Scarborough with lead exceedance > 5% and mature tree canopy within 5m
2. Secondary: segments with utility cuts within 50m in the past 18 months (construction-induced stress)
3. Defer: PVC segments installed after 1990 — estimated 40+ remaining service years

Shall I generate a formal Capital Works Order for the top segment?""",

    "cascade": """\
**Cascade Failure Simulation — Pipe {pipe_id}**

If **{pipe_id}** ({material}, {age} years old, {length}m) fails:

| Timeframe | Effect |
|---|---|
| 0–15 min | Pressure loss in immediate zone |
| 30 min | Downstream segments {d1}, {d2} drop below 20 PSI |
| 2 hours | **{properties} properties** lose water service |
| 4 hours | Isolation valves activated; repair crew dispatched |

**Affected facilities:** {schools} school(s) · {hospitals} hospital zone(s)  
**Estimated emergency cost:** **${cost:,}**

cuGraph identifies **3 bridging segments** nearby — reinforcing them would contain cascade to under 40 properties.  
Want me to generate isolation valve recommendations?""",

    "whatif": """\
**What-If Scenario: {scenario}**

Under this scenario, the network risk model projects:

- **Risk change:** +{risk_delta}% increase in network-wide failure probability
- **Most vulnerable:** Pipes in **{ward}** — clay soil expands significantly under these conditions
- **Cost projection:** Additional **${added_cost:,}** in expected annual maintenance
- **Recommended action:** Pre-emptive inspection of {n_pipes} segments in the affected zone

SHAP analysis indicates **{factor}** becomes the dominant failure driver under this scenario.  
Shall I filter the Risk Map to show only affected segments?""",

    "default": """\
**CityNerve Network Intelligence Summary**

Monitoring **{n_pipes}** pipe segments across Toronto's 6,100 km network.

| Risk Level | Segments | % of Network |
|---|---|---|
| 🔴 Critical | {critical} | {crit_pct:.1f}% |
| 🟠 High | {high} | {high_pct:.1f}% |
| 🟡 Medium | {medium} | {med_pct:.1f}% |
| 🟢 Low | {low} | {low_pct:.1f}% |

**Key findings:**
- Highest-risk ward: **{top_ward}** (avg risk score {top_ward_score:.1f})
- Primary failure driver across network: **aging cast iron infrastructure** (avg {avg_age:.0f} years)
- Top priority segment: **{top_pipe}** — estimated emergency cost **${top_cost:,}**

Ask me about specific pipes, replacement priorities, or "what-if" scenarios.""",
}


@st.cache_data(
    show_spinner="📡 Fetching Distribution Watermains from Toronto Open Data…",
    ttl=3600,
)
def get_distribution_watermains(max_features: int | None = 5_000) -> pd.DataFrame:
    """
    Fetch only the Distribution Watermain GeoJSON layer from Toronto Open Data.
    Pass max_features=None to load the full layer (~46k+ features).
    Returns a DataFrame with geometry, material, diameter, install year, etc.
    Raises RuntimeError if the dataset is unreachable.
    """
    from real_data import (
        _ckan_get,
        _find_geojson_url,
        _fetch_geojson,
        _parse_features,
        _add_risk_scores,
        DATASET_ID,
    )
    import numpy as np

    pkg_data  = _ckan_get("package_show", {"id": DATASET_ID})
    if not pkg_data.get("success"):
        raise RuntimeError(f"CKAN package_show failed for '{DATASET_ID}'")

    resources = pkg_data["result"]["resources"]
    dist_url  = _find_geojson_url(resources, "Distribution")
    features  = _fetch_geojson(dist_url, max_features=max_features)
    rows      = _parse_features(features, pipe_type="Distribution")

    if not rows:
        raise RuntimeError("No valid Distribution Watermain features parsed.")

    df  = pd.DataFrame(rows)
    rng = np.random.default_rng(int(df["install_year"].mean()) if len(df) else 42)
    df  = _add_risk_scores(df, rng=rng)
    return df


def get_ai_response(query: str, df: pd.DataFrame) -> str:
    q = query.lower()
    n  = len(df)
    critical = df[df["risk_level"] == "Critical"]
    high     = df[df["risk_level"] == "High"]
    medium   = df[df["risk_level"] == "Medium"]
    low      = df[df["risk_level"] == "Low"]
    top_pipe = df.nlargest(1, "emergency_cost").iloc[0]

    if any(w in q for w in ["replac", "repair", "priorit", "next", "should", "recommend"]):
        savings    = df.nlargest(10, "expected_savings")["expected_savings"].sum()
        properties = df.nlargest(10, "properties_affected")["properties_affected"].sum()
        return RESPONSES["replace"].format(savings=savings, properties=properties)

    elif any(w in q for w in ["cascade", "break", "fail", "what happen", "downstream", "if pipe"]):
        p = (critical.sample(1) if len(critical) else df.sample(1)).iloc[0]
        top5 = df.nlargest(5, "risk_score")["pipe_id"].tolist()
        return RESPONSES["cascade"].format(
            pipe_id=p["pipe_id"], material=p["material"],
            age=p["age"], length=p["length_m"],
            d1=top5[1] if len(top5) > 1 else "WM-0017",
            d2=top5[2] if len(top5) > 2 else "WM-0041",
            properties=p["properties_affected"],
            schools=p["schools_affected"],
            hospitals=max(p["hospitals_affected"], 1),
            cost=p["emergency_cost"],
        )

    elif any(w in q for w in ["rain", "winter", "construct", "temperatur", "climat", "freeze"]):
        scenario = (
            "Increased rainfall (+30%)" if "rain" in q else
            "Severe winter freeze-thaw cycle" if "winter" in q or "freez" in q else
            "Major construction activity nearby"
        )
        ward  = df.sample(1, random_state=7).iloc[0]["ward"]
        factor = "thermal stress" if "winter" in q or "freez" in q else "soil saturation"
        return RESPONSES["whatif"].format(
            scenario=scenario, risk_delta=14, ward=ward,
            added_cost=430000, n_pipes=52, factor=factor,
        )

    else:
        ward_avg   = df.groupby("ward")["risk_score"].mean()
        top_ward   = ward_avg.idxmax()
        return RESPONSES["default"].format(
            n_pipes=n,
            critical=len(critical), crit_pct=len(critical)/n*100,
            high=len(high),         high_pct=len(high)/n*100,
            medium=len(medium),     med_pct=len(medium)/n*100,
            low=len(low),           low_pct=len(low)/n*100,
            top_ward=top_ward,      top_ward_score=ward_avg[top_ward],
            avg_age=df["age"].mean(),
            top_pipe=top_pipe["pipe_id"], top_cost=top_pipe["emergency_cost"],
        )
