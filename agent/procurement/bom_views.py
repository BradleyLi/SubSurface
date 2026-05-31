"""Render role-scoped procurement summaries for W2 prompts and reports."""

from __future__ import annotations

from agent.schemas import BillOfMaterials, BomLineItem, RoleName

ENGINEER_CATEGORIES = {
    "pipe_section",
    "repair_clamp",
    "full_circle_clamp",
    "coupling",
    "restraint_fitting",
    "gasket",
    "bolt_kit",
    "mechanical_fitting",
    "gate_valve",
}
FIELD_CATEGORIES = ENGINEER_CATEGORIES | {
    "utility_locate",
    "dewatering",
    "excavation_equipment",
}
POLICE_CATEGORIES = {"traffic_control", "road_restoration", "excavation_equipment"}


def _money(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"${value:,.2f}"


def _line_table(lines: list[BomLineItem], *, include_price: bool = True) -> str:
    if not lines:
        return "- No relevant BoM lines for this role."
    out = []
    for line in lines:
        price = f", unit {_money(line.unit_price)}, total {_money(line.line_total)}" if include_price else ""
        supplier = f", supplier {line.chosen_supplier_name}" if line.chosen_supplier_name else ""
        out.append(
            f"- {line.description}: qty {line.qty:g} {line.unit}{supplier}{price}. Reason: {line.reason or 'selected'}"
        )
    return "\n".join(out)


def _award_lines(bom: BillOfMaterials) -> str:
    if not bom.contract_awards:
        return "- No supplier contract award recommendations available."
    return "\n".join(
        f"- Award {award.supplier_name} ({award.supplier_type}) for {award.scope}: "
        f"{_money(award.award_subtotal)}; approval required."
        for award in bom.contract_awards
    )


def full_bom_summary(bom: BillOfMaterials) -> str:
    return "\n".join(
        [
            "## Procurement / BoM and supplier award recommendations",
            "Draft, human-approved procurement support only.",
            "",
            "### Required parts and services",
            _line_table(bom.line_items),
            "",
            "### Recommended supplier contract awards",
            _award_lines(bom),
            "",
            "### Cost estimate",
            f"- Parts subtotal: {_money(bom.parts_subtotal)}",
            f"- Services subtotal: {_money(bom.services_subtotal)}",
            f"- Subtotal: {_money(bom.subtotal)}",
            f"- Total with contingency/tax: {_money(bom.total_estimate)}",
        ]
    )


def project_bom_for_role(bom: BillOfMaterials, role: RoleName) -> str:
    if role is RoleName.OPERATIONS:
        return full_bom_summary(bom)
    if role is RoleName.ENGINEER:
        lines = [line for line in bom.line_items if line.category in ENGINEER_CATEGORIES]
        return "\n".join(
            [
                "## Repair parts (specs) - advisory BoM slice",
                "Use only to comment on material/diameter compatibility and repair scope.",
                _line_table(lines, include_price=False),
            ]
        )
    if role is RoleName.FIELD:
        lines = [line for line in bom.line_items if line.category in FIELD_CATEGORIES]
        return "\n".join(
            [
                "## Parts/equipment to stage - advisory BoM slice",
                "Use for staging and verification checklist only.",
                _line_table(lines),
            ]
        )
    if role is RoleName.POLICE:
        lines = [line for line in bom.line_items if line.category in POLICE_CATEGORIES]
        return "\n".join(
            [
                "## Road/traffic restoration scope - advisory BoM slice",
                "Use to size traffic control and road-impact coordination only.",
                _line_table(lines),
            ]
        )
    return ""
