"""
Deterministic Workflow 1 summary when Nemotron is unavailable or returns invalid JSON.
"""

from __future__ import annotations

from agent.schemas import PipeRiskEvidence, Workflow1Summary


def _impact_phrase(impact: str) -> str:
    return "increases predicted risk" if impact == "increase_risk" else "may decrease predicted risk"


def template_summary(evidence: PipeRiskEvidence) -> Workflow1Summary:
    pct = evidence.risk_percentile
    prob_pct = round(evidence.predicted_break_probability * 100, 1)
    category = evidence.risk_category.replace("_", " ").title()

    top_reasons = [
        f"{c.feature_label} ({c.feature_value}) {_impact_phrase(c.impact)}."
        for c in evidence.top_shap_contributors[:3]
    ]

    material = evidence.material or "unknown material"
    headline = (
        f"{category}-risk {material.lower()} main — model flags elevated break drivers."
    )[:160]

    risk_sentence = (
        f"This pipe is in the {pct:.1f}th risk percentile with a "
        f"{prob_pct:.1f}% model-estimated annual break probability."
    )[:280]

    if evidence.risk_category in ("CRITICAL", "HIGH"):
        next_step = (
            "Prioritize field verification and engineering review for near-term "
            "inspection or renewal planning."
        )
    else:
        next_step = (
            "Schedule routine monitoring and include in the next capital planning review."
        )

    caveats = [
        "Based on model output and SHAP-style contributors, not a completed field inspection.",
        "Operational dispatch requires human approval.",
    ]

    return Workflow1Summary(
        pipe_id=evidence.pipe_id,
        headline=headline,
        risk_sentence=risk_sentence,
        top_reasons=top_reasons,
        recommended_next_step=next_step[:220],
        caveats=caveats[:3],
    )
