"""
Load XGBoost pipe predictions (JSONL) into the canonical UI DataFrame schema.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from data_utils import RISK_COLORS
from real_data import MATERIAL_MAP

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_PRED_DIR = _REPO_ROOT / "ml-models" / ".structured-data" / "predictions"

FEATURE_LABELS: dict[str, str] = {
    "length_m": "Pipe length (m)",
    "material": "Material",
    "construction_year": "Construction year",
    "age_years": "Pipe age",
    "diameter_mm": "Diameter (mm)",
    "breaks_past_5yr": "Breaks (5 yr)",
    "breaks_past_3yr": "Breaks (3 yr)",
    "breaks_past_1yr": "Breaks (1 yr)",
    "years_since_last_break": "Years since last break",
    "years_since_last_break__isnan": "No prior break on record",
    "install_date": "Install date",
    "trees_count": "Trees nearby",
    "trees_count_per_100m": "Trees per 100 m",
    "break_count": "Total breaks",
}


def resolve_predictions_path() -> Path | None:
    """Find the newest predictions JSONL (env override → metadata → glob)."""
    env_path = os.getenv("CITYNERVE_PREDICTIONS_FILE", "").strip()
    if env_path:
        path = Path(env_path).expanduser()
        if path.is_file():
            return path

    pred_dir = Path(os.getenv("CITYNERVE_PREDICTIONS_DIR", str(_DEFAULT_PRED_DIR)))
    if not pred_dir.is_dir():
        return None

    for meta_path in sorted(pred_dir.glob("run_metadata_*.json"), reverse=True):
        try:
            meta = json.loads(meta_path.read_text())
            candidate = Path(meta["predictions_file"])
            if candidate.is_file():
                return candidate
        except (KeyError, json.JSONDecodeError, OSError):
            continue

    matches = sorted(pred_dir.glob("pipe_predictions_*.jsonl"), reverse=True)
    return matches[0] if matches else None


def _material_label(code: str | None) -> str:
    if not code:
        return "Unknown"
    key = str(code).strip().upper()
    return MATERIAL_MAP.get(key, key.title())


def _risk_level(score: float) -> str:
    if score >= 75:
        return "Critical"
    if score >= 50:
        return "High"
    if score >= 25:
        return "Medium"
    return "Low"


def _segment_from_centroid(lat: float, lon: float, length_m: float, pipe_id: str) -> tuple[float, float, float, float]:
    """Build a short map segment from centroid + length (deterministic bearing per pipe)."""
    seed = sum(ord(c) for c in pipe_id) % 360
    bearing = np.radians(seed)
    half = max(float(length_m), 20.0) * 0.0000045 / 2.0
    lat0 = lat - half * np.cos(bearing)
    lon0 = lon - half * np.sin(bearing)
    lat1 = lat + half * np.cos(bearing)
    lon1 = lon + half * np.sin(bearing)
    return float(lat0), float(lon0), float(lat1), float(lon1)


def _impact_estimates(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["properties_affected"] = (df["length_m"] * 1.8).clip(lower=1).astype(int)
    df["schools_affected"] = np.minimum((df["properties_affected"] / 380).astype(int), 5)
    df["hospitals_affected"] = np.minimum((df["properties_affected"] / 2200).astype(int), 2)
    df["emergency_cost"] = (
        df["diameter_mm"] * df["length_m"] * df["risk_score"] / 45
    ).astype(int)
    df["replacement_cost"] = (df["diameter_mm"] * df["length_m"] * 1.3).astype(int)
    df["expected_savings"] = (df["emergency_cost"] - df["replacement_cost"]).clip(lower=0)
    df["priority_rank"] = df["expected_savings"].rank(ascending=False, method="first").astype(int)
    return df


def load_predictions_records(
    path: Path,
    *,
    snapshot_year: int | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Load JSONL predictions, keeping the latest snapshot year per pipe_id.
    """
    by_pipe: dict[str, dict[str, Any]] = {}
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            pipe_id = str(record["pipe_id"])
            year = int(str(record.get("prediction_date", "0000"))[:4])
            if snapshot_year is not None and year != snapshot_year:
                continue
            prev = by_pipe.get(pipe_id)
            if prev is None or year >= int(str(prev.get("prediction_date", "0000"))[:4]):
                by_pipe[pipe_id] = record
    return by_pipe


