"""
agent/why_failing_agent.py
Human-readable, agent-style explanations for pipe failure risk.
"""

from __future__ import annotations

from model import MATERIAL_LIFE


def agent_failure_explanation(row) -> str:
    """Return an agent-style human-readable explanation for one pipe."""
    pipe_id = str(row.get("pipe_id", "This segment"))
    material = str(row.get("material", "unknown material"))
    age = int(row.get("age", 0))
    ward = str(row.get("ward", "unknown ward"))
    risk_score = float(row.get("risk_score", 0))
    risk_level = str(row.get("risk_level", "Unknown"))

    drivers: list[str] = []
    life = MATERIAL_LIFE.get(material, 60)
    if age > life:
        drivers.append(f"it is {age} years old, beyond typical {material} service life ({life} years)")
    elif age > int(life * 0.75):
        drivers.append(f"it is {age} years old and approaching end-of-life for {material}")
    else:
        drivers.append(f"it has a moderate age profile ({age} years)")

    trees = int(row.get("tree_count_5m", 0))
    if trees >= 4:
        drivers.append(f"{trees} nearby trees increase the chance of root-related stress")

    complaints = int(row.get("complaints_12mo", 0))
    if complaints >= 3:
        drivers.append(f"{complaints} recent service complaints indicate active local distress")

    breaks = int(row.get("break_count_10yr", 0))
    if breaks >= 2:
        drivers.append(f"historical break activity ({breaks} in 10 years) raises recurrence risk")

    resurfacing = int(row.get("years_since_resurfacing", 0))
    if resurfacing >= 18:
        drivers.append(f"{resurfacing} years since resurfacing suggests prolonged surface load stress")

    emergency_cost = int(row.get("emergency_cost", 0))
    replacement_cost = int(row.get("replacement_cost", 0))
    savings = int(row.get("expected_savings", 0))

    primary_driver = drivers[0] if drivers else "its overall risk profile remains elevated"
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
