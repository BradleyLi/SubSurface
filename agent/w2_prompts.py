"""Workflow 2 prompt loading and message builders."""

from __future__ import annotations

import json
from pathlib import Path

from agent.schemas import AnalysisPacket, RoleName, RoleReport

PROMPTS_W2_DIR = Path(__file__).parent / "prompts" / "w2"

W2_ROLE_MAX_TOKENS = 4096
W2_SYNTHESIS_MAX_TOKENS = 8192
W2_TEMPERATURE = 0.3

_ROLE_PROMPT_FILES: dict[RoleName, str] = {
    RoleName.ENGINEER: "engineer_system.txt",
    RoleName.POLICE: "police_system.txt",
    RoleName.FIELD: "field_system.txt",
    RoleName.OPERATIONS: "operations_system.txt",
}

_ROLE_FILENAMES: dict[RoleName, str] = {
    RoleName.ENGINEER: "engineer.md",
    RoleName.POLICE: "police.md",
    RoleName.FIELD: "field_investigation.md",
    RoleName.OPERATIONS: "operations.md",
}


def load_role_system_prompt(role: RoleName) -> str:
    path = PROMPTS_W2_DIR / _ROLE_PROMPT_FILES[role]
    return path.read_text(encoding="utf-8").strip()


def load_synthesis_system_prompt() -> str:
    return (PROMPTS_W2_DIR / "synthesis_system.txt").read_text(encoding="utf-8").strip()


def role_filename(role: RoleName) -> str:
    return _ROLE_FILENAMES[role]


def build_role_messages(packet: AnalysisPacket, role: RoleName) -> list[dict[str, str]]:
    payload = packet.model_dump_json(indent=2)
    user = (
        f"Analyze the following evidence packet as the {role.value} role.\n\n"
        f"{payload}"
    )
    return [
        {"role": "system", "content": load_role_system_prompt(role)},
        {"role": "user", "content": user},
    ]


def build_synthesis_messages(
    packet: AnalysisPacket,
    role_reports: list[RoleReport],
) -> list[dict[str, str]]:
    roles_block = "\n\n---\n\n".join(
        f"### {r.role.value}\n\n{r.markdown}" for r in role_reports
    )
    user = (
        "Synthesize a final report and action plan from the evidence and role reports.\n\n"
        f"Evidence packet:\n{packet.model_dump_json(indent=2)}\n\n"
        f"Role reports:\n{roles_block}"
    )
    return [
        {"role": "system", "content": load_synthesis_system_prompt()},
        {"role": "user", "content": user},
    ]


def split_synthesis_response(raw: str) -> tuple[str, dict]:
    """Split markdown body and trailing JSON action plan."""
    text = raw.strip()
    json_start = text.rfind("{")
    if json_start == -1:
        raise ValueError("No JSON action plan in synthesis response")
    markdown_part = text[:json_start].strip()
    json_part = text[json_start:]
    return markdown_part, json.loads(json_part)
