"""
agent/why_failing_agent.py
Human-readable, agent-style explanations for pipe failure risk.
"""

from __future__ import annotations


def agent_failure_explanation(row) -> str:
    """Return an agent-style human-readable explanation for one pipe."""
    pipe_id = str(row.get("pipe_id", "This segment"))
    material = str(row.get("material", "unknown material"))
    age = int(row.get("age", 0))
    ward = str(row.get("ward", "unknown ward"))
    risk_score = float(row.get("risk_score", 0))
    risk_level = str(row.get("risk_level", "Unknown"))

    drivers: list[str] = []
    if row.get("predicted_break_probability") is not None and str(row.get("predicted_break_probability")) != "nan":
        drivers.append(
            f"the XGBoost model estimates a {risk_score:.1f}% annual break probability "
            f"(network percentile {float(row.get('risk_percentile', 0)):.0f})"
        )
    else:
        drivers.append(f"its overall risk score is {risk_score:.1f}/100")

    breaks = int(row.get("break_count_10yr", 0) or 0)
    if breaks >= 2:
        drivers.append(f"historical break activity ({breaks} in 10 years) raises recurrence risk")
    elif breaks == 1:
        drivers.append("one prior break is on record for this segment")

    if age >= 80:
        drivers.append(f"the segment is {age} years old ({material})")

    emergency_cost = int(row.get("emergency_cost", 0))
    replacement_cost = int(row.get("replacement_cost", 0))
    savings = int(row.get("expected_savings", 0))

    primary_driver = drivers[0] if drivers else "model output indicates elevated failure risk"
    secondary = ""
    if len(drivers) > 1:
        secondary = " Secondary factors: " + "; ".join(drivers[1:3]) + "."

    action = (
        f" Recommended action: prioritize proactive replacement in the current planning cycle "
        f"(replace: ${replacement_cost:,}, avoided emergency exposure: ${emergency_cost:,}, expected savings: ${savings:,})."
        if risk_score >= 70
        else (
            f" Recommended action: schedule targeted inspection and monitoring before full replacement "
            f"(replace: ${replacement_cost:,}, projected emergency exposure: ${emergency_cost:,})."
        )
    )

    return (
        f"{pipe_id} in {ward} is classified as {risk_level} risk ({risk_score:.1f}/100) because {primary_driver}."
        f"{secondary}{action}"
    )
