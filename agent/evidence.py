"""
Build deterministic evidence packets for Nemotron Workflow 1.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from agent.harness.workflow1 import TABLE_PIPE_PROFILE, TABLE_SHAP
from agent.schemas import PipeRiskEvidence, ShapContributor


def _risk_category(level: str) -> str:
    return str(level).upper().replace(" ", "_")


def _parse_ml_shap(row: pd.Series) -> list[ShapContributor] | None:
    raw = row.get("ml_top_shap_contributors")
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not raw:
        return None

    contributors: list[ShapContributor] = []
    for item in raw[:5]:
        feature = str(item.get("feature", "unknown")).replace("_", " ")
        impact = item.get("impact", "increase_risk")
        contributors.append(
            ShapContributor(
                feature_label=feature,
                feature_value=item.get("feature_value", ""),
                impact=impact,  # type: ignore[arg-type]
                shap_contribution=round(float(item.get("shap_contribution", 0.0)), 4),
            )
        )
    return contributors or None


def build_evidence_from_row(row: pd.Series, df: pd.DataFrame | None = None) -> PipeRiskEvidence:
    """Convert a pipe dataframe row into a Nemotron-safe evidence packet."""
    if pd.notna(row.get("predicted_break_probability")):
        probability = round(float(row["predicted_break_probability"]), 4)
        percentile = round(float(row["risk_percentile"]), 1)
    else:
        raise ValueError(
            f"Pipe {row.get('pipe_id')} has no ML prediction; "
            "heuristic risk fallback is disabled."
        )

    ml_shap = _parse_ml_shap(row)
    if not ml_shap:
        raise ValueError(
            f"Pipe {row.get('pipe_id')} has no ML SHAP contributors."
        )

    return PipeRiskEvidence(
        pipe_id=str(row["pipe_id"]),
        predicted_break_probability=probability,
        risk_percentile=percentile,
        risk_category=_risk_category(str(row.get("risk_level", "Unknown"))),
        ward=str(row.get("ward")) if pd.notna(row.get("ward")) else None,
        material=str(row.get("material")) if pd.notna(row.get("material")) else None,
        age_years=int(row["age"]) if pd.notna(row.get("age")) else None,
        diameter_mm=int(row["diameter_mm"]) if pd.notna(row.get("diameter_mm")) else None,
        length_m=int(row["length_m"]) if pd.notna(row.get("length_m")) else None,
        properties_affected=int(row["properties_affected"])
        if pd.notna(row.get("properties_affected"))
        else None,
        emergency_cost=int(row["emergency_cost"])
        if pd.notna(row.get("emergency_cost"))
        else None,
        top_shap_contributors=ml_shap,
    )


def build_evidence_from_dict(row: dict[str, Any], df: pd.DataFrame | None = None) -> PipeRiskEvidence:
    return build_evidence_from_row(pd.Series(row), df=df)


def evidence_to_w1_tables(evidence: PipeRiskEvidence) -> dict[str, list[dict[str, Any]]]:
    """
    Map structured evidence to harness Workflow 1 table keys (for prose summarize() or debugging).
    """
    profile_row: dict[str, Any] = {
        "pipe_id": evidence.pipe_id,
        "predicted_break_probability": evidence.predicted_break_probability,
        "risk_percentile": evidence.risk_percentile,
        "risk_category": evidence.risk_category,
        "ward": evidence.ward,
        "material": evidence.material,
        "age_years": evidence.age_years,
        "diameter_mm": evidence.diameter_mm,
    }
    shap_rows = [c.model_dump() for c in evidence.top_shap_contributors]
    return {
        TABLE_PIPE_PROFILE: [profile_row],
        TABLE_SHAP: shap_rows,
    }
