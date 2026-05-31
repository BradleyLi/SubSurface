"""
Load XGBoost pipe predictions and enrich Toronto Open Data pipe rows.

Joins Toronto watermain geometry (local data/watermains/ or Open Data) with model output from:
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
DEFAULT_ENRICHED_PATH = (
    BASE_DIR / "data" / "watermains" / "ml_enriched_pipes.parquet"
)


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


def enriched_pipes_path() -> Path:
    """Pre-joined geometry + ML predictions (override via ML_ENRICHED_PATH)."""
    return Path(os.getenv("ML_ENRICHED_PATH", str(DEFAULT_ENRICHED_PATH)))


def _enriched_source_paths() -> list[Path]:
    """Inputs that invalidate a cached enriched parquet when newer."""
    from real_data import watermains_data_dir, DIST_GEOJSON_NAME, TRANS_GEOJSON_NAME

    data_dir = watermains_data_dir()
    return [
        data_dir / DIST_GEOJSON_NAME,
        data_dir / TRANS_GEOJSON_NAME,
        predictions_path(),
    ]


def _enriched_cache_is_fresh(cache_path: Path) -> bool:
    if not cache_path.is_file():
        return False
    cache_mtime = cache_path.stat().st_mtime
    for source in _enriched_source_paths():
        if source.is_file() and source.stat().st_mtime > cache_mtime:
            return False
    return True


def _prepare_enriched_for_parquet(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "ml_top_shap_contributors" in out.columns:
        out["ml_top_shap_contributors"] = out["ml_top_shap_contributors"].map(
            lambda value: json.dumps(value) if not isinstance(value, str) else value
        )
    if "risk_level" in out.columns:
        out["risk_level"] = out["risk_level"].astype(str)
    return out


def _restore_enriched_from_parquet(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "ml_top_shap_contributors" in out.columns:
        def _parse_shap(raw: object) -> list | str:
            if isinstance(raw, list):
                return raw
            if isinstance(raw, str):
                try:
                    parsed = json.loads(raw)
                    return parsed if isinstance(parsed, list) else raw
                except json.JSONDecodeError:
                    return raw
            return raw

        out["ml_top_shap_contributors"] = out["ml_top_shap_contributors"].map(_parse_shap)
    return out


def load_enriched_pipes_static(path: Path | None = None) -> pd.DataFrame:
    """Load pre-joined pipes from disk (fast path)."""
    cache_path = path or enriched_pipes_path()
    if not _enriched_cache_is_fresh(cache_path):
        raise FileNotFoundError(f"Enriched cache missing or stale: {cache_path}")
    df = pd.read_parquet(cache_path)
    return _restore_enriched_from_parquet(df)


def build_enriched_pipes_cache(
    *,
    max_dist: int | None = None,
    prediction_year: int | None = None,
    predictions_file: Path | None = None,
    output_path: Path | None = None,
) -> Path:
    """Join GeoJSON geometry with ML predictions once and write a static parquet file."""
    from real_data import get_real_pipes

    year = active_prediction_year() if prediction_year is None else prediction_year
    preds = load_predictions(predictions_file, prediction_year=year)
    real_df = get_real_pipes(max_dist=max_dist)
    enriched = enrich_real_pipes_with_predictions(real_df, preds)
    if enriched.empty:
        raise RuntimeError(
            "No Toronto pipes matched ML predictions. "
            "Check pipe_id formats and that watermain assets overlap the model panel."
        )

    cache_path = output_path or enriched_pipes_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    _prepare_enriched_for_parquet(enriched).to_parquet(cache_path, index=False)
    return cache_path


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
    ]
    preds = pred_df[pred_cols].copy()

    merged = pipes.merge(preds, on="_join_key", how="inner")
    if merged.empty:
        return merged

    if "ml_material" in merged.columns:
        merged["material"] = merged["ml_material"]

<<<<<<< HEAD
    if "ml_installation_year" in merged.columns:
        inst = pd.to_numeric(merged["ml_installation_year"], errors="coerce")
        merged["install_year"] = inst.fillna(merged["install_year"]).astype(int)

    if "ml_age_years" in merged.columns:
        ml_age = pd.to_numeric(merged["ml_age_years"], errors="coerce").round()
        merged["age"] = ml_age.fillna(merged["age"]).abs().astype(int)

=======
>>>>>>> da3b215 (static-map)
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
    """Load Toronto pipes with ML predictions — from static cache when available."""
    cache_path = enriched_pipes_path()
    if max_dist is None and _enriched_cache_is_fresh(cache_path):
        return load_enriched_pipes_static(cache_path)

    from real_data import get_real_pipes

    preds = load_predictions(predictions_file, prediction_year=prediction_year)
    real_df = get_real_pipes(max_dist=max_dist)
    enriched = enrich_real_pipes_with_predictions(real_df, preds)
    if enriched.empty:
        raise RuntimeError(
            "No Toronto pipes matched ML predictions. "
            "Check pipe_id formats and that watermain assets overlap the model panel."
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
