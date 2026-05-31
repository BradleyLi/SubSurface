"""
Load XGBoost pipe predictions and enrich Toronto Open Data pipe rows.

Joins live GeoJSON geometry (real_data) with model output from:
  ml-models/.structured-data/predictions/pipe_predictions_{start}_{end}.jsonl
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from materials import normalize_material_code
from real_data import RISK_COLORS

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_PREDICTIONS_PATH = (
    BASE_DIR
    / "ml-models"
    / ".structured-data"
    / "predictions"
    / "pipe_predictions_2015_2016.jsonl"
)
DEFAULT_PREDICTION_YEAR = 2016


def active_prediction_year() -> int:
    """Snapshot year for ML predictions (override via ML_PREDICTION_YEAR env)."""
    raw = os.getenv("ML_PREDICTION_YEAR")
    if raw:
        return int(raw)
    return DEFAULT_PREDICTION_YEAR


def normalize_pipe_join_key(pipe_id: str) -> str:
    """Normalize WM-LN100001 and WM_LN100001 to a shared join key."""
    s = str(pipe_id).strip().upper()
    if s.startswith("WM-"):
        s = s[3:]
    elif s.startswith("WM_"):
        s = s[3:]
    return s.replace("-", "").replace("_", "")


def predictions_path() -> Path:
    return Path(os.getenv("ML_PREDICTIONS_PATH", str(DEFAULT_PREDICTIONS_PATH)))


def load_predictions(
    path: Path | None = None,
    *,
    prediction_year: int | None = None,
) -> pd.DataFrame:
    """Load JSONL predictions, optionally filtered to one snapshot year."""
    year = active_prediction_year() if prediction_year is None else prediction_year
    jsonl_path = path or predictions_path()
    if not jsonl_path.exists():
        raise FileNotFoundError(f"ML predictions file not found: {jsonl_path}")

    rows: list[dict[str, Any]] = []
    with jsonl_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if year is not None:
                year_prefix = f"{year}-"
                if not str(rec.get("prediction_date", "")).startswith(year_prefix):
                    continue
            rows.append(_flatten_prediction(rec))

    if not rows:
        raise RuntimeError(
            f"No prediction rows found in {jsonl_path}"
            + (f" for year {year}" if year is not None else "")
        )

    df = pd.DataFrame(rows)
    df["_join_key"] = df["ml_pipe_id"].map(normalize_pipe_join_key)
    df = df.drop_duplicates(subset=["_join_key"], keep="first")
    return df


def _flatten_prediction(rec: dict[str, Any]) -> dict[str, Any]:
    attrs = rec.get("pipe_attributes") or {}
    hist = rec.get("break_history") or {}
    model_out = rec.get("model_output") or {}
    return {
        "ml_pipe_id": rec.get("pipe_id"),
        "prediction_date": rec.get("prediction_date"),
        "predicted_break_probability": rec.get("predicted_break_probability"),
        "risk_percentile": rec.get("risk_percentile"),
        "ml_top_shap_contributors": rec.get("top_shap_contributors") or [],
        "ml_base_probability": model_out.get("base_probability"),
        "ml_final_probability": model_out.get("final_probability"),
        "ml_break_count_10yr": hist.get("total_breaks"),
        "ml_breaks_last_5_years": hist.get("breaks_last_5_years"),
        "ml_years_since_last_break": hist.get("years_since_last_break"),
        "ml_material": normalize_material_code(attrs.get("material")),
        "ml_installation_year": attrs.get("installation_year"),
        "ml_age_years": attrs.get("age_years"),
    }


def enrich_real_pipes_with_predictions(
    real_df: pd.DataFrame,
    pred_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Inner-join Toronto pipe geometry with ML predictions on normalized asset id.
    Keeps real lat/lon geometry; replaces heuristic risk with model output.
    """
    if real_df.empty or pred_df.empty:
        return pd.DataFrame()

    pipes = real_df.copy()
    pipes["_join_key"] = pipes["pipe_id"].map(normalize_pipe_join_key)

    pred_cols = [
        "_join_key",
        "predicted_break_probability",
        "risk_percentile",
        "prediction_date",
        "ml_top_shap_contributors",
        "ml_base_probability",
        "ml_final_probability",
        "ml_break_count_10yr",
        "ml_breaks_last_5_years",
        "ml_years_since_last_break",
        "ml_material",
        "ml_installation_year",
        "ml_age_years",
    ]
    preds = pred_df[pred_cols].copy()

    merged = pipes.merge(preds, on="_join_key", how="inner")
    if merged.empty:
        return merged

    if "ml_material" in merged.columns:
        merged["material"] = merged["ml_material"]

    if "ml_installation_year" in merged.columns:
        inst = pd.to_numeric(merged["ml_installation_year"], errors="coerce")
        merged["install_year"] = inst.fillna(merged["install_year"]).astype(int)

    if "ml_age_years" in merged.columns:
        ml_age = pd.to_numeric(merged["ml_age_years"], errors="coerce").round()
        merged["age"] = ml_age.fillna(merged["age"]).abs().astype(int)

    merged["risk_score"] = (merged["predicted_break_probability"] * 100.0).round(1)
    merged["risk_level"] = pd.cut(
        merged["risk_percentile"],
        bins=[0, 25, 50, 75, 100],
        labels=["Low", "Medium", "High", "Critical"],
    )
    merged["risk_color"] = merged["risk_level"].map(RISK_COLORS)

    if "ml_break_count_10yr" in merged.columns:
        merged["break_count_10yr"] = (
            pd.to_numeric(merged["ml_break_count_10yr"], errors="coerce")
            .fillna(merged.get("break_count_10yr", 0))
            .astype(int)
        )

    merged["emergency_cost"] = (
        merged["diameter_mm"] * merged["length_m"] * merged["risk_score"] / 45.0
    ).astype(int)
    merged["replacement_cost"] = (merged["diameter_mm"] * merged["length_m"] * 1.3).astype(int)
    merged["expected_savings"] = (
        merged["emergency_cost"] - merged["replacement_cost"]
    ).clip(lower=0)
    merged["priority_rank"] = merged["expected_savings"].rank(
        ascending=False, method="first"
    ).astype(int)

    merged["data_source"] = "ml_enriched"
    drop_cols = ["_join_key", "ml_material", "ml_installation_year", "ml_age_years"]
    return merged.drop(columns=[c for c in drop_cols if c in merged.columns])


def get_ml_enriched_pipes(
    *,
    max_dist: int | None = None,
    prediction_year: int | None = None,
    predictions_file: Path | None = None,
) -> pd.DataFrame:
    """Load Toronto GeoJSON pipes and overlay ML model predictions."""
    from real_data import get_real_pipes

    preds = load_predictions(predictions_file, prediction_year=prediction_year)
    real_df = get_real_pipes(max_dist=max_dist)
    enriched = enrich_real_pipes_with_predictions(real_df, preds)
    if enriched.empty:
        raise RuntimeError(
            "No Toronto pipes matched ML predictions. "
            "Check pipe_id formats and that Open Data assets overlap the model panel."
        )
    return enriched


def find_pipe_row(df: pd.DataFrame, pipe_id: str) -> pd.Series | None:
    """Resolve a pipe row by Toronto or ML pipe_id format."""
    matches = df[df["pipe_id"] == pipe_id]
    if not matches.empty:
        return matches.iloc[0]

    key = normalize_pipe_join_key(pipe_id)
    if "_join_key" in df.columns:
        matches = df[df["_join_key"] == key]
    else:
        matches = df[df["pipe_id"].map(normalize_pipe_join_key) == key]
    if matches.empty:
        return None
    return matches.iloc[0]
