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

from data_utils import get_ai_response, get_distribution_watermains, get_pipes
from real_data import get_real_pipes


app = FastAPI(title="CityNerve API", version="1.0.0")


def _to_records(df: pd.DataFrame) -> list[dict]:
    """Convert DataFrame to JSON-serializable records."""
    if df.empty:
        return []
    return json.loads(df.to_json(orient="records"))


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/pipes")
def api_pipes(use_real: bool = False) -> dict:
    try:
        df = get_pipes(use_real=use_real)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load pipes: {exc}") from exc
    return {
        "count": int(len(df)),
        "records": _to_records(df),
        "source": "real" if use_real else "synthetic",
    }


@app.get("/api/watermains-layer")
def api_watermains_layer(
    layer_mode: Literal["Distribution", "Transmission", "Both", "Synthetic"] = "Distribution",
    use_real: bool = True,
    max_features: int | None = None,
) -> dict:
    try:
        if not use_real or layer_mode == "Synthetic":
            df = get_pipes(use_real=False)
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
    use_real: bool = False
    focus_ward: str | None = None
    focus_material: str | None = None


@app.post("/api/ai-response")
def api_ai_response(body: AIRequest) -> dict:
    try:
        df = get_pipes(use_real=body.use_real)

        if body.focus_ward and body.focus_ward != "All Wards":
            df = df[df["ward"] == body.focus_ward]
        if body.focus_material and body.focus_material != "All Materials":
            df = df[df["material"] == body.focus_material]
        if df.empty:
            df = get_pipes(use_real=body.use_real)

        reply = get_ai_response(body.query, df)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to generate AI response: {exc}") from exc

    return {"response": reply, "context_count": int(len(df))}
