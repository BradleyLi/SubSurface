"""Reachability checks for dual Ollama workflow profiles."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from .endpoints import WorkflowProfile, get_endpoint
from .settings import get_settings

_CHECK_TIMEOUT = httpx.Timeout(10.0, connect=3.0)


@dataclass
class ProfileHealth:
    profile: WorkflowProfile
    base_url: str
    model: str
    ok: bool
    detail: str
    models_available: list[str] | None = None


async def check_profile(profile: WorkflowProfile) -> ProfileHealth:
    cfg = get_endpoint(profile)
    tags_url = f"{cfg.base_url}/models"
    try:
        async with httpx.AsyncClient(timeout=_CHECK_TIMEOUT) as client:
            response = await client.get(
                tags_url,
                headers={"Authorization": f"Bearer {cfg.api_key}"},
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, OSError) as exc:
        return ProfileHealth(
            profile=profile,
            base_url=cfg.base_url,
            model=cfg.model,
            ok=False,
            detail=str(exc),
        )

    models = [item.get("id", "") for item in payload.get("data", []) if item.get("id")]
    model_ok = cfg.model in models or any(cfg.model.split(":")[0] in m for m in models)
    detail = "ok" if model_ok else f"model {cfg.model!r} not listed (available: {models or 'none'})"
    return ProfileHealth(
        profile=profile,
        base_url=cfg.base_url,
        model=cfg.model,
        ok=model_ok,
        detail=detail,
        models_available=models or None,
    )


async def check_all() -> list[ProfileHealth]:
    return [
        await check_profile(WorkflowProfile.WORKFLOW1),
        await check_profile(WorkflowProfile.WORKFLOW2),
    ]


def nemoclaw_sandbox_names() -> tuple[str, str]:
    settings = get_settings()
    return settings.nemoclaw_w1_sandbox, settings.nemoclaw_w2_sandbox
