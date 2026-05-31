"""Build lowest-cost Bill of Materials and supplier award recommendations."""

from __future__ import annotations

from collections import defaultdict

from agent.procurement.catalog import (
    items_by_id,
    load_offers,
    load_suppliers,
    suppliers_by_id,
)
from agent.procurement.finalize import FinalizedItem
from agent.schemas import (
    BillOfMaterials,
    BomLineItem,
    ContractAwardRecommendation,
    SupplierPartOffer,
)

AWARD_SCOPE_BY_TYPE = {
    "pipe_construction": "pipe repair materials and civil watermain repair support",
    "mechanical_parts_service": "mechanical watermain parts and repair service",
    "paving_restoration": "road restoration and pavement reinstatement",
    "utility_locates": "emergency utility locates",
    "dewatering_pumping": "dewatering and pumping support",
    "environmental_response": "environmental cleanup response",
    "equipment_rental": "excavation and traffic support equipment",
    "electrical_supply": "electrical supply and service support",
}


def _best_offers(item_id: str) -> list[SupplierPartOffer]:
    offers = [offer for offer in load_offers() if offer.item_id == item_id]
    return sorted(
        offers,
        key=lambda o: (
            o.unit_price,
            not o.in_stock,
            o.lead_time_days,
            o.supplier_id,
        ),
    )


def _round_money(value: float) -> float:
    return round(float(value), 2)


def _award_scope(supplier_type: str, line_descriptions: list[str]) -> str:
    base = AWARD_SCOPE_BY_TYPE.get(supplier_type, supplier_type.replace("_", " "))
    categories = ", ".join(sorted(set(line_descriptions))[:4])
    return f"{base}: {categories}"


def build_bom(
    *,
    pipe_id: str,
    run_id: str,
    finalized_items: list[FinalizedItem],
    missing_data: list[str] | None = None,
    source: str = "deterministic",
) -> BillOfMaterials:
    item_map = items_by_id()
    supplier_map = suppliers_by_id(load_suppliers())
    line_items: list[BomLineItem] = []
    missing = list(missing_data or [])

    for idx, finalized in enumerate(finalized_items, 1):
        item = item_map.get(finalized.item_id)
        if item is None:
            missing.append(f"Catalog item not found: {finalized.item_id}")
            continue
        offers = _best_offers(item.item_id)
        chosen = offers[0] if offers else None
        supplier = supplier_map.get(chosen.supplier_id) if chosen else None
        qty = _round_money(finalized.qty)
        unit_price = _round_money(chosen.unit_price) if chosen else None
        line_total = _round_money(qty * unit_price) if unit_price is not None else 0.0
        alternatives = []
        for alt in offers[1:4]:
            alt_supplier = supplier_map.get(alt.supplier_id)
            alternatives.append(
                {
                    "supplier_id": alt.supplier_id,
                    "supplier_name": alt_supplier.name if alt_supplier else alt.supplier_id,
                    "unit_price": alt.unit_price,
                    "lead_time_days": alt.lead_time_days,
                    "in_stock": alt.in_stock,
                }
            )
        if chosen is None:
            missing.append(f"No supplier offer for {item.item_id}")
        line_items.append(
            BomLineItem(
                line_id=f"bom-{idx:03d}",
                item_id=item.item_id,
                kind=item.kind,
                category=item.category,
                description=item.name,
                qty=qty,
                unit=item.unit,
                chosen_supplier_id=chosen.supplier_id if chosen else None,
                chosen_supplier_name=supplier.name if supplier else None,
                unit_price=unit_price,
                line_total=line_total,
                alternatives=alternatives,
                reason=finalized.reason,
            )
        )

    contract_awards = _build_contract_awards(line_items, supplier_map)
    parts_subtotal = _round_money(sum(li.line_total for li in line_items if li.kind == "part"))
    services_subtotal = _round_money(
        sum(li.line_total for li in line_items if li.kind == "service")
    )
    subtotal = _round_money(parts_subtotal + services_subtotal)
    contingency_pct = 0.15
    tax_pct = 0.13
    total_estimate = _round_money(subtotal * (1 + contingency_pct) * (1 + tax_pct))
    notes = [
        "Supplier names and contract history are seeded from Toronto non-competitive contracts.",
        "Line-item prices are synthetic estimates for decision support.",
        f"Procurement finalizer source: {source}.",
        "Draft supplier contract awards require human procurement approval.",
    ]
    return BillOfMaterials(
        pipe_id=pipe_id,
        run_id=run_id,
        line_items=line_items,
        contract_awards=contract_awards,
        parts_subtotal=parts_subtotal,
        services_subtotal=services_subtotal,
        subtotal=subtotal,
        contingency_pct=contingency_pct,
        tax_pct=tax_pct,
        total_estimate=total_estimate,
        notes=notes,
        missing_data=missing,
    )


def _build_contract_awards(
    line_items: list[BomLineItem],
    supplier_map: dict[str, object],
) -> list[ContractAwardRecommendation]:
    grouped: dict[str, list[BomLineItem]] = defaultdict(list)
    for line in line_items:
        if line.chosen_supplier_id:
            grouped[line.chosen_supplier_id].append(line)

    awards: list[ContractAwardRecommendation] = []
    for supplier_id, lines in sorted(grouped.items()):
        supplier = supplier_map[supplier_id]
        categories = [line.category.replace("_", " ") for line in lines]
        subtotal = _round_money(sum(line.line_total for line in lines))
        awards.append(
            ContractAwardRecommendation(
                supplier_id=supplier_id,
                supplier_name=getattr(supplier, "name"),
                supplier_type=getattr(supplier, "supplier_type"),
                scope=_award_scope(getattr(supplier, "supplier_type"), categories),
                line_item_ids=[line.line_id for line in lines],
                award_subtotal=subtotal,
                rationale=(
                    "Lowest evaluated supplier for these required BoM lines; "
                    "synthetic estimated pricing seeded from Toronto contract history."
                ),
                requires_human_approval=True,
            )
        )
    return sorted(awards, key=lambda a: a.award_subtotal, reverse=True)
