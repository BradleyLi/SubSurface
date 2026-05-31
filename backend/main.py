"""
FastAPI backend for CityNerve SubSurface.
Serves pipe/network data and AI workflows for the React UI (SubSurface-UI).
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
import json
import logging
import os
from dataclasses import asdict
from typing import Any, Literal

import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


def _configure_logging() -> None:
    """Emit application (agent.*) INFO logs under uvicorn.

    Uvicorn only configures its own loggers, leaving the root logger at
    WARNING with no handler, so progress logs from agent.w2_gateway etc. are
    dropped. Honor CITYNERVE_LOG_LEVEL (set by scripts/run_citynerve.sh) so the
    Workflow 2 multi-role analysis logs are visible in the server output.
    """
    level_name = os.getenv("CITYNERVE_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    logging.getLogger("agent").setLevel(level)


_configure_logging()

from agent.gateway import workflow1_summary
from agent.harness.endpoints import WorkflowProfile
from agent.harness.health import check_all, check_profile
from agent.schemas import AnalysisRunRequest
from agent.voice_context import load_voice_transcript
from agent.voice_pipe_match import find_pipe_for_latest_transcript
from agent.w2_gateway import workflow2_run
from agent.w2_storage import load_file, load_latest_run_for_pipe, load_manifest
from data_utils import get_ai_response, get_distribution_watermains, get_pipes_uncached
from real_data import get_real_pipes


app = FastAPI(title="CityNerve API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _to_records(df: pd.DataFrame) -> list[dict]:
    """Convert DataFrame to JSON-serializable records."""
    if df.empty:
        return []
    return json.loads(df.to_json(orient="records"))


@app.get("/health")
async def health() -> dict:
    profiles = await check_all()
    w1 = next(p for p in profiles if p.profile is WorkflowProfile.WORKFLOW1)
    return {
        "status": "ok" if w1.ok else "degraded",
        "llm_reachable": w1.ok,
        "workflows": [
            {
                "profile": p.profile.value,
                "ok": p.ok,
                "model": p.model,
                "base_url": p.base_url,
                "detail": p.detail,
            }
            for p in profiles
        ],
    }


@app.get("/health/workflow1")
async def health_workflow1() -> dict:
    p = await check_profile(WorkflowProfile.WORKFLOW1)
    return {
        "profile": p.profile.value,
        "ok": p.ok,
        "model": p.model,
        "base_url": p.base_url,
        "detail": p.detail,
        "models_available": p.models_available,
    }


@app.get("/health/workflow2")
async def health_workflow2() -> dict:
    p = await check_profile(WorkflowProfile.WORKFLOW2)
    return {
        "profile": p.profile.value,
        "ok": p.ok,
        "model": p.model,
        "base_url": p.base_url,
        "detail": p.detail,
        "models_available": p.models_available,
    }


@app.get("/api/pipes")
def api_pipes(use_real: bool = True) -> dict:
    try:
        df = get_pipes_uncached(use_real=use_real)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load pipes: {exc}") from exc
    return {
        "count": int(len(df)),
        "records": _to_records(df),
        "source": _pipe_data_source(df, use_real),
    }


@app.get("/api/watermains-layer")
def api_watermains_layer(
    layer_mode: Literal["Distribution", "Transmission", "Both", "Synthetic"] = "Distribution",
    use_real: bool = True,
    max_features: int | None = None,
) -> dict:
    try:
        if not use_real or layer_mode == "Synthetic":
            df = get_pipes_uncached(use_real=True)
            df = df[df["pipe_type"] == "Synthetic"].copy()
            source = "synthetic"
        elif layer_mode == "Distribution":
            df = get_distribution_watermains(max_features=max_features)
            source = "real_distribution"
        else:
            real_df = get_real_pipes(max_dist=max_features)
            if layer_mode == "Transmission":
                df = real_df[real_df["pipe_type"] == "Transmission"].copy()
                source = "real_transmission"
            else:
                df = real_df[real_df["pipe_type"].isin(["Distribution", "Transmission"])].copy()
                source = "real_both"
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load layer: {exc}") from exc

    return {"count": int(len(df)), "records": _to_records(df), "source": source}


class AIRequest(BaseModel):
    query: str
    use_real: bool = True
    focus_ward: str | None = None
    focus_material: str | None = None


def _pipe_data_source(df: pd.DataFrame, use_real: bool) -> str:
    if not use_real:
        return "synthetic"
    if "data_source" in df.columns and len(df):
        value = df["data_source"].iloc[0]
        if value == "ml_enriched":
            return "ml_enriched"
    if "predicted_break_probability" in df.columns and df["predicted_break_probability"].notna().any():
        return "ml_enriched"
    return "real"


@app.get("/api/pipes/{pipe_id}/risk-summary")
def api_pipe_risk_summary(pipe_id: str, use_real: bool = True) -> dict:
    """Workflow 1: Nemotron JSON risk summary for a single pipe."""
    try:
        result = workflow1_summary(pipe_id, use_real=use_real)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate risk summary: {exc}",
        ) from exc
    return result.model_dump()


def _demo_cache_enabled() -> bool:
    return os.getenv("W2_DEMO_CACHE", "true").lower() in ("1", "true", "yes")


def _demo_cache_delay() -> float:
    try:
        return float(os.getenv("W2_DEMO_CACHE_DELAY", "60"))
    except ValueError:
        return 60.0


async def _sleep_with_disconnect(seconds: float, request: Request, pipe_id: str) -> None:
    """Sleep up to `seconds`, aborting early if the client disconnects."""
    deadline = asyncio.get_event_loop().time() + seconds
    while asyncio.get_event_loop().time() < deadline:
        if await request.is_disconnected():
            logging.getLogger("agent.w2_gateway").info(
                "Workflow 2 client disconnected during demo cache replay for pipe %s",
                pipe_id,
            )
            raise asyncio.CancelledError
        await asyncio.sleep(0.5)


@app.post("/api/analysis-runs")
async def api_create_analysis_run(body: AnalysisRunRequest, request: Request) -> dict:
    """Workflow 2: four-role analysis + synthesis (Nemotron Super)."""
    if _demo_cache_enabled():
        cached = load_latest_run_for_pipe(body.pipe_id)
        if cached is not None:
            delay = _demo_cache_delay()
            logging.getLogger("agent.w2_gateway").info(
                "Workflow 2 demo cache hit for pipe %s (run_id=%s); "
                "replaying after %.0fs",
                body.pipe_id,
                cached.get("run_id"),
                delay,
            )
            try:
                await _sleep_with_disconnect(delay, request, body.pipe_id)
            except asyncio.CancelledError:
                raise
            return cached

    task = asyncio.create_task(
        workflow2_run(
            body.pipe_id,
            use_real=body.use_real,
            use_latest_voice_transcript=body.use_latest_voice_transcript,
            transcript_path=body.transcript_path,
        )
    )
    try:
        while not task.done():
            if await request.is_disconnected():
                logging.getLogger("agent.w2_gateway").info(
                    "Workflow 2 client disconnected; cancelling pipe %s",
                    body.pipe_id,
                )
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
                raise asyncio.CancelledError
            await asyncio.sleep(0.5)
        result = await task
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logging.getLogger("agent.w2_gateway").exception(
            "Workflow 2 failed for pipe %s",
            body.pipe_id,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to run multi-role analysis: {exc}",
        ) from exc
    return result.model_dump()


@app.get("/api/analysis-runs/{run_id}")
def api_get_analysis_run(run_id: str) -> dict:
    manifest = load_manifest(run_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Analysis run not found: {run_id}")
    return manifest


@app.get("/api/analysis-runs/{run_id}/files/{filename}")
def api_get_analysis_run_file(run_id: str, filename: str) -> dict:
    allowed = {
        "engineer.md",
        "police.md",
        "field_investigation.md",
        "operations.md",
        "final_summary.md",
        "action_plan.json",
        "bill_of_materials.json",
        "manifest.json",
    }
    if filename not in allowed:
        raise HTTPException(status_code=400, detail=f"Unknown file: {filename}")
    content = load_file(run_id, filename)
    if content is None:
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")
    return {"run_id": run_id, "filename": filename, "content": content}


@app.post("/api/ai-response")
def api_ai_response(body: AIRequest) -> dict:
    try:
        df = get_pipes_uncached(use_real=body.use_real)

        if body.focus_ward and body.focus_ward != "All Wards":
            df = df[df["ward"] == body.focus_ward]
        if body.focus_material and body.focus_material != "All Materials":
            df = df[df["material"] == body.focus_material]
        if df.empty:
            df = get_pipes_uncached(use_real=body.use_real)

        reply = get_ai_response(body.query, df)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to generate AI response: {exc}") from exc

    return {"response": reply, "context_count": int(len(df))}


def _json_safe(value: Any) -> Any:
    """Convert dataclasses and other objects to JSON-serializable values."""
    if value is None:
        return None
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    return value


@app.get("/api/voice/transcript/latest")
def api_voice_transcript_latest(transcript_path: str | None = None) -> dict:
    """Return the latest (or explicit) voice call transcript JSON."""
    payload = load_voice_transcript(transcript_path)
    if payload is None:
        return {"payload": None}
    return {"payload": payload}


@app.get("/api/voice/match/latest")
def api_voice_match_latest(
    use_real: bool = True,
    transcript_path: str | None = None,
) -> dict:
    """Match the latest voice transcript to a pipe in the network."""
    try:
        df = get_pipes_uncached(use_real=use_real)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load pipes for voice match: {exc}",
        ) from exc

    payload, match = find_pipe_for_latest_transcript(
        df,
        transcript_path=transcript_path,
    )
    return {
        "payload": payload,
        "match": _json_safe(match),
    }
