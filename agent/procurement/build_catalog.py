"""Build synthetic procurement catalog seeded from Toronto contract suppliers."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from agent.schemas import CatalogItem, Supplier, SupplierPartOffer

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = REPO_ROOT / "data" / "procurement" / "supplier_details_bom_synthetic_data"
SOURCE_CSV = DATA_ROOT / "source" / "non_competitive_contracts.csv"
GENERATED_DIR = DATA_ROOT / "generated"
CATALOG_JSON = GENERATED_DIR / "repair_parts_catalog.json"
SUPPLIERS_JSON = GENERATED_DIR / "toronto_suppliers.json"

WARD_POOL = ["Toronto", "Etobicoke", "North York", "Scarborough", "East York", "York"]
DIAMETERS_MM = [100, 150, 200, 250, 300, 400]
MATERIALS = ["Cast Iron", "Ductile Iron", "PVC", "Concrete", "Asbestos Cement"]

SUPPLIER_ALLOWLIST: dict[str, str] = {
    "fer-pal construction": "pipe_construction",
    "clearway construction": "pipe_construction",
    "ojcr construction": "pipe_construction",
    "rabcon contractors": "pipe_construction",
    "link-line contractors": "pipe_construction",
    "cipparrone construction": "pipe_construction",
    "co-x-co construction": "pipe_construction",
    "vipe construction": "pipe_construction",
    "ws nicholls construction": "pipe_construction",
    "sanscon construction": "pipe_construction",
    "supco construction": "pipe_construction",
    "pvs contractors": "pipe_construction",
    "grascan construction": "pipe_construction",
    "il duca contracting": "pipe_construction",
    "bennett mechanical": "mechanical_parts_service",
    "ainsworth": "mechanical_parts_service",
    "lakeside process controls": "mechanical_parts_service",
    "vector process equipment": "mechanical_parts_service",
    "pro aqua": "mechanical_parts_service",
    "evoqua water": "mechanical_parts_service",
    "ovivo": "mechanical_parts_service",
    "alfa laval": "mechanical_parts_service",
    "bond paving": "paving_restoration",
    "finch paving": "paving_restoration",
    "qx locates": "utility_locates",
    "multiview locates": "utility_locates",
    "link utility technologies": "utility_locates",
    "promark telecon": "utility_locates",
    "john knox pumping": "dewatering_pumping",
    "accuworx": "environmental_response",
    "gfl environmental": "environmental_response",
    "envirocan": "environmental_response",
    "united rentals": "equipment_rental",
    "super save fence": "equipment_rental",
    "joe johnson equipment": "equipment_rental",
    "toromont": "equipment_rental",
    "westburne": "electrical_supply",
    "gescan": "electrical_supply",
    "directrik": "electrical_supply",
}

BASE_PARTS: dict[str, dict[str, Any]] = {
    "repair_clamp": {"unit": "each", "base": 430, "name": "Stainless repair clamp"},
    "full_circle_clamp": {"unit": "each", "base": 760, "name": "Full-circle repair clamp"},
    "coupling": {"unit": "each", "base": 520, "name": "Restrained coupling"},
    "gate_valve": {"unit": "each", "base": 1250, "name": "Resilient-seat gate valve"},
    "pipe_section": {"unit": "m", "base": 185, "name": "Replacement pipe section"},
    "gasket": {"unit": "each", "base": 65, "name": "Watermain gasket kit"},
    "bolt_kit": {"unit": "each", "base": 95, "name": "Stainless bolt kit"},
    "restraint_fitting": {"unit": "each", "base": 340, "name": "Mechanical restraint fitting"},
    "bedding_material": {"unit": "m", "base": 48, "name": "Granular bedding material"},
    "mechanical_fitting": {"unit": "each", "base": 610, "name": "Mechanical repair fitting"},
}

BASE_SERVICES: dict[str, dict[str, Any]] = {
    "road_restoration": {"unit": "lot", "base": 6500, "name": "Road cut restoration"},
    "traffic_control": {"unit": "day", "base": 2200, "name": "Traffic control setup"},
    "dewatering": {"unit": "day", "base": 1800, "name": "Dewatering and pumping"},
    "utility_locate": {"unit": "lot", "base": 850, "name": "Emergency utility locates"},
    "environmental_cleanup": {"unit": "lot", "base": 2400, "name": "Environmental cleanup response"},
    "excavation_equipment": {"unit": "day", "base": 3200, "name": "Excavation equipment rental"},
    "mechanical_repair_service": {"unit": "day", "base": 3600, "name": "Mechanical repair service crew"},
    "electrical_service": {"unit": "lot", "base": 1600, "name": "Electrical service support"},
}

SUPPLIER_ITEM_TYPES: dict[str, set[str]] = {
    "pipe_construction": {
        "repair_clamp",
        "full_circle_clamp",
        "coupling",
        "pipe_section",
        "gasket",
        "bolt_kit",
        "restraint_fitting",
        "bedding_material",
        "mechanical_fitting",
        "road_restoration",
        "excavation_equipment",
    },
    "mechanical_parts_service": {
        "repair_clamp",
        "full_circle_clamp",
        "coupling",
        "gate_valve",
        "gasket",
        "bolt_kit",
        "restraint_fitting",
        "mechanical_fitting",
        "mechanical_repair_service",
    },
    "paving_restoration": {"road_restoration", "traffic_control"},
    "utility_locates": {"utility_locate"},
    "dewatering_pumping": {"dewatering"},
    "environmental_response": {"environmental_cleanup", "dewatering"},
    "equipment_rental": {"excavation_equipment", "traffic_control"},
    "electrical_supply": {"electrical_service", "gate_valve"},
}


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _supplier_id(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:6]
    return f"supp_{cleaned[:34]}_{digest}"


def _canonical_name(name: str) -> str:
    name = re.sub(r"\s+", " ", name).strip()
    words = []
    for word in name.split(" "):
        if word.upper() in {"INC", "LTD", "LLC", "GMBH", "CIPP"}:
            words.append(word.upper())
        else:
            words.append(word.capitalize())
    return " ".join(words).replace(" Inc.", " Inc").replace(" Ltd.", " Ltd")


def _match_supplier_type(name: str, division: str) -> str | None:
    k = _key(name)
    for needle, supplier_type in SUPPLIER_ALLOWLIST.items():
        if needle in k:
            return supplier_type
    if division not in {"Toronto Water", "Engineering & Construction Services - Engineering Services"}:
        return None
    if "construction" in k or "contract" in k:
        return "pipe_construction"
    return None


def _stable_fraction(*parts: str) -> float:
    raw = "|".join(parts).encode("utf-8")
    return int(hashlib.sha1(raw).hexdigest()[:8], 16) / 0xFFFFFFFF


def _supplier_multiplier(contract_max: float | None) -> float:
    if not contract_max or contract_max <= 0:
        return 1.0
    # Larger contractors carry higher overhead but often faster availability.
    return round(0.85 + min(math.log10(contract_max + 10) / 12, 0.55), 3)


def _wards_for_supplier(supplier_id: str) -> list[str]:
    start = int(_stable_fraction(supplier_id) * len(WARD_POOL))
    return [WARD_POOL[(start + i) % len(WARD_POOL)] for i in range(3)]


def load_seed_suppliers(path: Path = SOURCE_CSV) -> list[Supplier]:
    grouped: dict[str, dict[str, Any]] = {}
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            name = (row.get("Supplier Name") or "").strip()
            division = (row.get("Division") or "").strip()
            supplier_type = _match_supplier_type(name, division)
            if not name or supplier_type is None:
                continue
            key = _key(name)
            amount_raw = (
                str(row.get("Contract Amount") or "0")
                .replace(",", "")
                .replace("$", "")
            )
            amount = float(amount_raw or 0)
            current = grouped.setdefault(
                key,
                {
                    "name": _canonical_name(name),
                    "supplier_type": supplier_type,
                    "real_contract_max": 0.0,
                },
            )
            current["real_contract_max"] = max(current["real_contract_max"], amount)
    suppliers: list[Supplier] = []
    for data in sorted(grouped.values(), key=lambda d: (d["supplier_type"], d["name"])):
        sid = _supplier_id(data["name"])
        suppliers.append(
            Supplier(
                supplier_id=sid,
                name=data["name"],
                supplier_type=data["supplier_type"],
                real_contract_max=round(float(data["real_contract_max"]), 2),
                wards_served=_wards_for_supplier(sid),
                contact="synthetic-procurement@example.invalid",
            )
        )
    return suppliers


def build_catalog_items() -> list[CatalogItem]:
    items: list[CatalogItem] = []
    for category, meta in BASE_PARTS.items():
        for diameter in DIAMETERS_MM:
            items.append(
                CatalogItem(
                    item_id=f"{category}_{diameter}mm",
                    kind="part",
                    category=category,
                    name=f"{meta['name']} ({diameter} mm)",
                    material_compatibility=MATERIALS,
                    diameter_mm=diameter,
                    unit=meta["unit"],
                    spec=f"Synthetic Toronto watermain repair item sized for {diameter} mm mains.",
                )
            )
    for category, meta in BASE_SERVICES.items():
        items.append(
            CatalogItem(
                item_id=category,
                kind="service",
                category=category,
                name=meta["name"],
                material_compatibility=[],
                diameter_mm=None,
                unit=meta["unit"],
                spec="Synthetic blast-radius service estimate seeded from Toronto contract suppliers.",
            )
        )
    return items


def _base_price(item: CatalogItem) -> float:
    meta = BASE_PARTS.get(item.category) or BASE_SERVICES[item.category]
    diameter_factor = 1.0
    if item.diameter_mm:
        diameter_factor = max(item.diameter_mm / 150, 0.75) ** 0.82
    return float(meta["base"]) * diameter_factor


def build_offers(suppliers: list[Supplier], items: list[CatalogItem]) -> list[SupplierPartOffer]:
    offers: list[SupplierPartOffer] = []
    for supplier in suppliers:
        allowed = SUPPLIER_ITEM_TYPES.get(supplier.supplier_type, set())
        multiplier = _supplier_multiplier(supplier.real_contract_max)
        for item in items:
            if item.category not in allowed:
                continue
            jitter = 0.88 + (_stable_fraction(supplier.supplier_id, item.item_id) * 0.28)
            unit_price = round(_base_price(item) * multiplier * jitter, 2)
            lead_time = 1 + int(_stable_fraction(item.item_id, supplier.supplier_id) * 6)
            in_stock = _stable_fraction("stock", item.item_id, supplier.supplier_id) > 0.12
            offers.append(
                SupplierPartOffer(
                    supplier_id=supplier.supplier_id,
                    item_id=item.item_id,
                    unit_price=unit_price,
                    min_order_qty=1.0,
                    lead_time_days=lead_time,
                    in_stock=in_stock,
                )
            )
    return offers


def build_outputs() -> tuple[list[CatalogItem], list[Supplier], list[SupplierPartOffer]]:
    suppliers = load_seed_suppliers()
    items = build_catalog_items()
    offers = build_offers(suppliers, items)
    return items, suppliers, offers


def main() -> None:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    items, suppliers, offers = build_outputs()
    CATALOG_JSON.write_text(
        json.dumps({"items": [i.model_dump() for i in items]}, indent=2),
        encoding="utf-8",
    )
    SUPPLIERS_JSON.write_text(
        json.dumps(
            {
                "suppliers": [s.model_dump() for s in suppliers],
                "offers": [o.model_dump() for o in offers],
                "notes": [
                    "Supplier names and real_contract_max values are seeded from Toronto non-competitive contracts.",
                    "Per-item prices are synthetic estimates for demo procurement analysis.",
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {CATALOG_JSON} ({len(items)} items)")
    print(f"Wrote {SUPPLIERS_JSON} ({len(suppliers)} suppliers, {len(offers)} offers)")


if __name__ == "__main__":
    main()
