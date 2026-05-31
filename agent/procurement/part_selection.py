"""Deterministic candidate item selection for watermain repair BoMs."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from agent.procurement.catalog import item_matches_pipe, load_catalog
from agent.schemas import CatalogItem, PipeRiskEvidence


@dataclass(frozen=True)
class CandidateItem:
    item: CatalogItem
    qty: float
    reason: str


def transcript_text_from_packet(transcript: list[dict[str, str]] | None) -> str:
    return " ".join((entry.get("content") or "") for entry in transcript or [])


def _has_any(text: str, words: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(word)}\b", text) for word in words)


def _service_days(evidence: PipeRiskEvidence, base: float = 1.0) -> float:
    props = evidence.properties_affected or 0
    diameter = evidence.diameter_mm or 150
    scale = 1.0
    if props >= 75 or diameter >= 300:
        scale += 1.0
    elif props >= 25 or diameter >= 200:
        scale += 0.5
    return round(base * scale, 1)


def _pipe_qty(evidence: PipeRiskEvidence) -> float:
    length = evidence.length_m or 6
    return float(max(1, min(12, math.ceil(length * 0.08))))


def _add_category(
    out: dict[str, CandidateItem],
    category: str,
    evidence: PipeRiskEvidence,
    qty: float,
    reason: str,
) -> None:
    for item in load_catalog():
        if item.category != category:
            continue
        if not item_matches_pipe(
            item,
            material=evidence.material,
            diameter_mm=evidence.diameter_mm,
        ):
            continue
        out[item.item_id] = CandidateItem(item=item, qty=qty, reason=reason)
        return


def select_candidate_items(
    evidence: PipeRiskEvidence,
    transcript_text: str = "",
) -> list[CandidateItem]:
    """Select a conservative candidate BoM from evidence and transcript keywords."""
    text = transcript_text.lower()
    candidates: dict[str, CandidateItem] = {}

    _add_category(candidates, "utility_locate", evidence, 1.0, "Locates precede excavation.")

    strong_signal = False
    if _has_any(text, ("burst", "break", "broken", "main break", "watermain break")):
        strong_signal = True
        _add_category(candidates, "full_circle_clamp", evidence, 1.0, "Transcript indicates break/burst.")
        _add_category(candidates, "pipe_section", evidence, _pipe_qty(evidence), "Possible replacement spool for break repair.")
        _add_category(candidates, "dewatering", evidence, _service_days(evidence), "Break response may need pumping.")
        _add_category(candidates, "road_restoration", evidence, 1.0, "Break response may disturb roadway.")

    if _has_any(text, ("leak", "leaking", "joint", "seep", "spray")):
        strong_signal = True
        _add_category(candidates, "repair_clamp", evidence, 1.0, "Transcript indicates leak/joint issue.")
        _add_category(candidates, "gasket", evidence, 2.0, "Leak repair kit staging.")
        _add_category(candidates, "bolt_kit", evidence, 1.0, "Leak repair kit staging.")

    if _has_any(text, ("valve", "shutoff", "shut off", "isolate", "isolation")):
        strong_signal = True
        _add_category(candidates, "gate_valve", evidence, 1.0, "Transcript mentions valve/isolation.")

    if _has_any(text, ("flood", "flooding", "sinkhole", "road", "lane", "pavement")):
        strong_signal = True
        _add_category(candidates, "road_restoration", evidence, 1.0, "Road or flooding impact reported.")
        _add_category(candidates, "traffic_control", evidence, _service_days(evidence), "Road impact may require traffic control.")

    if _has_any(text, ("sewage", "contam", "contamination", "fuel", "spill")):
        strong_signal = True
        _add_category(candidates, "environmental_cleanup", evidence, 1.0, "Potential contamination concern.")

    if not strong_signal:
        _add_category(candidates, "repair_clamp", evidence, 1.0, "Baseline repair contingency.")
        _add_category(candidates, "gasket", evidence, 2.0, "Baseline repair contingency.")
        _add_category(candidates, "bolt_kit", evidence, 1.0, "Baseline repair contingency.")

    _add_category(candidates, "excavation_equipment", evidence, _service_days(evidence), "Excavation equipment staging estimate.")
    return list(candidates.values())
