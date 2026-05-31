"""Shared test fixtures."""

from __future__ import annotations

from data_utils import get_pipes


def synthetic_ml_df():
    """Synthetic demo rows augmented with ML-shaped fields for unit tests only."""
    df = get_pipes(use_real=False).copy()
    shap = [
        {
            "feature": "age_years",
            "feature_value": 40,
            "shap_contribution": -0.42,
            "impact": "decrease_risk",
        }
    ]
    df["predicted_break_probability"] = df["risk_score"] / 100.0
    df["risk_percentile"] = 50.0
    df["ml_top_shap_contributors"] = [shap for _ in range(len(df))]
    return df
