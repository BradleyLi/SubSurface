"""
Build deterministic evidence packets for Nemotron Workflow 1.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from agent.harness.workflow1 import TABLE_PIPE_PROFILE, TABLE_SHAP
from agent.schemas import PipeRiskEvidence, ShapContributor
from data_utils import get_shap


def _risk_category(level: str) -> str:
    return str(level).upper().replace(" ", "_")


def _percentile_for_score(risk_score: float, df: pd.DataFrame | None) -> float:
    if df is not None and len(df) > 0 and "risk_score" in df.columns:
        return float((df["risk_score"] <= risk_score).mean() * 100.0)
    return float(min(max(risk_score, 0.0), 100.0))


def _shap_to_contributors(row: pd.Series) -> list[ShapContributor]:
    shap = get_shap(row)
    median = float(pd.Series(list(shap.values())).median()) if shap else 5.0
    contributors: list[ShapContributor] = []

    label_map = {
        "Pipe Age": ("pipe age", lambda r: int(r["age"])),
        "Trees within 5m": ("trees within 5m", lambda r: int(r["tree_count_5m"])),
        "311 Complaints (12mo)": ("311 complaints (12mo)", lambda r: int(r["complaints_12mo"])),
        "Lead Exceedance %": ("lead exceedance %", lambda r: round(float(r["lead_exceedance_pct"]), 1)),
        "Utility Cuts (18mo)": ("utility cuts (18mo)", lambda r: int(r["utility_cuts_18mo"])),
        "Years Since Resurfacing": ("years since resurfacing", lambda r: int(r["years_since_resurfacing"])),
        "Break History (10yr)": ("breaks in last 10 years", lambda r: int(r["break_count_10yr"])),
    }

    for name, value in sorted(shap.items(), key=lambda x: x[1], reverse=True):
        impact: str = "increase_risk" if value >= median else "decrease_risk"
        if name.startswith("Material ("):
            material = str(row.get("material", "unknown"))
            label = f"{material.lower()} material"
            feat_val: Any = True
        elif name in label_map:
            label, getter = label_map[name]
            feat_val = getter(row)
        else:
            label = name.lower()
            feat_val = value

        contributors.append(
            ShapContributor(
                feature_label=label,
                feature_value=feat_val,
                impact=impact,  # type: ignore[arg-type]
                shap_contribution=round(float(value), 2),
            )
        )

    return contributors[:5]


def build_evidence_from_row(row: pd.Series, df: pd.DataFrame | None = None) -> PipeRiskEvidence:
    """Convert a pipe dataframe row into a Nemotron-safe evidence packet."""
    risk_score = float(row["risk_score"])
    probability = round(risk_score / 100.0, 4)
    percentile = round(_percentile_for_score(risk_score, df), 1)

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
        top_shap_contributors=_shap_to_contributors(row),
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
