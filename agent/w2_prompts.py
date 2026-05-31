"""Workflow 2 prompt loading and message builders."""

from __future__ import annotations

import json
from pathlib import Path

from agent.schemas import AnalysisPacket, RoleName, RoleReport

PROMPTS_W2_DIR = Path(__file__).parent / "prompts" / "w2"

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


def load_orchestrator_system_prompt() -> str:
    return (
        PROMPTS_W2_DIR / "transcript_orchestrator_system.txt"
    ).read_text(encoding="utf-8").strip()


_CALLER_CONTEXT_HEADER = """## Caller report — unverified field intelligence
{body}
Treat the above as unverified caller intelligence. Cross-check with the evidence packet.
Do not invent facts not stated in the call."""


def augment_system_prompt(base: str, role_context: str) -> str:
    """Append orchestrator-curated caller intelligence to a role system prompt."""
    ctx = (role_context or "").strip()
    if not ctx:
        return base
    block = _CALLER_CONTEXT_HEADER.format(body=ctx)
    return f"{base}\n\n{block}"


def role_filename(role: RoleName) -> str:
    return _ROLE_FILENAMES[role]


def build_role_messages(
    packet: AnalysisPacket,
    role: RoleName,
    *,
    role_context: str = "",
) -> list[dict[str, str]]:
    payload = packet.model_dump_json(indent=2)
    user = (
        f"Analyze the following evidence packet as the {role.value} role.\n\n"
        f"{payload}"
    )
    system = augment_system_prompt(load_role_system_prompt(role), role_context)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_synthesis_messages(
    packet: AnalysisPacket,
    role_reports: list[RoleReport],
    *,
    synthesis_context: str = "",
) -> list[dict[str, str]]:
    roles_block = "\n\n---\n\n".join(
        f"### {r.role.value}\n\n{r.markdown}" for r in role_reports
    )
    user = (
        "Synthesize a final report and action plan from the evidence and role reports.\n\n"
        f"Evidence packet:\n{packet.model_dump_json(indent=2)}\n\n"
        f"Role reports:\n{roles_block}"
    )
    system = augment_system_prompt(
        load_synthesis_system_prompt(), synthesis_context
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def split_synthesis_response(raw: str) -> tuple[str, dict]:
    """Split markdown body and trailing JSON action plan."""
    from agent.json_utils import extract_json_object

    text = raw.strip()
    json_blob = extract_json_object(text)
    json_start = text.find(json_blob)
    if json_start == -1:
        raise ValueError("No JSON action plan in synthesis response")
    markdown_part = text[:json_start].strip()
    return markdown_part, json.loads(json_blob)
