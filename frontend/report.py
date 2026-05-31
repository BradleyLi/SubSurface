"""
Capital works order report — uses Nemotron W1 summaries and optional W2 runs.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from api_client import get_risk_summary_api
from model import failure_summary
from frontend.nav import w1_session_key, w2_session_key
from frontend.workflow1_ui import ensure_w1_summaries

# Max pipes to call Nemotron W1 for (avoid multi-minute reports).
MAX_NEMOTRON_PIPES = 5


def _w1_summary_line(
    pipe_id: str,
    use_real: bool,
    session_state: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Return (pipe_id, text line) from Nemotron W1 or template fallback."""
    try:
        payload: dict[str, Any] | None = None
        if session_state is not None:
            cached = session_state.get(w1_session_key(pipe_id))
            if cached and cached.get("use_real") == use_real and not cached.get("error"):
                payload = cached
        if payload is None:
            payload = get_risk_summary_api(pipe_id, use_real=use_real)
        s = payload.get("summary", {})
        source = payload.get("source", "unknown")
        headline = s.get("headline", "")
        risk_sentence = s.get("risk_sentence", "")
        step = s.get("recommended_next_step", "")
        line = f"{headline} {risk_sentence} Next: {step}".strip()
        tag = "Nemotron W1" if source == "nemotron" else "template"
        return pipe_id, f"[{tag}] {line}"
    except Exception as exc:
        return pipe_id, f"[error] {failure_summary_line_from_row_id(pipe_id, use_real)} ({exc})"


def failure_summary_line_from_row_id(pipe_id: str, use_real: bool) -> str:
    from data_utils import get_pipes

    df = get_pipes(use_real=use_real)
    row = df[df["pipe_id"] == pipe_id]
    if row.empty:
        return f"{pipe_id}: (not found)"
    return failure_summary(row.iloc[0])


