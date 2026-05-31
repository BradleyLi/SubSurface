"""Load procurement catalog and supplier offers."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from agent.schemas import CatalogItem, Supplier, SupplierPartOffer

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = REPO_ROOT / "data" / "procurement" / "supplier_details_bom_synthetic_data"
GENERATED_DIR = DATA_ROOT / "generated"
DEFAULT_CATALOG = GENERATED_DIR / "repair_parts_catalog.json"
DEFAULT_SUPPLIERS = GENERATED_DIR / "toronto_suppliers.json"

MATERIAL_ALIASES: dict[str, str] = {
    "dip": "Ductile Iron",
    "ductile iron": "Ductile Iron",
    "di": "Ductile Iron",
    "ci": "Cast Iron",
    "cast iron": "Cast Iron",
    "pe": "PVC",
    "polyethylene": "PVC",
    "pvc": "PVC",
    "ac": "Asbestos Cement",
    "asbestos cement": "Asbestos Cement",
    "concrete": "Concrete",
}


def catalog_path() -> Path:
    return Path(os.getenv("PROCUREMENT_CATALOG", str(DEFAULT_CATALOG)))


def suppliers_path() -> Path:
    return Path(os.getenv("PROCUREMENT_SUPPLIERS", str(DEFAULT_SUPPLIERS)))


def normalize_material(material: str | None) -> str | None:
    if material is None:
        return None
    return MATERIAL_ALIASES.get(str(material).strip().lower(), str(material).strip())


@lru_cache(maxsize=4)
def load_catalog(path: str | None = None) -> tuple[CatalogItem, ...]:
    p = Path(path) if path else catalog_path()
    data = json.loads(p.read_text(encoding="utf-8"))
    return tuple(CatalogItem.model_validate(item) for item in data.get("items", []))


@lru_cache(maxsize=4)
def load_suppliers(path: str | None = None) -> tuple[Supplier, ...]:
    p = Path(path) if path else suppliers_path()
    data = json.loads(p.read_text(encoding="utf-8"))
    return tuple(Supplier.model_validate(s) for s in data.get("suppliers", []))


@lru_cache(maxsize=4)
def load_offers(path: str | None = None) -> tuple[SupplierPartOffer, ...]:
    p = Path(path) if path else suppliers_path()
    data = json.loads(p.read_text(encoding="utf-8"))
    return tuple(SupplierPartOffer.model_validate(o) for o in data.get("offers", []))


def items_by_id(items: tuple[CatalogItem, ...] | None = None) -> dict[str, CatalogItem]:
    catalog = items if items is not None else load_catalog()
    return {item.item_id: item for item in catalog}


def suppliers_by_id(suppliers: tuple[Supplier, ...] | None = None) -> dict[str, Supplier]:
    supplier_list = suppliers if suppliers is not None else load_suppliers()
    return {supplier.supplier_id: supplier for supplier in supplier_list}


def item_matches_pipe(
    item: CatalogItem,
    *,
    material: str | None,
    diameter_mm: int | None,
) -> bool:
    normalized = normalize_material(material)
    if item.kind == "part" and diameter_mm is not None and item.diameter_mm != diameter_mm:
        return False
    if item.material_compatibility and normalized:
        return normalized in item.material_compatibility
    return True
