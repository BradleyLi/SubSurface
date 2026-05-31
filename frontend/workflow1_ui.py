"""
Workflow 1 (Nemotron) summary cards for Streamlit — shared by Overview and reports.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import pandas as pd
import streamlit as st

from agent.evidence import build_evidence_from_row
from agent.template_summary import template_summary
from api_client import get_risk_summary_api
from frontend.nav import w1_session_key

# Parallel W1 HTTP calls (Ollama :11436 may queue; 2 is a safe default on one GPU).
W1_PARALLEL_MAX = max(1, min(4, int(os.environ.get("W1_PARALLEL_MAX", "2"))))


def _rerun_scoped(*, fragment: bool) -> None:
    """
    Rerun execution. When called from @st.fragment, plain st.rerun() reruns
    only that fragment (do not pass scope= — invalid on first fragment pass).
    """
    st.rerun()


def _fetch_w1_payload(pipe_id: str, use_real: bool) -> dict[str, Any]:
    try:
        payload = get_risk_summary_api(pipe_id, use_real=use_real)
        return {"use_real": use_real, **payload}
    except Exception as exc:
        return {
            "use_real": use_real,
            "error": str(exc),
            "summary": {},
            "source": "error",
        }


def ensure_w1_summaries(
    pipe_ids: list[str],
    *,
    use_real: bool,
    session_state: dict[str, Any] | None = None,
    show_spinner: bool = False,
) -> list[str]:
    """
    Fetch and cache W1 payloads for pipes missing cache or stale use_real flag.
    Returns pipe_ids that were fetched this call.

    Default: no spinner — Why Failing cards already show a loading badge on preview.
    """
    if not pipe_ids:
        return []

    state = session_state if session_state is not None else st.session_state
    to_fetch: list[str] = []
    for pid in pipe_ids:
        key = w1_session_key(pid)
        cached = state.get(key)
        if not cached or cached.get("use_real") != use_real:
            to_fetch.append(pid)

    if not to_fetch:
        return []

    workers = min(W1_PARALLEL_MAX, len(to_fetch))

    def _run_fetch() -> None:
        if workers <= 1:
            for pid in to_fetch:
                state[w1_session_key(pid)] = _fetch_w1_payload(pid, use_real)
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(_fetch_w1_payload, pid, use_real): pid for pid in to_fetch
                }
                for fut in as_completed(futures):
                    pid = futures[fut]
                    state[w1_session_key(pid)] = fut.result()

    if show_spinner:
        with st.spinner("Generating capital works order report…"):
            _run_fetch()
    else:
        _run_fetch()

    return to_fetch


def _template_payload(row: pd.Series, df: pd.DataFrame | None) -> dict[str, Any]:
    evidence = build_evidence_from_row(row, df=df)
    summary = template_summary(evidence)
    return {
        "summary": summary.model_dump(),
        "source": "template",
        "pending_nemotron": True,
    }


def format_w1_card_html(
    pipe_id: str,
    risk_level: str,
    level_color: str,
    payload: dict[str, Any],
) -> str:
    """HTML for one Why Failing / W1 card."""
    if payload.get("error"):
        return f"""
        <div class="cn-card" style="margin-bottom:.5rem;border-left:3px solid {level_color}">
            <div class="cn-card-title">{pipe_id} · {risk_level}</div>
            <div style="font-size:.78rem;color:#ff7043">{payload["error"]}</div>
        </div>
        """

    summary = payload.get("summary") or {}
    source = payload.get("source", "unknown")
    pending = payload.get("pending_nemotron", False)
    if pending:
        badge = (
            '<span style="font-size:.62rem;color:#4fc3f7;font-weight:600">'
            "● Preview · Nemotron loading…</span>"
        )
    elif source == "nemotron":
        badge = (
            '<span style="font-size:.62rem;color:#1de9b6;font-weight:600">● Nemotron W1</span>'
        )
    else:
        badge = (
            '<span style="font-size:.62rem;color:#ffa726;font-weight:600">● Template</span>'
        )
    reasons = summary.get("top_reasons") or []
    reasons_html = "".join(f"<li>{r}</li>" for r in reasons[:5])
    caveats = summary.get("caveats") or []
    caveats_html = (
        f'<p style="color:#5a7a9a;font-size:.68rem;margin:.5rem 0 0;font-style:italic">'
        f'{" · ".join(caveats[:2])}</p>'
        if caveats
        else ""
    )

    return f"""
    <div class="cn-card" style="margin-bottom:.5rem;border-left:3px solid {level_color}">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.35rem">
            <div class="cn-card-title" style="margin:0">{pipe_id} · {risk_level}</div>
            {badge}
        </div>
        <div style="font-size:.82rem;font-weight:600;color:#c9d8ea;margin-bottom:.25rem">
            {summary.get("headline", "")}</div>
        <div style="font-size:.78rem;line-height:1.45;color:#c9d8ea">
            {summary.get("risk_sentence", "")}</div>
        <ul style="color:#8faabf;font-size:.75rem;margin:.4rem 0;padding-left:1.1rem">
            {reasons_html}
        </ul>
        <div style="font-size:.76rem;color:#ffa726;margin-top:.35rem">
            <strong>Next:</strong> {summary.get("recommended_next_step", "")}</div>
        {caveats_html}
    </div>
    """


def render_w1_agent_cards(
    rows: pd.DataFrame,
    *,
    use_real: bool,
    df: pd.DataFrame | None = None,
    session_state: dict[str, Any] | None = None,
    max_cards: int = 4,
    fragment_rerun: bool = False,
) -> None:
    """
    Render Workflow 1 cards. Shows instant template preview, then Nemotron when ready.
    """
    if rows.empty:
        return

    state = session_state if session_state is not None else st.session_state
    subset = rows.head(max_cards)
    pipe_ids = [str(p) for p in subset["pipe_id"].tolist()]

    need_nemotron: list[str] = []
    for pid in pipe_ids:
        cached = state.get(w1_session_key(pid))
        if (
            cached
            and cached.get("use_real") == use_real
            and cached.get("source") == "nemotron"
            and not cached.get("error")
        ):
            continue
        need_nemotron.append(pid)

    def _render_cards() -> None:
        for _, r in subset.iterrows():
            pid = str(r["pipe_id"])
            lvl = str(r["risk_level"])
            color = (
                "#ff3d3d" if lvl == "Critical" else "#ffa726" if lvl == "High" else "#8faabf"
            )
            cached = state.get(w1_session_key(pid))
            if (
                cached
                and cached.get("use_real") == use_real
                and cached.get("source") == "nemotron"
                and not cached.get("error")
            ):
                payload = cached
            elif pid in need_nemotron:
                payload = _template_payload(r, df)
            elif cached and cached.get("use_real") == use_real and not cached.get("error"):
                payload = cached
            else:
                payload = _template_payload(r, df)
            st.markdown(
                format_w1_card_html(pid, lvl, color, payload),
                unsafe_allow_html=True,
            )

    if not need_nemotron:
        state.pop("_w1_pending_fetch", None)
        _render_cards()
        return

    pending_token = (tuple(sorted(need_nemotron)), use_real)
    is_fetch_pass = state.get("_w1_pending_fetch") == pending_token

    # Pass 1: preview cards immediately, then rerun (no Nemotron call yet).
    if not is_fetch_pass:
        _render_cards()
        state["_w1_pending_fetch"] = pending_token
        _rerun_scoped(fragment=fragment_rerun)
        return

    # Pass 2: keep preview cards visible, spinner while Nemotron runs.
    _render_cards()
    n_load = len(need_nemotron)
    spin_label = (
        f"Loading Nemotron summary for {need_nemotron[0]}…"
        if n_load == 1
        else f"Loading Nemotron summaries for {n_load} pipes…"
    )
    with st.spinner(spin_label + " (~20–50s per pipe on GX10)"):
        ensure_w1_summaries(
            need_nemotron,
            use_real=use_real,
            session_state=state,
            show_spinner=False,
        )

    state.pop("_w1_pending_fetch", None)
    _rerun_scoped(fragment=fragment_rerun)


@st.fragment
def render_pipe_summaries_panel(
    rows: pd.DataFrame,
    *,
    use_real: bool,
    df: pd.DataFrame | None = None,
    max_cards: int = 4,
) -> None:
    """Right-column Workflow 1 pipe summaries (isolated reruns)."""
    if rows.empty:
        st.markdown(
            """
            <div class="cn-card" style="border-style:dashed">
                <div style="font-size:.8rem;color:#8faabf;line-height:1.5">
                    Select pipes in the queue to load per-pipe summaries here.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    render_w1_agent_cards(
        rows,
        use_real=use_real,
        df=df,
        max_cards=max_cards,
        fragment_rerun=True,
    )
    if len(rows) > max_cards:
        st.caption(f"Showing first {max_cards} of {len(rows)} selected pipes.")
