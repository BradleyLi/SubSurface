"""
Sync facade over agent.harness for Workflow 1 (and future W2) LLM calls.
"""

from __future__ import annotations

import asyncio

from agent.harness.client import chat as harness_chat
from agent.harness.endpoints import WorkflowProfile, get_endpoint
from agent.harness.health import check_profile
from agent.w1_prompts import W1_JSON_MAX_TOKENS, W1_JSON_TEMPERATURE, load_system_prompt
from agent.w2_prompts import W2_ROLE_MAX_TOKENS, W2_SYNTHESIS_MAX_TOKENS, W2_TEMPERATURE

__all__ = [
    "chat_completion",
    "chat_completion_messages",
    "chat_completion_w2_messages",
    "llm_reachable",
    "llm_reachable_w2",
    "load_system_prompt",
    "workflow1_endpoint",
    "workflow2_endpoint",
]


def workflow1_endpoint():
    return get_endpoint(WorkflowProfile.WORKFLOW1)


def workflow2_endpoint():
    return get_endpoint(WorkflowProfile.WORKFLOW2)


async def chat_completion_w2_messages(
    messages: list[dict[str, str]],
    *,
    max_tokens: int = W2_ROLE_MAX_TOKENS,
    temperature: float = W2_TEMPERATURE,
) -> str:
    return await harness_chat(
        WorkflowProfile.WORKFLOW2,
        messages,
        max_tokens=max_tokens,
        temperature=temperature,
        json_mode=False,
    )


async def chat_completion_w2_synthesis(messages: list[dict[str, str]]) -> str:
    return await chat_completion_w2_messages(
        messages,
        max_tokens=W2_SYNTHESIS_MAX_TOKENS,
    )


def chat_completion_messages(
    messages: list[dict[str, str]],
    *,
    max_tokens: int = W1_JSON_MAX_TOKENS,
    temperature: float = W1_JSON_TEMPERATURE,
) -> str:
    """Run async harness chat from sync code (gateway, tests)."""
    return asyncio.run(
        harness_chat(
            WorkflowProfile.WORKFLOW1,
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
            json_mode=True,
        )
    )


def chat_completion(
    user_content: str,
    *,
    system_prompt: str | None = None,
    model: str | None = None,  # noqa: ARG001 — model comes from harness settings
    max_tokens: int = W1_JSON_MAX_TOKENS,
    temperature: float = W1_JSON_TEMPERATURE,
    json_mode: bool = True,
) -> str:
    """Backward-compatible single user message helper."""
    system = system_prompt if system_prompt is not None else load_system_prompt()
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]
    if not json_mode:
        return asyncio.run(
            harness_chat(
                WorkflowProfile.WORKFLOW1,
                messages,
                max_tokens=max_tokens,
                temperature=temperature,
                json_mode=False,
            )
        )
    return chat_completion_messages(
        messages, max_tokens=max_tokens, temperature=temperature
    )


def llm_reachable() -> bool:
    """True when Workflow 1 Ollama endpoint responds and lists the configured model."""
    result = asyncio.run(check_profile(WorkflowProfile.WORKFLOW1))
    return result.ok


def llm_reachable_w2() -> bool:
    result = asyncio.run(check_profile(WorkflowProfile.WORKFLOW2))
    return result.ok
