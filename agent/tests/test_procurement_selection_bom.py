from agent.procurement.bom import build_bom
from agent.procurement.finalize import FinalizedItem
from agent.procurement.part_selection import select_candidate_items
from agent.schemas import PipeRiskEvidence, ShapContributor


def _evidence() -> PipeRiskEvidence:
    return PipeRiskEvidence(
        pipe_id="WM_TEST",
        predicted_break_probability=0.82,
        risk_percentile=96.0,
        risk_category="CRITICAL",
        ward="Scarborough",
        material="Ductile Iron",
        age_years=55,
        diameter_mm=200,
        length_m=80,
        properties_affected=42,
        emergency_cost=150000,
        top_shap_contributors=[
            ShapContributor(
                feature_label="pipe age",
                feature_value=55,
                impact="increase_risk",
                shap_contribution=0.8,
            )
        ],
    )


def test_burst_transcript_selects_parts_and_services():
    selected = select_candidate_items(
        _evidence(),
        "Caller reports a burst watermain with flooding across the road.",
    )
    categories = {candidate.item.category for candidate in selected}
    assert "full_circle_clamp" in categories
    assert "pipe_section" in categories
    assert "dewatering" in categories
    assert "road_restoration" in categories
    assert "utility_locate" in categories


def test_bom_chooses_suppliers_and_groups_awards():
    selected = select_candidate_items(_evidence(), "leak at the joint")
    finalized = [
        FinalizedItem(
            item_id=candidate.item.item_id,
            qty=candidate.qty,
            reason=candidate.reason,
        )
        for candidate in selected
    ]
    bom = build_bom(
        pipe_id="WM_TEST",
        run_id="run-test",
        finalized_items=finalized,
        source="test",
    )
    assert bom.line_items
    assert bom.contract_awards
    assert bom.parts_subtotal > 0
    assert bom.services_subtotal > 0
    assert bom.total_estimate > bom.subtotal
    assert all(award.requires_human_approval for award in bom.contract_awards)
    assert {line.line_id for line in bom.line_items} >= {
        line_id
        for award in bom.contract_awards
        for line_id in award.line_item_ids
    }
