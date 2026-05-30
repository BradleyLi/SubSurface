"""Workflow 1 — 2–3 sentence summary from selected JSON tables."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from .client import chat
from .endpoints import EndpointConfig, WorkflowProfile

# Suggested table keys when assembling W1 input from the API layer.
TABLE_PIPE_PROFILE = "pipe_profile"
TABLE_RISK_DRIVERS = "risk_drivers"
TABLE_SHAP = "shap_drivers"
TABLE_NETWORK_CONTEXT = "network_context"
TABLE_CASCADE_IMPACT = "cascade_impact"
TABLE_SOURCE_DOCUMENT = "source_document"

_W1_SYSTEM_PROMPT = """\
You are a municipal water infrastructure analyst for Toronto's watermain network.
You receive JSON data tables selected for one pipe or segment.
Write a plain-language risk summary in exactly 2–3 sentences.
Use only facts present in the tables. Do not invent data.
No markdown headers, bullet lists, or tables in your reply — prose only.
"""


@dataclass(frozen=True)
class JsonTable:
    """One named JSON table (list of row objects)."""

    name: str
    rows: list[dict[str, Any]]


Workflow1Tables = Mapping[str, list[dict[str, Any]]] | Sequence[JsonTable]


def normalize_tables(tables: Workflow1Tables) -> dict[str, list[dict[str, Any]]]:
    if isinstance(tables, Mapping):
        normalized = {str(name): list(rows) for name, rows in tables.items()}
    else:
        normalized = {table.name: list(table.rows) for table in tables}

    if not normalized:
        raise ValueError("Workflow 1 requires at least one JSON table")

    for name, rows in normalized.items():
        if not name.strip():
            raise ValueError("JSON table names must be non-empty")
        if not isinstance(rows, list):
            raise TypeError(f"Table {name!r} must be a list of row objects, got {type(rows).__name__}")
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                raise TypeError(
                    f"Table {name!r} row {i} must be a dict, got {type(row).__name__}"
                )

    return normalized


def build_w1_messages(
    tables: Workflow1Tables,
    *,
    instruction: str | None = None,
    system_prompt: str | None = None,
) -> list[dict[str, str]]:
    """Turn selected JSON tables into chat messages for Workflow 1."""
    normalized = normalize_tables(tables)
    payload: dict[str, Any] = {"tables": normalized}
    if instruction:
        payload["instruction"] = instruction

    user_content = (
        "Summarize the following selected JSON tables.\n\n"
        f"{json.dumps(payload, indent=2, default=str)}"
    )
    return [
        {"role": "system", "content": system_prompt or _W1_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


async def summarize(
    tables: Workflow1Tables,
    *,
    instruction: str | None = None,
    system_prompt: str | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    endpoint: EndpointConfig | None = None,
    timeout: httpx.Timeout | None = None,
) -> str:
    """Generate a 2–3 sentence summary from selected JSON tables (Workflow 1)."""
    messages = build_w1_messages(
        tables, instruction=instruction, system_prompt=system_prompt
    )
    return await chat(
        WorkflowProfile.WORKFLOW1,
        messages,
        max_tokens=max_tokens,
        temperature=temperature,
        endpoint=endpoint,
        timeout=timeout,
    )
