"""LLM finalize step for procurement candidate items."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent.harness.client import chat as harness_chat
from agent.harness.endpoints import WorkflowProfile
from agent.json_utils import parse_json_object
from agent.procurement.part_selection import CandidateItem
from agent.schemas import AnalysisPacket

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "w2" / "procurement_system.txt"


@dataclass(frozen=True)
class FinalizedItem:
    item_id: str
    qty: float
    reason: str


def _fallback(candidates: list[CandidateItem]) -> list[FinalizedItem]:
    return [
        FinalizedItem(item_id=c.item.item_id, qty=c.qty, reason=c.reason)
        for c in candidates
    ]


def _candidate_payload(candidates: list[CandidateItem]) -> list[dict]:
    return [
        {
            "item_id": c.item.item_id,
            "kind": c.item.kind,
            "category": c.item.category,
            "name": c.item.name,
            "unit": c.item.unit,
            "qty": c.qty,
            "reason": c.reason,
        }
        for c in candidates
    ]


async def finalize_items_llm(
    packet: AnalysisPacket,
    candidates: list[CandidateItem],
    *,
    role_context: str = "",
) -> tuple[list[FinalizedItem], list[str], str]:
    """Finalize candidate quantities via W2 LLM, falling back deterministically."""
    if not candidates:
        return [], ["No procurement candidates selected."], "deterministic"

    allowed = {c.item.item_id for c in candidates}
    user = {
        "evidence": packet.model_dump(mode="json"),
        "caller_context": role_context,
        "candidate_items": _candidate_payload(candidates),
    }
    messages = [
        {"role": "system", "content": PROMPT_PATH.read_text(encoding="utf-8").strip()},
        {"role": "user", "content": str(user)},
    ]
    try:
        raw = await harness_chat(
            WorkflowProfile.WORKFLOW2,
            messages,
            max_tokens=700,
            temperature=0.1,
            json_mode=True,
        )
        data = parse_json_object(raw)
        finalized: list[FinalizedItem] = []
        for item in data.get("items", []):
            item_id = str(item.get("item_id") or "")
            if item_id not in allowed:
                continue
            try:
                qty = max(float(item.get("qty", 1)), 0.0)
            except (TypeError, ValueError):
                qty = 1.0
            finalized.append(
                FinalizedItem(
                    item_id=item_id,
                    qty=qty,
                    reason=str(item.get("reason") or "Selected by procurement finalizer."),
                )
            )
        if not finalized:
            raise ValueError("Procurement finalizer returned no valid items")
        missing = [str(x) for x in data.get("missing_data", [])]
        return finalized, missing, "nemotron"
    except Exception:
        return _fallback(candidates), [], "deterministic"
