"""
Workflow 1 gateway: evidence → Nemotron (via harness) → validated summary.
"""

from __future__ import annotations

import json

import pandas as pd

from agent.evidence import build_evidence_from_row
from agent.harness.endpoints import WorkflowProfile, get_endpoint
from agent.json_utils import parse_json_object
from agent.llm_client import chat_completion_messages
from agent.schemas import PipeRiskEvidence, RiskSummaryResponse, Workflow1Summary
from agent.template_summary import template_summary
from agent.w1_prompts import build_json_repair_messages, build_json_summary_messages
from data_utils import get_pipes_uncached
from ml_predictions import find_pipe_row

PROMPT_VERSION = "workflow1-v1"


def workflow1_summary(
    pipe_id: str,
    *,
    use_real: bool = True,
    df: pd.DataFrame | None = None,
) -> RiskSummaryResponse:
    """
    Build evidence for pipe_id, call Nemotron, validate JSON, or use template fallback.
    """
    if df is None:
        df = get_pipes_uncached(use_real=use_real)

    row = find_pipe_row(df, pipe_id)
    if row is None:
        raise KeyError(f"Pipe not found: {pipe_id}")

    evidence = build_evidence_from_row(row, df=df)
    endpoint = get_endpoint(WorkflowProfile.WORKFLOW1)

    try:
        summary = _call_nemotron(evidence)
        return RiskSummaryResponse(
            summary=summary,
            source="nemotron",
            model=endpoint.model,
            evidence=evidence,
        )
    except Exception:
        return RiskSummaryResponse(
            summary=template_summary(evidence),
            source="template",
            model=None,
            evidence=evidence,
        )


def _call_nemotron(evidence: PipeRiskEvidence) -> Workflow1Summary:
    messages = build_json_summary_messages(evidence)
    raw = chat_completion_messages(messages)
    try:
        data = parse_json_object(raw)
    except (ValueError, json.JSONDecodeError):
        raw = chat_completion_messages(build_json_repair_messages(evidence))
        data = parse_json_object(raw)

    data["pipe_id"] = evidence.pipe_id
    if isinstance(data.get("caveats"), str):
        data["caveats"] = [data["caveats"]]
    return Workflow1Summary.model_validate(data)
