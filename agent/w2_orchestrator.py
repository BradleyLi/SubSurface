"""Transcript triage orchestrator: per-role context from a voice call."""

from __future__ import annotations

import logging

from agent.harness.client import chat as harness_chat
from agent.harness.endpoints import WorkflowProfile
from agent.json_utils import parse_json_object
from agent.schemas import CallerReport, PerRoleCallerContext
from agent.voice_context import format_transcript_for_orchestrator
from agent.w2_prompts import load_orchestrator_system_prompt

logger = logging.getLogger(__name__)

_ORCHESTRATOR_MAX_TOKENS = 512
_ORCHESTRATOR_TEMPERATURE = 0.2


async def call_transcript_orchestrator(
    caller_report: CallerReport,
) -> PerRoleCallerContext:
    """One LLM call: split transcript facts across W2 roles."""
    payload = {
        "session_id": caller_report.session_id,
        "ended_at": caller_report.ended_at,
        "incident": {"location": caller_report.location},
        "transcript": caller_report.transcript,
    }
    user_text = format_transcript_for_orchestrator(payload)
    messages = [
        {"role": "system", "content": load_orchestrator_system_prompt()},
        {
            "role": "user",
            "content": (
                "Triage this voice call transcript for the specialist roles.\n\n"
                f"{user_text}"
            ),
        },
    ]
    try:
        raw = await harness_chat(
            WorkflowProfile.WORKFLOW2,
            messages,
            max_tokens=_ORCHESTRATOR_MAX_TOKENS,
            temperature=_ORCHESTRATOR_TEMPERATURE,
            json_mode=False,
        )
        data = parse_json_object(raw)
        return PerRoleCallerContext.model_validate(data)
    except Exception as exc:
        logger.warning("Transcript orchestrator failed: %s", exc)
        return PerRoleCallerContext()
