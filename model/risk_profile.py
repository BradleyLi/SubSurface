"""
model/risk_profile.py
Risk-profile logic shared across frontend views and agent narratives.
"""

from __future__ import annotations


def failure_summary(row) -> str:
    """Compact summary using model output and break history — no material heuristics."""
    reasons: list[str] = []

    if row.get("predicted_break_probability") is not None and str(row.get("predicted_break_probability")) != "nan":
        reasons.append(f"Model break risk {float(row['risk_score']):.1f}%")

    breaks = int(row.get("break_count_10yr", 0) or 0)
    if breaks >= 3:
        reasons.append(f"🔧 {breaks} breaks (10yr)")
    elif breaks >= 1:
        reasons.append(f"🔧 {breaks} break(s) on record")

    if not reasons and row.get("risk_score") is not None and str(row.get("risk_score")) != "nan":
        reasons.append(f"Risk score {float(row['risk_score']):.0f}/100")

    if not reasons:
        material = str(row.get("material", "unknown"))
        reasons.append(f"{material} · {int(row.get('age', 0))} yrs")

    return " · ".join(reasons)
