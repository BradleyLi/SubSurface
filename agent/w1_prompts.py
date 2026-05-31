"""Workflow 1 prompt assembly (structured JSON summaries)."""

from __future__ import annotations

from pathlib import Path

from agent.schemas import PipeRiskEvidence

PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_system_prompt(name: str = "workflow1_system.txt") -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def build_json_summary_messages(evidence: PipeRiskEvidence) -> list[dict[str, str]]:
    """Chat messages for Nemotron structured Workflow 1 output."""
    user_payload = evidence.model_dump_json()
    user = (
        "Summarize this evidence as JSON matching the required schema.\n\n"
        f"{user_payload}"
    )
    return [
        {"role": "system", "content": load_system_prompt()},
        {"role": "user", "content": user},
    ]


def build_json_repair_messages(evidence: PipeRiskEvidence) -> list[dict[str, str]]:
    user_payload = evidence.model_dump_json()
    user = (
        "The previous response was invalid. Return ONLY valid JSON for this evidence:\n\n"
        f"{user_payload}"
    )
    return [
        {"role": "system", "content": load_system_prompt()},
        {"role": "user", "content": user},
    ]
