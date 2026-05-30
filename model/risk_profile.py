"""
model/risk_profile.py
Risk-profile logic shared across frontend views and agent narratives.
"""

from __future__ import annotations

MATERIAL_LIFE: dict[str, int] = {
    "Cast Iron": 60,
    "Lead": 40,
    "Clay": 50,
    "Asbestos Cement": 55,
    "Galvanized": 50,
    "Concrete": 60,
    "Ductile Iron": 100,
    "PVC": 80,
}


def failure_summary(row) -> str:
    """Compact machine-friendly summary of top failure drivers."""
    reasons: list[str] = []
    material = str(row.get("material", ""))
    age = int(row.get("age", 0))
    life = MATERIAL_LIFE.get(material, 60)

    if age > life:
        reasons.append(f"⚠ {age}yr {material} (>{life}yr life)")
    elif age > life * 0.75:
        reasons.append(f"↑ {age}yr {material} (near EOL)")

    trees = int(row.get("tree_count_5m", 0))
    if trees > 5:
        reasons.append(f"🌳 {trees} trees within 5m")

    complaints = int(row.get("complaints_12mo", 0))
    if complaints > 3:
        reasons.append(f"📞 {complaints} complaints/yr")

    resurfacing = int(row.get("years_since_resurfacing", 0))
    if resurfacing > 20:
        reasons.append(f"🛣 {resurfacing}yr since resurfacing")

    breaks = int(row.get("break_count_10yr", 0))
    if breaks >= 3:
        reasons.append(f"🔧 {breaks} breaks (10yr)")

    if not reasons:
        reasons.append(f"Risk score {float(row.get('risk_score', 0)):.0f}/100")

    return " · ".join(reasons)
