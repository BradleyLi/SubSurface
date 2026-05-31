"""
Frontend API client for CityNerve Streamlit pages.
Prefers FastAPI backend and falls back to local data_utils when needed.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

import pandas as pd
import streamlit as st

from agent.gateway import workflow1_summary as _local_workflow1_summary
from agent.w2_gateway import workflow2_run_sync as _local_workflow2_run
from data_utils import get_ai_response as _local_ai_response
from data_utils import get_distribution_watermains as _local_distribution
from data_utils import get_pipes as _local_get_pipes
from real_data import get_real_pipes as _local_get_real_pipes


API_BASE_URL = os.getenv("CITYNERVE_API_URL", "http://127.0.0.1:8000").rstrip("/")


def _warn_once(msg: str, key: str) -> None:
    state_key = f"_api_warned_{key}"
    if not st.session_state.get(state_key, False):
        st.session_state[state_key] = True
        st.warning(msg)


def _request_json(path: str, query: dict | None = None, payload: dict | None = None, timeout: int = 120) -> dict:
    url = f"{API_BASE_URL}{path}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"

    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=headers, method="POST" if payload else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _records_to_df(records: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(records)


@st.cache_data(show_spinner=False)
def get_pipes_api(use_real: bool = False) -> pd.DataFrame:
    try:
        data = _request_json("/api/pipes", query={"use_real": str(use_real).lower()})
        return _records_to_df(data["records"])
    except Exception:
        _warn_once(
            f"Backend unavailable at {API_BASE_URL}. Falling back to in-process data loading.",
            key="pipes",
        )
        return _local_get_pipes(use_real=use_real)


@st.cache_data(show_spinner=False)
def get_watermains_layer_api(
    use_real: bool = True,
    layer_mode: str = "Distribution",
    max_features: int | None = None,
) -> pd.DataFrame:
    try:
        query = {
            "use_real": str(use_real).lower(),
            "layer_mode": layer_mode,
        }
        if max_features is not None:
            query["max_features"] = str(max_features)
        data = _request_json("/api/watermains-layer", query=query, timeout=240)
        return _records_to_df(data["records"])
    except Exception:
        _warn_once(
            f"Backend unavailable at {API_BASE_URL}. Falling back to in-process data loading.",
            key="watermains",
        )
        if not use_real or layer_mode == "Synthetic":
            fallback = _local_get_pipes(use_real=False)
            return fallback[fallback["pipe_type"] == "Synthetic"].copy()
        if layer_mode == "Distribution":
            return _local_distribution(max_features=max_features)
        all_real = _local_get_real_pipes(max_dist=max_features)
        if layer_mode == "Transmission":
            return all_real[all_real["pipe_type"] == "Transmission"].copy()
        return all_real[all_real["pipe_type"].isin(["Distribution", "Transmission"])].copy()


def get_workflow2_health_api() -> dict:
    try:
        return _request_json("/health/workflow2", timeout=15)
    except Exception:
        return {"ok": False, "detail": "backend unavailable"}


def post_analysis_run_api(pipe_id: str, use_real: bool = False) -> dict:
    """Workflow 2 multi-role analysis (may take several minutes)."""
    try:
        return _request_json(
            "/api/analysis-runs",
            payload={"pipe_id": pipe_id, "use_real": use_real},
            timeout=900,
        )
    except Exception:
        _warn_once(
            f"Backend unavailable at {API_BASE_URL}. Running Workflow 2 in-process.",
            key="analysis_run",
        )
        result = _local_workflow2_run(pipe_id, use_real=use_real)
        return result.model_dump()


def get_analysis_run_api(run_id: str) -> dict:
    return _request_json(
        f"/api/analysis-runs/{urllib.parse.quote(run_id, safe='')}",
        timeout=30,
    )


def get_risk_summary_api(pipe_id: str, use_real: bool = False) -> dict:
    """Workflow 1 Nemotron risk summary for one pipe."""
    try:
        return _request_json(
            f"/api/pipes/{urllib.parse.quote(pipe_id, safe='')}/risk-summary",
            query={"use_real": str(use_real).lower()},
            timeout=180,
        )
    except Exception:
        _warn_once(
            f"Backend unavailable at {API_BASE_URL}. Using in-process Nemotron gateway.",
            key="risk_summary",
        )
        result = _local_workflow1_summary(pipe_id, use_real=use_real)
        return result.model_dump()


def get_ai_response_api(
    query: str,
    use_real: bool = False,
    focus_ward: str | None = None,
    focus_material: str | None = None,
) -> str:
    try:
        payload = {
            "query": query,
            "use_real": use_real,
            "focus_ward": focus_ward,
            "focus_material": focus_material,
        }
        data = _request_json("/api/ai-response", payload=payload)
        return str(data["response"])
    except Exception:
        _warn_once(
            f"Backend unavailable at {API_BASE_URL}. Falling back to local AI response mode.",
            key="ai",
        )
        df = _local_get_pipes(use_real=use_real)
        if focus_ward and focus_ward != "All Wards":
            df = df[df["ward"] == focus_ward]
        if focus_material and focus_material != "All Materials":
            df = df[df["material"] == focus_material]
        if df.empty:
            df = _local_get_pipes(use_real=use_real)
        return _local_ai_response(query, df)
