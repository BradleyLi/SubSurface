"""Workflow 1 unit tests (no live Nemotron required)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from agent.evidence import build_evidence_from_row, evidence_to_w1_tables
from agent.gateway import workflow1_summary
from agent.harness.endpoints import WorkflowProfile, get_endpoint
from agent.json_utils import extract_json_object, parse_json_object
from agent.template_summary import template_summary
from agent.w1_prompts import build_json_summary_messages
from data_utils import get_pipes


def test_evidence_builder_required_fields():
    df = get_pipes(use_real=False)
    row = df.iloc[0]
    ev = build_evidence_from_row(row, df=df)
    assert ev.pipe_id == row["pipe_id"]
    assert 0.0 <= ev.predicted_break_probability <= 1.0
    assert len(ev.top_shap_contributors) >= 1


def test_evidence_to_w1_tables():
    df = get_pipes(use_real=False)
    ev = build_evidence_from_row(df.iloc[0], df=df)
    tables = evidence_to_w1_tables(ev)
    assert "pipe_profile" in tables
    assert "shap_drivers" in tables
    assert tables["pipe_profile"][0]["pipe_id"] == ev.pipe_id
    assert len(tables["shap_drivers"]) >= 1


def test_build_json_summary_messages():
    df = get_pipes(use_real=False)
    ev = build_evidence_from_row(df.iloc[0], df=df)
    messages = build_json_summary_messages(ev)
    assert messages[0]["role"] == "system"
    assert ev.pipe_id in messages[1]["content"]


def test_w1_endpoint_uses_settings():
    cfg = get_endpoint(WorkflowProfile.WORKFLOW1)
    assert cfg.model
    assert "11436" in cfg.base_url or cfg.base_url  # default or legacy env


def test_template_summary_matches_probability():
    df = get_pipes(use_real=False)
    row = df.nlargest(1, "risk_score").iloc[0]
    ev = build_evidence_from_row(row, df=df)
    summary = template_summary(ev)
    prob_pct = f"{ev.predicted_break_probability * 100:.1f}"
    assert prob_pct in summary.risk_sentence
    assert summary.pipe_id == ev.pipe_id


def test_parse_json_from_fenced_block():
    raw = 'Here is output:\n```json\n{"pipe_id": "X", "headline": "h", "risk_sentence": "r", "top_reasons": ["a"], "recommended_next_step": "s", "caveats": ["c"]}\n```'
    data = parse_json_object(raw)
    assert data["pipe_id"] == "X"


def test_workflow1_summary_uses_mock_nemotron():
    df = get_pipes(use_real=False)
    pipe_id = str(df.iloc[0]["pipe_id"])
    mock_json = json.dumps(
        {
            "pipe_id": pipe_id,
            "headline": "Test headline",
            "risk_sentence": "Test risk sentence with 12.3% probability.",
            "top_reasons": ["Reason one"],
            "recommended_next_step": "Review pipe",
            "caveats": ["Model estimate only"],
        }
    )

    with patch("agent.gateway.chat_completion_messages", return_value=mock_json):
        resp = workflow1_summary(pipe_id, df=df)

    assert resp.source == "nemotron"
    assert resp.summary.headline == "Test headline"


def test_workflow1_summary_fallback_on_bad_llm():
    df = get_pipes(use_real=False)
    pipe_id = str(df.iloc[0]["pipe_id"])

    with patch("agent.gateway.chat_completion_messages", return_value="not json at all"):
        resp = workflow1_summary(pipe_id, df=df)

    assert resp.source == "template"
    assert resp.summary.pipe_id == pipe_id


def test_extract_json_object_raises():
    with pytest.raises(ValueError):
        extract_json_object("no braces here")


@pytest.mark.asyncio
async def test_harness_chat_json_mode_delegates_native():
    from agent.harness.client import chat

    mock_native = AsyncMock(return_value='{"ok": true}')
    with patch("agent.harness.client._chat_native_json", mock_native):
        result = await chat(
            WorkflowProfile.WORKFLOW1,
            [{"role": "user", "content": "hi"}],
            json_mode=True,
        )
    assert result == '{"ok": true}'
    mock_native.assert_awaited_once()
