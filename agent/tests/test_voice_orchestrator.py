"""Tests for transcript triage orchestrator."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from agent.schemas import CallerReport, PerRoleCallerContext
from agent.w2_orchestrator import call_transcript_orchestrator


@pytest.mark.asyncio
async def test_orchestrator_parses_json():
    caller = CallerReport(
        session_id="s1",
        transcript=[
            {"role": "user", "content": "Flooding at Yonge and Bloor"},
            {"role": "assistant", "content": "No injuries reported."},
        ],
    )
    orch_json = json.dumps(
        {
            "engineer": "Surface flooding may indicate main break.",
            "police": "No injuries.",
            "field": "Visible flooding at intersection.",
            "operations": "Possible service disruption.",
            "synthesis": "Flooding at Yonge/Bloor, no injuries.",
        }
    )

    with patch(
        "agent.w2_orchestrator.harness_chat",
        AsyncMock(return_value=orch_json),
    ):
        result = await call_transcript_orchestrator(caller)

    assert isinstance(result, PerRoleCallerContext)
    assert "flooding" in result.field.lower()
    assert "injuries" in result.police.lower()


@pytest.mark.asyncio
async def test_orchestrator_fallback_on_failure():
    caller = CallerReport(session_id="s2", transcript=[])

    with patch(
        "agent.w2_orchestrator.harness_chat",
        AsyncMock(side_effect=RuntimeError("down")),
    ):
        result = await call_transcript_orchestrator(caller)

    assert result == PerRoleCallerContext()
