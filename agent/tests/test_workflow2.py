"""Workflow 2 unit tests (mocked Nemotron Super)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from agent.analysis_packet import build_analysis_packet
from agent.schemas import RoleName
from agent.w2_gateway import workflow2_run
from agent.w2_template import template_role_report, template_synthesis
from data_utils import get_pipes

_ROLE_MD = "# Role\n\n## Section\n\nTemplate body.\n"

_SYNTH_RAW = """# Final

## Executive summary
Done.

{
  "run_id": "PLACEHOLDER",
  "priority": "HIGH",
  "recommended_actions": [
    {
      "action": "Schedule field verification",
      "owner": "Field Investigation Crew",
      "urgency": "near_term",
      "requires_human_approval": true,
      "evidence": ["risk_percentile=90"]
    }
  ],
  "missing_data": ["valve map"],
  "model_versions": {"risk_model": "test:1", "llm": "test-super"}
}
"""


@pytest.mark.asyncio
async def test_build_analysis_packet():
    df = get_pipes(use_real=False)
    packet = build_analysis_packet(str(df.iloc[0]["pipe_id"]), df)
    assert packet.run_id
    assert len(packet.assets) == 1
    assert packet.analysis_scope.pipe_ids


@pytest.mark.asyncio
async def test_workflow2_run_mocked():
    df = get_pipes(use_real=False)
    pipe_id = str(df.iloc[0]["pipe_id"])
    packet = build_analysis_packet(pipe_id, df)

    synth = _SYNTH_RAW.replace("PLACEHOLDER", packet.run_id)

    async def mock_chat(profile, messages, **kwargs):
        _ = profile, kwargs
        content = messages[-1]["content"]
        if "Synthesize" in content or "synthesis" in content.lower():
            return synth
        return _ROLE_MD

    with patch("agent.w2_gateway.harness_chat", side_effect=mock_chat):
        result = await workflow2_run(pipe_id, df=df)

    assert result.status == "completed"
    assert result.source == "nemotron"
    assert len(result.roles) == 4
    assert result.action_plan.run_id == packet.run_id
    assert result.storage_dir


@pytest.mark.asyncio
async def test_workflow2_template_fallback():
    df = get_pipes(use_real=False)
    packet = build_analysis_packet(str(df.iloc[0]["pipe_id"]), df)
    roles = [template_role_report(packet, r) for r in RoleName]
    final_md, plan = template_synthesis(packet, roles)
    assert "Executive summary" in final_md
    assert plan.recommended_actions


@pytest.mark.asyncio
async def test_workflow2_all_template_on_failure():
    df = get_pipes(use_real=False)
    pipe_id = str(df.iloc[0]["pipe_id"])

    with patch(
        "agent.w2_gateway.harness_chat",
        AsyncMock(side_effect=RuntimeError("down")),
    ):
        result = await workflow2_run(pipe_id, df=df)

    assert result.source == "template"
    assert all(r.source == "template" for r in result.roles)
