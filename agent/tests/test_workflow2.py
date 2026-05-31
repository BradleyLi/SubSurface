"""Workflow 2 unit tests (mocked Nemotron Super)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from agent.analysis_packet import build_analysis_packet
from agent.schemas import CallerReport, PerRoleCallerContext, RoleName
from agent.w2_gateway import workflow2_run
from agent.w2_prompts import augment_system_prompt, build_role_messages
from agent.w2_template import template_role_report, template_synthesis
from agent.tests.conftest import synthetic_ml_df
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
    df = synthetic_ml_df()
    packet = build_analysis_packet(str(df.iloc[0]["pipe_id"]), df)
    assert packet.run_id
    assert len(packet.assets) == 1
    assert packet.analysis_scope.pipe_ids


@pytest.mark.asyncio
async def test_workflow2_run_mocked():
    df = synthetic_ml_df()
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
        result = await workflow2_run(
            pipe_id,
            df=df,
            use_latest_voice_transcript=False,
        )

    assert result.status == "completed"
    assert result.source == "nemotron"
    assert len(result.roles) == 4
    assert result.action_plan.run_id == packet.run_id
    assert result.storage_dir


@pytest.mark.asyncio
async def test_workflow2_template_fallback():
    df = synthetic_ml_df()
    packet = build_analysis_packet(str(df.iloc[0]["pipe_id"]), df)
    roles = [template_role_report(packet, r) for r in RoleName]
    final_md, plan = template_synthesis(packet, roles)
    assert "Executive summary" in final_md
    assert plan.recommended_actions


@pytest.mark.asyncio
async def test_workflow2_all_template_on_failure():
    df = synthetic_ml_df()
    pipe_id = str(df.iloc[0]["pipe_id"])

    with patch(
        "agent.w2_gateway.harness_chat",
        AsyncMock(side_effect=RuntimeError("down")),
    ):
        result = await workflow2_run(
            pipe_id,
            df=df,
            use_latest_voice_transcript=False,
        )

    assert result.source == "template"
    assert all(r.source == "template" for r in result.roles)


def test_augment_system_prompt_injects_caller_slice():
    base = "Base role instructions."
    out = augment_system_prompt(base, "Flooding reported at intersection.")
    assert "Caller report" in out
    assert "Flooding reported" in out
    assert augment_system_prompt(base, "") == base


@pytest.mark.asyncio
async def test_workflow2_role_system_includes_orchestrator_context():
    df = get_pipes(use_real=False)
    pipe_id = str(df.iloc[0]["pipe_id"])
    packet = build_analysis_packet(
        pipe_id,
        df,
        caller_report=CallerReport(
            session_id="s-test",
            transcript=[{"role": "user", "content": "flooding"}],
        ),
    )
    per_role = PerRoleCallerContext(
        engineer="Hydraulic concern from caller.",
        police="",
        field="",
        operations="",
        synthesis="",
    )
    messages = build_role_messages(
        packet, RoleName.ENGINEER, role_context=per_role.engineer
    )
    assert "Hydraulic concern from caller" in messages[0]["content"]
    assert "I see a lot of flooding" not in messages[0]["content"]


@pytest.mark.asyncio
async def test_workflow2_with_caller_report_calls_orchestrator():
    df = get_pipes(use_real=False)
    pipe_id = str(df.iloc[0]["pipe_id"])
    packet = build_analysis_packet(pipe_id, df)
    synth = _SYNTH_RAW.replace("PLACEHOLDER", packet.run_id)

    caller = CallerReport(
        session_id="s1",
        transcript=[{"role": "user", "content": "flooding"}],
    )
    per_role = PerRoleCallerContext(
        engineer="Engineer slice only.",
        police="",
        field="",
        operations="",
        synthesis="Synthesis slice.",
    )

    async def mock_chat(profile, messages, **kwargs):
        _ = profile, kwargs
        if messages[0]["role"] == "system" and "Triage" in messages[0]["content"]:
            return json.dumps(per_role.model_dump())
        content = messages[-1]["content"]
        if "Synthesize" in content:
            return synth
        return _ROLE_MD

    with (
        patch("agent.w2_gateway.harness_chat", side_effect=mock_chat),
        patch(
            "agent.w2_gateway.call_transcript_orchestrator",
            AsyncMock(return_value=per_role),
        ),
    ):
        result = await workflow2_run(
            pipe_id,
            df=df,
            caller_report=caller,
            use_latest_voice_transcript=False,
        )

    assert result.status == "completed"
