"""Tests for ML prediction loading and enrichment."""

from __future__ import annotations

import pandas as pd

from agent.evidence import build_evidence_from_row
from ml_predictions import enrich_real_pipes_with_predictions, load_predictions, normalize_pipe_join_key


def test_normalize_pipe_join_key():
    assert normalize_pipe_join_key("WM-LN100001") == "LN100001"
    assert normalize_pipe_join_key("WM_LN100001") == "LN100001"


def test_load_predictions_2016():
    preds = load_predictions(prediction_year=2016)
    assert len(preds) > 40_000
    assert "predicted_break_probability" in preds.columns
    assert preds["_join_key"].is_unique


def test_enrich_real_pipe_with_ml_predictions():
    preds = load_predictions(prediction_year=2016)
    sample_key = preds["_join_key"].iloc[0]
    sample = preds[preds["_join_key"] == sample_key].iloc[0]
    real = pd.DataFrame(
        [
            {
                "pipe_id": f"WM-{sample_key}",
                "ward": "Scarborough",
                "material": "DIP",
                "install_year": 1973,
                "diameter_mm": 200,
                "length_m": 85,
                "pipe_type": "Distribution",
                "street": "",
                "lat0": 43.79,
                "lon0": -79.32,
                "lat1": 43.791,
                "lon1": -79.319,
                "lat": 43.793,
                "lon": -79.323,
                "age": 53,
                "tree_count_5m": 2,
                "complaints_12mo": 1,
                "utility_cuts_18mo": 0,
                "lead_exceedance_pct": 3.0,
                "years_since_resurfacing": 5,
                "break_count_10yr": 2,
                "risk_score": 50.0,
                "risk_level": "Medium",
                "risk_color": "#ffdd57",
                "properties_affected": 100,
                "schools_affected": 0,
                "hospitals_affected": 0,
                "emergency_cost": 10000,
                "replacement_cost": 8000,
                "expected_savings": 2000,
                "priority_rank": 1,
            }
        ]
    )
    enriched = enrich_real_pipes_with_predictions(real, preds)
    assert len(enriched) == 1
    row = enriched.iloc[0]
    assert row["data_source"] == "ml_enriched"
    assert row["material"] == sample["ml_material"]
    assert 0 <= row["predicted_break_probability"] <= 1
    assert len(row["ml_top_shap_contributors"]) >= 1


def test_enrich_falls_back_when_ml_age_missing():
    preds = load_predictions(prediction_year=2016)
    missing = preds[preds["ml_age_years"].isna()].iloc[0]
    sample_key = missing["_join_key"]
    real = pd.DataFrame(
        [
            {
                "pipe_id": f"WM-{sample_key}",
                "ward": "Scarborough",
                "material": "DIP",
                "install_year": 1973,
                "diameter_mm": 200,
                "length_m": 85,
                "pipe_type": "Distribution",
                "street": "",
                "lat0": 43.79,
                "lon0": -79.32,
                "lat1": 43.791,
                "lon1": -79.319,
                "lat": 43.793,
                "lon": -79.323,
                "age": 53,
                "tree_count_5m": 2,
                "complaints_12mo": 1,
                "utility_cuts_18mo": 0,
                "lead_exceedance_pct": 3.0,
                "years_since_resurfacing": 5,
                "break_count_10yr": 0,
                "risk_score": 50.0,
                "risk_level": "Medium",
                "risk_color": "#ffdd57",
                "properties_affected": 100,
                "schools_affected": 0,
                "hospitals_affected": 0,
                "emergency_cost": 10000,
                "replacement_cost": 8000,
                "expected_savings": 2000,
                "priority_rank": 1,
            }
        ]
    )
    enriched = enrich_real_pipes_with_predictions(real, preds)
    assert len(enriched) == 1
    assert enriched.iloc[0]["age"] == 53


def test_evidence_uses_ml_shap_when_present():
    preds = load_predictions(prediction_year=2016)
    sample = preds.iloc[0]
    row = pd.Series(
        {
            "pipe_id": "WM-TEST",
            "risk_score": sample["predicted_break_probability"] * 100,
            "risk_level": "High",
            "ward": "Scarborough",
            "material": "DIP",
            "age": 40,
            "diameter_mm": 200,
            "length_m": 80,
            "properties_affected": 50,
            "emergency_cost": 5000,
            "predicted_break_probability": sample["predicted_break_probability"],
            "risk_percentile": sample["risk_percentile"],
            "ml_top_shap_contributors": sample["ml_top_shap_contributors"],
        }
    )
    evidence = build_evidence_from_row(row)
    assert evidence.predicted_break_probability == round(float(sample["predicted_break_probability"]), 4)
    assert evidence.top_shap_contributors[0].feature_label != "pipe age"
