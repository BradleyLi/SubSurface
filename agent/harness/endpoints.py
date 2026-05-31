"""Workflow profile → Ollama base URL and model mapping."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum

from .settings import get_settings


class WorkflowProfile(str, Enum):
    WORKFLOW1 = "workflow1"
    WORKFLOW2 = "workflow2"


@dataclass(frozen=True)
class EndpointConfig:
    base_url: str
    model: str
    api_key: str


@dataclass(frozen=True)
class ChatDefaults:
    max_tokens: int
    temperature: float


def _legacy_w1_base_url() -> str | None:
    """Support root .env OPENAI_API_BASE during migration."""
    value = os.getenv("OPENAI_API_BASE", "").strip()
    return value or None


def _legacy_w1_model() -> str | None:
    value = os.getenv("OPENAI_MODEL", "").strip()
    return value or None


def get_chat_defaults(profile: WorkflowProfile) -> ChatDefaults:
    settings = get_settings()
    if profile is WorkflowProfile.WORKFLOW1:
        return ChatDefaults(
            max_tokens=settings.workflow1_max_tokens,
            temperature=settings.workflow1_temperature,
        )
    if profile is WorkflowProfile.WORKFLOW2:
        return ChatDefaults(
            max_tokens=settings.workflow2_max_tokens,
            temperature=settings.workflow2_temperature,
        )
    raise ValueError(f"Unknown workflow profile: {profile!r}")


def get_endpoint(profile: WorkflowProfile) -> EndpointConfig:
    settings = get_settings()
    if profile is WorkflowProfile.WORKFLOW1:
        base = _legacy_w1_base_url() or settings.workflow1_openai_base_url
        model = _legacy_w1_model() or settings.workflow1_model
        return EndpointConfig(
            base_url=base.rstrip("/"),
            model=model,
            api_key=settings.openai_api_key,
        )
    if profile is WorkflowProfile.WORKFLOW2:
        return EndpointConfig(
            base_url=settings.workflow2_openai_base_url.rstrip("/"),
            model=settings.workflow2_model,
            api_key=settings.openai_api_key,
        )
    raise ValueError(f"Unknown workflow profile: {profile!r}")