def predictions_to_dataframe(
    records: dict[str, dict[str, Any]],
    *,
    max_pipes: int | None = None,
) -> pd.DataFrame:
    """Convert prediction records to the canonical pipe DataFrame."""
    rows: list[dict[str, Any]] = []
    for pipe_id, rec in records.items():
        attrs = rec.get("pipe_attributes") or {}
        breaks = rec.get("break_history") or {}
        loc = rec.get("location") or {}
        prob = float(rec["predicted_break_probability"])
        risk_score = round(prob * 100.0, 2)
        level = _risk_level(risk_score)
        material_code = str(attrs.get("material") or "UNK")
        material = _material_label(material_code)
        install_year = int(attrs.get("installation_year") or 1970)
        age = int(attrs.get("age_years") or max(2024 - install_year, 0))
        length_m = int(round(float(attrs.get("length_m") or 100)))
        diameter_mm = int(round(float(attrs.get("diameter_mm") or 150)))
        lat = float(loc.get("latitude") or 43.7)
        lon = float(loc.get("longitude") or -79.4)
        lat0, lon0, lat1, lon1 = _segment_from_centroid(lat, lon, length_m, pipe_id)

        rows.append(
            {
                "pipe_id": pipe_id,
                "ward": str(loc.get("ward") or "Unknown"),
                "material": material,
                "material_code": material_code,
                "install_year": install_year,
                "diameter_mm": diameter_mm,
                "length_m": length_m,
                "pipe_type": "Distribution",
                "street": "",
                "lat0": lat0,
                "lon0": lon0,
                "lat1": lat1,
                "lon1": lon1,
                "lat": lat,
                "lon": lon,
                "age": age,
                "risk_score": risk_score,
                "risk_level": level,
                "risk_color": RISK_COLORS[level],
                "risk_percentile": float(rec.get("risk_percentile") or 0.0),
                "predicted_break_probability": prob,
                "model_shap_json": json.dumps(rec.get("top_shap_contributors") or []),
                "data_source": "model",
                "tree_count_5m": 0,
                "complaints_12mo": 0,
                "utility_cuts_18mo": 0,
                "lead_exceedance_pct": 0.0,
                "years_since_resurfacing": 0,
                "break_count_10yr": int(breaks.get("total_breaks") or 0),
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df = df.sort_values("risk_score", ascending=False).reset_index(drop=True)
    if max_pipes is not None and len(df) > max_pipes:
        df = df.head(max_pipes).reset_index(drop=True)

    return _impact_estimates(df)


def get_model_pipes(
    *,
    max_pipes: int | None = None,
    snapshot_year: int | None = None,
) -> pd.DataFrame:
    """
    Load model predictions into the UI pipe schema.

    max_pipes defaults to CITYNERVE_MAX_MODEL_PIPES (5000) for map performance.
    snapshot_year defaults to CITYNERVE_PREDICTION_YEAR or latest in file.
    """
    path = resolve_predictions_path()
    if path is None:
        raise FileNotFoundError(
            "No predictions file found. Run ml-models/predict_xgb_gpu.py or set "
            "CITYNERVE_PREDICTIONS_FILE."
        )

    if max_pipes is None:
        max_pipes = int(os.getenv("CITYNERVE_MAX_MODEL_PIPES", "5000"))

    year_env = os.getenv("CITYNERVE_PREDICTION_YEAR", "").strip()
    if snapshot_year is None and year_env.isdigit():
        snapshot_year = int(year_env)

    records = load_predictions_records(path, snapshot_year=snapshot_year)
    if not records and snapshot_year is not None:
        records = load_predictions_records(path, snapshot_year=None)

    df = predictions_to_dataframe(records, max_pipes=max_pipes)
    if df.empty:
        raise ValueError(f"No prediction rows loaded from {path}")
    return df


def model_shap_for_row(row: pd.Series) -> dict[str, float] | None:
    """Parse real model SHAP contributors stored on a pipe row."""
    raw = row.get("model_shap_json")
    if raw is None or (isinstance(raw, float) and pd.isna(raw)) or raw == "":
        return None
    contributors = json.loads(raw) if isinstance(raw, str) else raw
    if not contributors:
        return None

    out: dict[str, float] = {}
    for item in contributors:
        feature = str(item.get("feature", "unknown"))
        label = FEATURE_LABELS.get(feature, feature.replace("_", " ").title())
        if feature == "material":
            label = f"Material ({item.get('feature_value', row.get('material_code', ''))})"
        value = abs(float(item.get("shap_contribution", 0.0))) * 100.0
        if value > 0:
            out[label] = round(value, 2)
    return out or None
