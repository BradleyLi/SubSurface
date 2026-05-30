"""Thin async Ollama chat client (OpenAI-compatible /v1/chat/completions)."""

from __future__ import annotations

from typing import Any

import httpx

from .endpoints import EndpointConfig, WorkflowProfile, get_chat_defaults, get_endpoint

_DEFAULT_TIMEOUT = httpx.Timeout(120.0, connect=5.0)
_W2_TIMEOUT = httpx.Timeout(600.0, connect=5.0)


async def chat(
    profile: WorkflowProfile,
    messages: list[dict[str, str]],
    *,
    max_tokens: int | None = None,
    temperature: float | None = None,
    endpoint: EndpointConfig | None = None,
    timeout: httpx.Timeout | None = None,
) -> str:
    defaults = get_chat_defaults(profile)
    max_tokens = defaults.max_tokens if max_tokens is None else max_tokens
    temperature = defaults.temperature if temperature is None else temperature
    cfg = endpoint or get_endpoint(profile)
    url = f"{cfg.base_url}/chat/completions"
    payload: dict[str, Any] = {
        "model": cfg.model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {cfg.api_key}"}
    request_timeout = timeout or (
        _W2_TIMEOUT if profile is WorkflowProfile.WORKFLOW2 else _DEFAULT_TIMEOUT
    )

    async with httpx.AsyncClient(timeout=request_timeout) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"No choices in Ollama response from {url}")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if content is None:
        raise RuntimeError(f"Missing message content in Ollama response from {url}")
    return str(content)
