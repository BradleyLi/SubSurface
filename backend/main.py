"""
FastAPI backend for CityNerve SubSurface.
Serves pipe/network data and AI responses for the Streamlit frontend.
"""

from __future__ import annotations

import json
from typing import Literal

import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agent.gateway import workflow1_summary
from agent.harness.endpoints import WorkflowProfile
from agent.harness.health import check_all, check_profile
from agent.schemas import AnalysisRunRequest
from agent.w2_gateway import workflow2_run
from agent.w2_storage import load_file, load_manifest
from data_utils import get_ai_response, get_distribution_watermains, get_pipes_uncached
from real_data import get_real_pipes


app = FastAPI(title="CityNerve API", version="1.0.0")


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


@app.post("/api/analysis-runs")
async def api_create_analysis_run(body: AnalysisRunRequest) -> dict:
    """Workflow 2: four-role analysis + synthesis (Nemotron Super)."""
    try:
        result = await workflow2_run(
            body.pipe_id,
            use_real=body.use_real,
            use_latest_voice_transcript=body.use_latest_voice_transcript,
            transcript_path=body.transcript_path,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
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