def build_order_report_view_model(
    sel_data: pd.DataFrame,
    *,
    budget: int,
    use_real: bool = False,
    session_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Structured report for UI + plain-text download."""
    n_sel = len(sel_data)
    sel_cost = int(sel_data["replacement_cost"].sum())
    sel_savings = int(sel_data["expected_savings"].sum())
    sel_props = int(sel_data["properties_affected"].sum())
    roi_pct = (sel_savings / max(sel_cost, 1)) * 100

    top_ids = [str(p) for p in sel_data.head(MAX_NEMOTRON_PIPES)["pipe_id"].tolist()]
    if top_ids:
        ensure_w1_summaries(
            top_ids, use_real=use_real, session_state=session_state, show_spinner=False
        )

    queue_table = sel_data[
        [
            "pipe_id",
            "risk_score",
            "risk_level",
            "ward",
            "material",
            "replacement_cost",
            "expected_savings",
        ]
    ].copy()
    queue_table.insert(0, "#", range(1, len(queue_table) + 1))
    queue_table.columns = [
        "#",
        "Pipe ID",
        "Risk %",
        "Level",
        "Ward",
        "Material",
        "Replace $",
        "Savings $",
    ]

    w1_sections: list[dict[str, Any]] = []
    for _, r in sel_data.head(MAX_NEMOTRON_PIPES).iterrows():
        pid = str(r["pipe_id"])
        payload: dict[str, Any] | None = None
        if session_state is not None:
            cached = session_state.get(w1_session_key(pid))
            if cached and cached.get("use_real") == use_real and not cached.get("error"):
                payload = cached
        if payload is None:
            try:
                payload = get_risk_summary_api(pid, use_real=use_real)
            except Exception:
                payload = {"summary": {}, "source": "error"}
        s = payload.get("summary") or {}
        w1_sections.append(
            {
                "pipe_id": pid,
                "source": payload.get("source", "unknown"),
                "headline": s.get("headline", ""),
                "risk_sentence": s.get("risk_sentence", ""),
                "top_reasons": s.get("top_reasons", []),
                "recommended_next_step": s.get("recommended_next_step", ""),
            }
        )

    w2_sections: list[dict[str, Any]] = []
    if session_state is not None:
        for pid in sel_data["pipe_id"].astype(str):
            run = session_state.get(w2_session_key(pid))
            if not run:
                continue
            plan = run.get("action_plan", {})
            actions = plan.get("recommended_actions", [])
            w2_sections.append(
                {
                    "pipe_id": pid,
                    "run_id": run.get("run_id", w2_session_key(pid)),
                    "actions": [
                        f"{a.get('action', '')} ({a.get('owner', '')})" for a in actions[:5]
                    ],
                    "excerpt": (run.get("final_markdown") or "")[:400],
                }
            )

    schedule: list[dict[str, str]] = []
    ward_groups = sel_data.groupby("ward")["pipe_id"].apply(list)
    for q_idx, (ward, pipes) in enumerate(ward_groups.items(), 1):
        pipe_list = ", ".join(pipes[:4])
        if len(pipes) > 4:
            pipe_list += f" (+{len(pipes) - 4} more)"
        schedule.append(
            {"label": f"Q{min(q_idx, 4)}", "pipes": pipe_list, "ward": str(ward)}
        )

    plain_text = build_capital_works_report(
        sel_data,
        budget=budget,
        use_real=use_real,
        session_state=session_state,
        skip_w1_prefetch=True,
    )

    return {
        "meta": {
            "generated_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
            "budget": budget,
            "n_sel": n_sel,
            "roi_pct": roi_pct,
            "sel_props": sel_props,
        },
        "queue_table": queue_table,
        "w1_sections": w1_sections,
        "w2_sections": w2_sections,
        "financial": {
            "sel_cost": sel_cost,
            "sel_savings": sel_savings,
            "emergency_total": sel_savings + sel_cost,
            "roi_pct": roi_pct,
        },
        "schedule": schedule,
        "plain_text": plain_text,
    }


def build_capital_works_report(
    sel_data: pd.DataFrame,
    *,
    budget: int,
    use_real: bool = False,
    session_state: dict[str, Any] | None = None,
    skip_w1_prefetch: bool = False,
) -> str:
    """
    Build plain-text capital works report for selected pipes.

    session_state: pass st.session_state to attach Workflow 2 appendix when available.
    """
    n_sel = len(sel_data)
    sel_cost = int(sel_data["replacement_cost"].sum())
    sel_savings = int(sel_data["expected_savings"].sum())
    sel_props = int(sel_data["properties_affected"].sum())
    roi_pct = (sel_savings / max(sel_cost, 1)) * 100

    lines = [
        "CITYNERVE CAPITAL WORKS ORDER REPORT",
        "━" * 56,
        f"Generated:      {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}",
        "Prepared by:    CityNerve SubSurface · Nemotron (local GX10)",
        f"Annual Budget:  ${budget:,}",
        f"Pipes Selected: {n_sel}",
        "",
        "━━━ PRIORITY QUEUE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"{'#':<4} {'Pipe ID':<10} {'Risk':>6}  {'Ward':<15} {'Material':<16} "
        f"{'Replace $':>10} {'Savings $':>10}",
        "─" * 75,
    ]
    for i, (_, r) in enumerate(sel_data.iterrows(), 1):
        lines.append(
            f"{i:<4} {r['pipe_id']:<10} {r['risk_score']:>5.1f}%  "
            f"{r['ward']:<15} {r['material']:<16} "
            f"${r['replacement_cost']:>9,} ${r['expected_savings']:>9,}"
        )

    lines += ["", "━━━ RISK INTELLIGENCE (Nemotron Workflow 1) ━━━━━━━━━━━"]
    top_for_llm = sel_data.head(MAX_NEMOTRON_PIPES)
    if not skip_w1_prefetch and top_for_llm.shape[0]:
        top_ids = [str(p) for p in top_for_llm["pipe_id"].tolist()]
        ensure_w1_summaries(
            top_ids, use_real=use_real, session_state=session_state, show_spinner=False
        )
    for _, r in top_for_llm.iterrows():
        pid, text = _w1_summary_line(str(r["pipe_id"]), use_real, session_state)
        lines.append(f"  {pid}:")
        lines.append(f"    {text}")

    if n_sel > MAX_NEMOTRON_PIPES:
        lines.append("")
        lines.append(
            f"  … {n_sel - MAX_NEMOTRON_PIPES} additional pipe(s) — driver summary:"
        )
        for _, r in sel_data.iloc[MAX_NEMOTRON_PIPES:].iterrows():
            lines.append(f"    {r['pipe_id']}: {failure_summary(r)}")

    lines += ["", "━━━ FAILURE DRIVERS (deterministic) ━━━━━━━━━━━━━━━━━━━━━"]
    for _, r in sel_data.iterrows():
        lines.append(f"  {r['pipe_id']}: {failure_summary(r)}")

    # W2 appendix from Risk Map session
    if session_state is not None:
        w2_blocks: list[str] = []
        for pid in sel_data["pipe_id"].astype(str):
            key = w2_session_key(pid)
            run = session_state.get(key)
            if not run:
                continue
            run_id = run.get("run_id", key)
            source = run.get("source", "unknown")
            plan = run.get("action_plan", {})
            actions = plan.get("recommended_actions", [])
            action_lines = [
                f"    - {a.get('action', '')} ({a.get('owner', '')})"
                for a in actions[:5]
            ]
            final = (run.get("final_markdown") or "")[:1200]
            w2_blocks.append(
                f"  {pid} · run {run_id} · source={source}\n"
                + "\n".join(action_lines)
                + (f"\n    Executive excerpt: {final[:400]}…" if final else "")
            )
        if w2_blocks:
            lines += ["", "━━━ MULTI-ROLE ANALYSIS (Workflow 2) ━━━━━━━━━━━━━━━━━"]
            lines.extend(w2_blocks)
            lines.append(
                "  Full role reports: Risk Map → Run multi-role analysis, or "
                "data/analysis_runs/<run_id>/"
            )

    lines += [
        "",
        "━━━ FINANCIAL SUMMARY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"  Total Replacement Cost:    ${sel_cost:>12,}",
        f"  Total Est. Emergency Cost: ${sel_savings + sel_cost:>12,}",
        f"  Net Expected Savings:      ${sel_savings:>12,}",
        f"  Properties Protected:      {sel_props:>12,}",
        f"  Portfolio ROI:             {roi_pct:>11.0f}%",
        "",
        "━━━ RECOMMENDED SCHEDULE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    ward_groups = sel_data.groupby("ward")["pipe_id"].apply(list)
    for q_idx, (ward, pipes) in enumerate(ward_groups.items(), 1):
        pipe_list = ", ".join(pipes[:4])
        if len(pipes) > 4:
            pipe_list += f" (+{len(pipes)-4} more)"
        lines.append(f"  Q{min(q_idx, 4)}: {pipe_list} — {ward}")

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "  Nemotron Nano 12B (W1) · Nemotron Super (W2) · CityNerve SubSurface",
        "  Human approval required for all operational dispatch decisions.",
    ]
    return "\n".join(lines)


def build_work_order_text(
    wo_pipe: pd.Series,
    *,
    wo_rank: int,
    queue_len: int,
    use_real: bool = False,
    session_state: dict[str, Any] | None = None,
) -> str:
    """Single-pipe work order using Nemotron W1 when available."""
    pipe_id = str(wo_pipe["pipe_id"])
    wo_level = str(wo_pipe["risk_level"])

    risk_block = failure_summary(wo_pipe)
    risk_tag = "deterministic drivers"
    try:
        payload: dict[str, Any] | None = None
        if session_state is not None:
            cached = session_state.get(w1_session_key(pipe_id))
            if cached and cached.get("use_real") == use_real and not cached.get("error"):
                payload = cached
        if payload is None:
            payload = get_risk_summary_api(pipe_id, use_real=use_real)
        s = payload.get("summary", {})
        source = payload.get("source", "unknown")
        risk_block = (
            f"{s.get('headline', '')}\n"
            f"{s.get('risk_sentence', '')}\n"
            f"Drivers: {'; '.join(s.get('top_reasons', [])[:3])}\n"
            f"Recommended: {s.get('recommended_next_step', '')}"
        )
        risk_tag = f"Nemotron W1 ({source})"
    except Exception:
        pass

    w2_appendix = ""
    if session_state is not None:
        run = session_state.get(w2_session_key(pipe_id))
        if run:
            plan = run.get("action_plan", {})
            actions = plan.get("recommended_actions", [])
            w2_appendix = "\n━━━ WORKFLOW 2 ACTION PLAN (excerpt) ━━━━━━━━━━━━━━━━━\n"
            for a in actions[:6]:
                w2_appendix += (
                    f"  • {a.get('action')} — {a.get('owner')} "
                    f"(approval required: {a.get('requires_human_approval', True)})\n"
                )

    return f"""\
CITYNERVE MAINTENANCE WORK ORDER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WO Number:     CN-{pipe_id}-{wo_pipe['install_year']}
Generated:     {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}
Priority:      {wo_level.upper()} — Rank #{wo_rank} of {queue_len}
Status:        DRAFT — REQUIRES HUMAN APPROVAL

━━━ SEGMENT DETAILS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Pipe ID:       {pipe_id}
Location:      {wo_pipe['ward']}, Toronto ON
Material:      {wo_pipe['material']} (installed {wo_pipe['install_year']})
Dimensions:    {wo_pipe['diameter_mm']}mm × {wo_pipe['length_m']}m length
Risk Score:    {wo_pipe['risk_score']:.1f} / 100

━━━ RISK INTELLIGENCE ({risk_tag}) ━━━━━━━━━━━━━━━━━━
{risk_block}

━━━ FINANCIAL ANALYSIS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Replacement Cost:      ${int(wo_pipe['replacement_cost']):>12,}
Emergency Cost (proj): ${int(wo_pipe['emergency_cost']):>12,}
Expected Net Savings:  ${int(wo_pipe['expected_savings']):>12,}
Properties Protected:  {int(wo_pipe['properties_affected']):>12,}

━━━ RECOMMENDED SCOPE OF WORK ━━━━━━━━━━━━━━━━━━━━━━
1. Field verification per Workflow 2 / engineering review
2. Traffic control — {wo_pipe['ward']} district coordination
3. Targeted repair or renewal per approved capital scope
4. Pressure test and clearance before service restore
{w2_appendix}
Generated by: Nemotron · CityNerve SubSurface Intelligence
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
