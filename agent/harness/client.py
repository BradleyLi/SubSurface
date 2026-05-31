"""Async Ollama client: native JSON chat (W1) + OpenAI-compatible fallback."""

from __future__ import annotations

import asyncio
import os
from typing import Any
from urllib.parse import urlparse
from weakref import WeakKeyDictionary

import httpx

from .endpoints import EndpointConfig, WorkflowProfile, get_chat_defaults, get_endpoint
from .settings import get_settings

_W1_TIMEOUT_SECONDS = float(os.getenv("WORKFLOW1_CHAT_TIMEOUT_SECONDS", "240"))
_W2_TIMEOUT_SECONDS = float(os.getenv("WORKFLOW2_CHAT_TIMEOUT_SECONDS", "1800"))
_DEFAULT_TIMEOUT = httpx.Timeout(_W1_TIMEOUT_SECONDS, connect=5.0)
_W2_TIMEOUT = httpx.Timeout(_W2_TIMEOUT_SECONDS, connect=5.0)
_HTTP_LIMITS = httpx.Limits(max_connections=20, max_keepalive_connections=10)
_shared_clients: WeakKeyDictionary[asyncio.AbstractEventLoop, httpx.AsyncClient] = (
    WeakKeyDictionary()
)


def _keep_alive() -> str:
    return os.getenv("OLLAMA_KEEP_ALIVE") or get_settings().ollama_keep_alive


def _num_ctx(profile: WorkflowProfile) -> int:
    settings = get_settings()
    if profile is WorkflowProfile.WORKFLOW1:
        return int(os.getenv("WORKFLOW1_NUM_CTX", str(settings.workflow1_num_ctx)))
    return int(os.getenv("WORKFLOW2_NUM_CTX", str(settings.workflow2_num_ctx)))


def _get_shared_client() -> httpx.AsyncClient:
    loop = asyncio.get_running_loop()
    client = _shared_clients.get(loop)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(timeout=_W2_TIMEOUT, limits=_HTTP_LIMITS)
        _shared_clients[loop] = client
    return client


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
    num_ctx: int,
) -> str:
    host = _native_host(cfg.base_url)
    payload = {
        "model": cfg.model,
        "messages": messages,
        "stream": False,
        "format": "json",
        "keep_alive": _keep_alive(),
        "think": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
            "num_ctx": num_ctx,
        },
    }
    client = _get_shared_client()
    response = await client.post(f"{host}/api/chat", json=payload, timeout=timeout)
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
    num_ctx: int,
) -> str:
    url = f"{cfg.base_url.rstrip('/')}/chat/completions"
    payload: dict[str, Any] = {
        "model": cfg.model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
        "keep_alive": _keep_alive(),
        # Disable Nemotron reasoning for the Multi-Role Analysis (Workflow 2).
        # Ollama's OpenAI-compatible endpoint ignores the native `think` flag;
        # `reasoning_effort: "none"` is the documented way to turn thinking off.
        "reasoning_effort": "none",
        "options": {"num_ctx": num_ctx},
    }
    headers = {"Authorization": f"Bearer {cfg.api_key}"}

    client = _get_shared_client()
    response = await client.post(url, json=payload, headers=headers, timeout=timeout)
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
    num_ctx = _num_ctx(profile)

    if json_mode:
        text = await _chat_native_json(
            cfg,
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=request_timeout,
            num_ctx=num_ctx,
        )
        if text:
            return text

    return await _chat_openai_compatible(
        cfg,
        messages,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=request_timeout,
        num_ctx=num_ctx,
    )
