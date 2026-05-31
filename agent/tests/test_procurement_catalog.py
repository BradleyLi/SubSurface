from agent.procurement.catalog import load_catalog, load_offers, load_suppliers, normalize_material


def test_catalog_and_suppliers_load():
    items = load_catalog()
    suppliers = load_suppliers()
    offers = load_offers()

    assert items
    assert suppliers
    assert offers
    assert {s.supplier_type for s in suppliers} >= {
        "pipe_construction",
        "mechanical_parts_service",
        "paving_restoration",
        "utility_locates",
        "dewatering_pumping",
        "environmental_response",
        "equipment_rental",
        "electrical_supply",
    }
    offered_item_ids = {offer.item_id for offer in offers}
    assert all(item.item_id in offered_item_ids for item in items)


def test_material_aliases():
    assert normalize_material("DIP") == "Ductile Iron"
    assert normalize_material("CI") == "Cast Iron"
    assert normalize_material("PE") == "PVC"
