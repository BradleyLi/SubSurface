#!/usr/bin/env python3
"""
Score trained XGBoost break-risk model for selected panel years.

For each pipe segment x year, writes one JSON object with predicted break
probability, risk percentile, pipe attributes, break history, location,
model output, and top SHAP contributors.

Requirements (GPU-enabled environment):
  - RAPIDS cuDF (required; no pandas fallback for panel loading)
  - xgboost with GPU support
  - shap

Usage:
  python predict_xgb_gpu.py --start-year 2015 --end-year 2016

Outputs (default: .structured-data/predictions/):
  - pipe_predictions_{start}_{end}.jsonl
  - run_metadata_{start}_{end}.json
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import shap
import xgboost as xgb

try:
    import cudf
except ImportError as exc:
    raise RuntimeError(
        "cudf is required. Install RAPIDS/cuDF in a CUDA-enabled environment."
    ) from exc

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / ".structured-data"
DEFAULT_PANEL = DATA_DIR / "panel.parquet"
DEFAULT_MODEL = DATA_DIR / "models" / "xgb_model.json"
DEFAULT_OUT = DATA_DIR / "predictions"

DISPLAY_COLS = [
    "segment_id",
    "asset_id",
    "year",
    "material",
    "diameter_mm",
    "construction_year",
    "age_years",
    "length_m",
    "centroid_lat",
    "centroid_lon",
    "breaks_past_5yr",
    "years_since_last_break",
]

FEATURE_RAW_MAP = {
    "material": "material",
    "diameter_mm": "diameter_mm",
    "construction_year": "construction_year",
    "age_years": "age_years",
    "length_m": "length_m",
    "breaks_past_5yr": "breaks_past_5yr",
    "breaks_past_3yr": "breaks_past_3yr",
    "breaks_past_1yr": "breaks_past_1yr",
    "years_since_last_break": "years_since_last_break",
    "break_count": "break_count",
    "source_layer": "source_layer",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def read_panel(path: Path):
    logger.info("Loading panel into cuDF...")
    try:
        return cudf.read_parquet(str(path))
    except Exception as exc:
        logger.warning("cudf.read_parquet failed (%s); loading via pyarrow", exc)
        import pyarrow.parquet as pq
        return cudf.DataFrame.from_arrow(pq.read_table(str(path)))


def add_total_breaks(df, *, id_col: str = "segment_id", year_col: str = "year"):
    ordered = df.sort_values([id_col, year_col])
    ordered["total_breaks"] = ordered.groupby(id_col)["break_count"].cumsum()
    return ordered


def preprocess_panel(
    df,
    *,
    train_end_year: int = 2011,
    year_col: str = "year",
    id_col: str = "segment_id",
    target: str = "break_next_year",
    max_cat_unique: int = 200,
):
    """Mirror train_xgb_gpu.py feature engineering for inference."""
    unique_years = df[year_col].unique()
    if hasattr(unique_years, "to_pylist"):
        years = sorted(map(int, unique_years.to_pylist()))
    else:
        years = sorted(map(int, unique_years.to_arrow().to_pylist()))
    train_years = [y for y in years if y <= train_end_year]

    drop_cols = [id_col, target, year_col]
    features = [c for c in df.columns if c not in drop_cols]

    keep_features = []
    for c in features:
        if df[c].dtype == "object" or str(df[c].dtype).startswith("str"):
            nuniq = int(df[c].nunique())
            if nuniq > max_cat_unique:
                warnings.warn(f"Dropping high-cardinality string column: {c} (unique={nuniq})")
                continue
        keep_features.append(c)
    features = keep_features

    cat_cols = [c for c in features if df[c].dtype == "object" or str(df[c].dtype).startswith("str")]
    for c in cat_cols:
        df[c] = df[c].astype("category").cat.codes.astype("int32")

    datetime_cols = [
        c for c in features
        if "datetime" in str(df[c].dtype) or "timestamp" in str(df[c].dtype)
    ]
    for c in datetime_cols:
        miss = f"{c}__isnan"
        if df[c].isnull().any():
            df[miss] = df[c].isnull().astype("int8")
            features.append(miss)
        df[c] = df[c].astype("int64").fillna(0)

    numeric_cols = [c for c in features if c not in cat_cols]
    for c in numeric_cols:
        if df[c].isnull().any():
            miss = f"{c}__isnan"
            df[miss] = df[c].isnull().astype("int8")
            features.append(miss)

    train_df = df[df[year_col].isin(train_years)]
    for c in numeric_cols:
        med = train_df[c].median()
        med = 0 if med is None else med
        df[c] = df[c].fillna(med)

    return df, features


def to_pandas(df):
    if hasattr(df, "to_pandas"):
        return df.to_pandas()
    return df


def load_booster(model_path: Path) -> xgb.Booster:
    booster = xgb.Booster()
    booster.load_model(str(model_path))
    if not booster.feature_names:
        raise RuntimeError(f"Model at {model_path} has no feature names")
    return booster


def predict_proba(booster: xgb.Booster, X, feature_names: list[str]) -> np.ndarray:
    missing = [f for f in feature_names if f not in X.columns]
    if missing:
        raise ValueError(
            f"Feature matrix missing columns expected by model: {missing[:5]}"
            f"{'...' if len(missing) > 5 else ''}"
        )

    X_model = X[feature_names]
    X_pd = to_pandas(X_model)
    dmat = xgb.DMatrix(X_pd, feature_names=feature_names)
    probs = booster.predict(dmat)
    if booster.best_iteration is not None and booster.best_iteration >= 0:
        probs_best = booster.predict(
            dmat, iteration_range=(0, booster.best_iteration + 1)
        )
        if not np.allclose(probs, probs_best):
            probs = probs_best
    return np.asarray(probs, dtype=np.float64)


def compute_risk_percentile(probs: np.ndarray, years: np.ndarray) -> np.ndarray:
    """Percentile rank of each score vs all pipes in the same snapshot year (0-100)."""
    scores = pd.Series(probs)
    year_series = pd.Series(years)
    return scores.groupby(year_series).rank(method="average", pct=True).to_numpy() * 100.0


def sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def ward_from_coords(lat: float, lon: float) -> str:
    """Approximate Toronto ward from centroid lat/lon."""
    if lat > 43.74:
        return "North York" if lon < -79.35 else "Scarborough"
    if lon < -79.50:
        return "Etobicoke"
    if lat < 43.67:
        return "Downtown Core"
    if lon > -79.34:
        return "East York"
    return "York"


def format_pipe_id(asset_id: str, segment_id: str) -> str:
    asset = str(asset_id).strip() if asset_id is not None and str(asset_id) != "nan" else ""
    if asset:
        return f"WM_{asset}"
    return f"WM_{str(segment_id).split('::')[0]}"


def json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (np.generic,)):
        value = value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if pd.isna(value):
        return None
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return round(float(value), 6)
    return value


def feature_display_value(feature: str, raw_row: pd.Series, model_value: Any) -> Any:
    raw_col = FEATURE_RAW_MAP.get(feature)
    if raw_col and raw_col in raw_row.index:
        return json_safe(raw_row[raw_col])
    if feature.endswith("__isnan"):
        return int(model_value)
    return json_safe(model_value)


def build_top_shap_contributors(
    feature_names: list[str],
    shap_row: np.ndarray,
    model_row: pd.Series,
    raw_row: pd.Series,
    top_n: int,
) -> list[dict[str, Any]]:
    order = np.argsort(np.abs(shap_row))[::-1][:top_n]
    contributors = []
    for idx in order:
        feature = feature_names[int(idx)]
        shap_val = float(shap_row[idx])
        contributors.append({
            "feature": feature,
            "feature_value": feature_display_value(feature, raw_row, model_row[feature]),
            "shap_contribution": round(shap_val, 6),
            "impact": "increase_risk" if shap_val >= 0 else "decrease_risk",
        })
    return contributors


def build_pipe_record(
    raw_row: pd.Series,
    predicted_probability: float,
    risk_percentile: float,
    shap_row: np.ndarray | None,
    feature_names: list[str],
    model_row: pd.Series,
    shap_base_value: float | None,
    top_n: int,
) -> dict[str, Any]:
    lat = float(raw_row["centroid_lat"])
    lon = float(raw_row["centroid_lon"])
    year = int(raw_row["year"])

    if shap_row is not None and shap_base_value is not None:
        margin = float(shap_base_value + shap_row.sum())
        base_probability = sigmoid(float(shap_base_value))
        final_probability = sigmoid(margin)
        top_shap = build_top_shap_contributors(
            feature_names, shap_row, model_row, raw_row, top_n
        )
    else:
        base_probability = predicted_probability
        final_probability = predicted_probability
        top_shap = []

    years_since = raw_row.get("years_since_last_break")
    years_since_val = None if pd.isna(years_since) else float(years_since)

    return {
        "pipe_id": format_pipe_id(raw_row.get("asset_id"), raw_row["segment_id"]),
        "prediction_date": f"{year}-01-01",
        "predicted_break_probability": round(float(predicted_probability), 6),
        "risk_percentile": round(float(risk_percentile), 6),
        "pipe_attributes": {
            "material": json_safe(raw_row.get("material")),
            "diameter_mm": json_safe(raw_row.get("diameter_mm")),
            "installation_year": json_safe(raw_row.get("construction_year")),
            "age_years": json_safe(raw_row.get("age_years")),
            "length_m": json_safe(raw_row.get("length_m")),
        },
        "break_history": {
            "total_breaks": json_safe(raw_row.get("total_breaks")),
            "breaks_last_5_years": json_safe(raw_row.get("breaks_past_5yr")),
            "years_since_last_break": years_since_val,
        },
        "location": {
            "latitude": round(lat, 6),
            "longitude": round(lon, 6),
            "ward": ward_from_coords(lat, lon),
        },
        "model_output": {
            "base_probability": round(base_probability, 6),
            "final_probability": round(final_probability, 6),
        },
        "top_shap_contributors": top_shap,
    }


def compute_shap_values(
    booster: xgb.Booster,
    X: pd.DataFrame,
    feature_names: list[str],
    batch_size: int,
) -> tuple[np.ndarray, float]:
    explainer = shap.TreeExplainer(booster)
    X_model = X[feature_names]
    n_rows = len(X_model)
    chunks = []

    for start in range(0, n_rows, batch_size):
        end = min(start + batch_size, n_rows)
        batch = X_model.iloc[start:end]
        shap_batch = explainer.shap_values(batch)
        chunks.append(np.asarray(shap_batch))
        logger.info("Computed SHAP for rows %d-%d / %d", start + 1, end, n_rows)

    base_value = float(np.asarray(explainer.expected_value).reshape(-1)[0])
    return np.vstack(chunks), base_value


def write_predictions_jsonl(records: list[dict[str, Any]], path: Path) -> None:
    with open(path, "w") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False))
            f.write("\n")


def main():
    parser = argparse.ArgumentParser(description="Predict break risk and SHAP values for panel years")
    parser.add_argument("--panel", default=str(DEFAULT_PANEL))
    parser.add_argument("--model", default=str(DEFAULT_MODEL))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUT))
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument("--end-year", type=int, default=2016)
    parser.add_argument("--train-end-year", type=int, default=2011, help="last train year used for imputation medians")
    parser.add_argument("--id-col", default="segment_id")
    parser.add_argument("--year-col", default="year")
    parser.add_argument("--target", default="break_next_year")
    parser.add_argument("--batch-size", type=int, default=10000, help="batch size for SHAP computation")
    parser.add_argument("--top-shap", type=int, default=4, help="number of SHAP contributors per pipe")
    parser.add_argument("--skip-shap", action="store_true")
    args = parser.parse_args()

    panel_path = Path(args.panel)
    model_path = Path(args.model)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not panel_path.exists():
        raise SystemExit(f"Panel file not found: {panel_path}")
    if not model_path.exists():
        raise SystemExit(f"Model file not found: {model_path} — train with train_xgb_gpu.py first")

    df = read_panel(panel_path)
    df = add_total_breaks(df, id_col=args.id_col, year_col=args.year_col)

    pred_mask = (df[args.year_col] >= args.start_year) & (df[args.year_col] <= args.end_year)
    if int(pred_mask.sum()) == 0:
        raise SystemExit(f"No rows found for years {args.start_year}-{args.end_year}")

    raw_cols = [c for c in DISPLAY_COLS if c in df.columns] + ["total_breaks"]
    pred_raw = to_pandas(df.loc[pred_mask, raw_cols]).reset_index(drop=True)

    df, features = preprocess_panel(
        df,
        train_end_year=args.train_end_year,
        year_col=args.year_col,
        id_col=args.id_col,
        target=args.target,
    )

    pred_df = df[pred_mask].copy()
    logger.info("Scoring %d rows for years %d-%d", len(pred_df), args.start_year, args.end_year)

    booster = load_booster(model_path)
    feature_names = list(booster.feature_names)
    missing = sorted(set(feature_names) - set(features))
    if missing:
        raise SystemExit(f"Preprocessed features missing columns required by model: {missing}")
    extra = sorted(set(features) - set(feature_names))
    if extra:
        logger.info("Ignoring %d extra preprocessed columns not used by model", len(extra))

    X = pred_df[features]
    probs = predict_proba(booster, X, feature_names)
    risk_percentiles = compute_risk_percentile(
        probs, pred_raw["year"].to_numpy()
    )

    shap_values = None
    shap_base_value = None
    if not args.skip_shap:
        logger.info("Computing SHAP values (batch_size=%d)...", args.batch_size)
        X_pd = to_pandas(pred_df[features])
        shap_values, shap_base_value = compute_shap_values(
            booster, X_pd, feature_names, args.batch_size
        )

    X_pd = to_pandas(pred_df[features])
    records = []
    for i in range(len(pred_raw)):
        raw_row = pred_raw.iloc[i]
        model_row = X_pd.iloc[i]
        shap_row = shap_values[i] if shap_values is not None else None
        records.append(
            build_pipe_record(
                raw_row=raw_row,
                predicted_probability=float(probs[i]),
                risk_percentile=float(risk_percentiles[i]),
                shap_row=shap_row,
                feature_names=feature_names,
                model_row=model_row,
                shap_base_value=shap_base_value,
                top_n=args.top_shap,
            )
        )

    pred_tag = f"{args.start_year}_{args.end_year}"
    jsonl_path = out_dir / f"pipe_predictions_{pred_tag}.jsonl"
    write_predictions_jsonl(records, jsonl_path)
    logger.info("Wrote %d pipe predictions to %s", len(records), jsonl_path)

    metadata = {
        "panel": str(panel_path),
        "model": str(model_path),
        "start_year": args.start_year,
        "end_year": args.end_year,
        "n_rows": len(records),
        "n_features": len(feature_names),
        "feature_names": feature_names,
        "predictions_file": str(jsonl_path),
        "shap_base_value": shap_base_value,
        "best_iteration": int(booster.best_iteration) if booster.best_iteration is not None else None,
        "record_schema": {
            "pipe_id": "WM_{asset_id}",
            "prediction_date": "YYYY-01-01 snapshot date",
            "predicted_break_probability": "model score",
            "risk_percentile": "percentile rank vs all pipes in the same year (0-100)",
            "pipe_attributes": ["material", "diameter_mm", "installation_year", "age_years", "length_m"],
            "break_history": ["total_breaks", "breaks_last_5_years", "years_since_last_break"],
            "location": ["latitude", "longitude", "ward"],
            "model_output": ["base_probability", "final_probability"],
            "top_shap_contributors": ["feature", "feature_value", "shap_contribution", "impact"],
        },
    }
    meta_path = out_dir / f"run_metadata_{pred_tag}.json"
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)
    logger.info("Wrote metadata to %s", meta_path)

    print("\nSample record:")
    print(json.dumps(records[0], indent=2, ensure_ascii=False))
    print(f"\nDone. Outputs in {out_dir}")


if __name__ == "__main__":
    main()
