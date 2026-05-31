"""Async Ollama client: native JSON chat (W1) + OpenAI-compatible fallback."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from .endpoints import EndpointConfig, WorkflowProfile, get_chat_defaults, get_endpoint

_DEFAULT_TIMEOUT = httpx.Timeout(120.0, connect=5.0)
_W2_TIMEOUT = httpx.Timeout(600.0, connect=5.0)


def _native_host(base_url: str) -> str:
    """Ollama root URL from an OpenAI-compatible base (…/v1)."""
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        return base[: -len("/v1")]
    parsed = urlparse(base)
    return f"{parsed.scheme}://{parsed.netloc}"


async def _chat_native_json(
    cfg: EndpointConfig,
    messages: list[dict[str, str]],
    *,
    max_tokens: int,
    temperature: float,
    timeout: httpx.Timeout,
) -> str:
    host = _native_host(cfg.base_url)
    payload = {
        "model": cfg.model,
        "messages": messages,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(f"{host}/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()
    return str((data.get("message") or {}).get("content") or "").strip()


async def _chat_openai_compatible(
    cfg: EndpointConfig,
    messages: list[dict[str, str]],
    *,
    max_tokens: int,
    temperature: float,
    timeout: httpx.Timeout,
) -> str:
    url = f"{cfg.base_url.rstrip('/')}/chat/completions"
    payload: dict[str, Any] = {
        "model": cfg.model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {cfg.api_key}"}

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"No choices in Ollama response from {url}")
    message = choices[0].get("message") or {}
    content = message.get("content")
    text = str(content).strip() if content is not None else ""
    if not text:
        reasoning = message.get("reasoning") or ""
        if isinstance(reasoning, str) and reasoning.strip():
            text = reasoning.strip()
    if not text:
        raise RuntimeError(f"Missing message content in Ollama response from {url}")
    return text


async def chat(
    profile: WorkflowProfile,
    messages: list[dict[str, str]],
    *,
    max_tokens: int | None = None,
    temperature: float | None = None,
    endpoint: EndpointConfig | None = None,
    timeout: httpx.Timeout | None = None,
    json_mode: bool = False,
) -> str:
    """
    Call Nemotron on the profile's Ollama instance.

    When json_mode is True (Workflow 1 structured summaries), prefer native
    Ollama /api/chat with format=json, then fall back to OpenAI-compatible API.
    """
    defaults = get_chat_defaults(profile)
    max_tokens = defaults.max_tokens if max_tokens is None else max_tokens
    temperature = defaults.temperature if temperature is None else temperature
    cfg = endpoint or get_endpoint(profile)
    request_timeout = timeout or (
        _W2_TIMEOUT if profile is WorkflowProfile.WORKFLOW2 else _DEFAULT_TIMEOUT
    )

    if json_mode:
        text = await _chat_native_json(
            cfg,
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=request_timeout,
        )
        if text:
            return text

    return await _chat_openai_compatible(
        cfg,
        messages,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=request_timeout,
    )
