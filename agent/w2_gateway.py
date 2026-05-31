"""
Workflow 2 gateway: multi-role analysis via Nemotron Super (harness W2).
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone

import pandas as pd

from agent.analysis_packet import build_analysis_packet
from agent.harness.client import chat as harness_chat
from agent.harness.endpoints import WorkflowProfile, get_endpoint
from agent.json_utils import parse_json_object
from agent.procurement.bom import build_bom
from agent.procurement.bom_views import full_bom_summary, project_bom_for_role
from agent.procurement.finalize import finalize_items_llm
from agent.procurement.part_selection import (
    select_candidate_items,
    transcript_text_from_packet,
)
from agent.schemas import (
    ActionPlan,
    AnalysisPacket,
    AnalysisRunResponse,
    BillOfMaterials,
    CallerReport,
    PerRoleCallerContext,
    RecommendedAction,
    RoleName,
    RoleReport,
)
from agent.voice_context import caller_report_from_payload
from agent.voice_pipe_match import find_pipe_for_latest_transcript
from agent.w2_orchestrator import call_transcript_orchestrator
from agent.w2_prompts import (
    build_role_messages,
    build_synthesis_messages,
    role_filename,
    split_synthesis_response,
)
from agent.w2_storage import save_run
from agent.w2_template import template_role_report, template_synthesis
from data_utils import get_pipes

_ALL_ROLES = [
    RoleName.ENGINEER,
    RoleName.POLICE,
    RoleName.FIELD,
    RoleName.OPERATIONS,
]

_ROLE_CONTEXT_ATTR = {
    RoleName.ENGINEER: "engineer",
    RoleName.POLICE: "police",
    RoleName.FIELD: "field",
    RoleName.OPERATIONS: "operations",
}


def _w2_parallel() -> bool:
    return os.getenv("W2_PARALLEL", "true").lower() in ("1", "true", "yes")


def _append_context(existing: str, addition: str) -> str:
    existing = (existing or "").strip()
    addition = (addition or "").strip()
    if not addition:
        return existing
    return f"{existing}\n\n{addition}".strip() if existing else addition


def _attach_bom_context(
    per_role_ctx: PerRoleCallerContext,
    bom: BillOfMaterials,
) -> PerRoleCallerContext:
    return PerRoleCallerContext(
        engineer=_append_context(
            per_role_ctx.engineer,
            project_bom_for_role(bom, RoleName.ENGINEER),
        ),
        police=_append_context(
            per_role_ctx.police,
            project_bom_for_role(bom, RoleName.POLICE),
        ),
        field=_append_context(
            per_role_ctx.field,
            project_bom_for_role(bom, RoleName.FIELD),
        ),
        operations=_append_context(
            per_role_ctx.operations,
            project_bom_for_role(bom, RoleName.OPERATIONS),
        ),
        synthesis=_append_context(per_role_ctx.synthesis, full_bom_summary(bom)),
    )


def _attach_procurement_action(plan: ActionPlan, bom: BillOfMaterials) -> ActionPlan:
    if not bom.contract_awards:
        return plan
    suppliers = ", ".join(a.supplier_name for a in bom.contract_awards[:4])
    evidence = [
        f"{a.supplier_name}: {a.scope} ({a.award_subtotal:.2f} CAD)"
        for a in bom.contract_awards
    ]
    plan.recommended_actions.append(
        RecommendedAction(
            action=(
                "Review draft supplier contract awards for watermain repair BoM: "
                f"{suppliers}"
            ),
            owner="Operations / Procurement",
            urgency="near_term",
            requires_human_approval=True,
            evidence=evidence,
        )
    )
    return plan


def _resolve_caller_report(
    pipe_id: str,
    df: pd.DataFrame,
    *,
    caller_report: CallerReport | None,
    use_latest_voice_transcript: bool,
    transcript_path: str | None,
) -> CallerReport | None:
    """Attach caller report only when transcript matches the requested pipe."""
    if caller_report is not None:
        return caller_report

    if not use_latest_voice_transcript:
        return None

    payload, match = find_pipe_for_latest_transcript(
        df, transcript_path=transcript_path
    )
    if payload is None or match is None or match.pipe_id != pipe_id:
        return None

    return CallerReport.model_validate(
        caller_report_from_payload(
            payload,
            match_confidence=match.confidence,
            match_method=match.method,
        )
    )


async def _call_role(
    packet: AnalysisPacket,
    role: RoleName,
    per_role_ctx: PerRoleCallerContext,
) -> RoleReport:
    attr = _ROLE_CONTEXT_ATTR[role]
    role_context = getattr(per_role_ctx, attr, "")
    messages = build_role_messages(packet, role, role_context=role_context)
    try:
        markdown = await harness_chat(
            WorkflowProfile.WORKFLOW2,
            messages,
            json_mode=False,
        )
        if not markdown.strip():
            raise RuntimeError("Empty role response")
        return RoleReport(
            role=role,
            markdown=markdown.strip(),
            source="nemotron",
            filename=role_filename(role),
        )
    except Exception:
        return template_role_report(packet, role)


async def _call_synthesis(
    packet: AnalysisPacket,
    role_reports: list[RoleReport],
    *,
    model_name: str,
    per_role_ctx: PerRoleCallerContext,
) -> tuple[str, ActionPlan, str]:
    """Returns (final_markdown, action_plan, source)."""
    messages = build_synthesis_messages(
        packet,
        role_reports,
        synthesis_context=per_role_ctx.synthesis,
    )
    try:
        raw = await harness_chat(
            WorkflowProfile.WORKFLOW2,
            messages,
            json_mode=False,
        )
        try:
            final_md, plan_data = split_synthesis_response(raw)
        except (ValueError, json.JSONDecodeError):
            plan_data = parse_json_object(raw)
            final_md = raw[: raw.rfind("{")].strip() if "{" in raw else raw.strip()
        plan_data["run_id"] = packet.run_id
        plan = ActionPlan.model_validate(plan_data)
        if "llm" not in plan.model_versions:
            plan.model_versions["llm"] = model_name
        if "risk_model" not in plan.model_versions:
            plan.model_versions["risk_model"] = (
                f"{packet.risk_model.model_name}:{packet.risk_model.model_version}"
            )
        return final_md, plan, "nemotron"
    except Exception:
        final_md, plan = template_synthesis(packet, role_reports)
        return final_md, plan, "template"


async def workflow2_run(
    pipe_id: str,
    *,
    use_real: bool = True,
    df: pd.DataFrame | None = None,
    caller_report: CallerReport | None = None,
    use_latest_voice_transcript: bool = True,
    transcript_path: str | None = None,
) -> AnalysisRunResponse:
    if df is None:
        df = get_pipes(use_real=use_real)

    resolved_caller = _resolve_caller_report(
        pipe_id,
        df,
        caller_report=caller_report,
        use_latest_voice_transcript=use_latest_voice_transcript,
        transcript_path=transcript_path,
    )

    packet = build_analysis_packet(
        pipe_id, df, caller_report=resolved_caller
    )
    endpoint = get_endpoint(WorkflowProfile.WORKFLOW2)
    model_name = endpoint.model

    per_role_ctx = PerRoleCallerContext()
    if resolved_caller is not None:
        per_role_ctx = await call_transcript_orchestrator(resolved_caller)

    evidence = packet.assets[0]
    transcript_text = (
        transcript_text_from_packet(resolved_caller.transcript)
        if resolved_caller is not None
        else ""
    )
    procurement_candidates = select_candidate_items(evidence, transcript_text)
    finalized_items, procurement_missing, procurement_source = await finalize_items_llm(
        packet,
        procurement_candidates,
        role_context=per_role_ctx.synthesis,
    )
    bill_of_materials = build_bom(
        pipe_id=pipe_id,
        run_id=packet.run_id,
        finalized_items=finalized_items,
        missing_data=procurement_missing,
        source=procurement_source,
    )
    per_role_ctx = _attach_bom_context(per_role_ctx, bill_of_materials)

    if _w2_parallel():
        role_reports = list(
            await asyncio.gather(
                *[
                    _call_role(packet, role, per_role_ctx)
                    for role in _ALL_ROLES
                ]
            )
        )
    else:
        role_reports = []
        for role in _ALL_ROLES:
            role_reports.append(await _call_role(packet, role, per_role_ctx))

    final_md, action_plan, synth_source = await _call_synthesis(
        packet,
        role_reports,
        model_name=model_name,
        per_role_ctx=per_role_ctx,
    )
    action_plan = _attach_procurement_action(action_plan, bill_of_materials)
    if "Recommended supplier contract awards" not in final_md:
        final_md = f"{final_md}\n\n{full_bom_summary(bill_of_materials)}"

    role_sources = {r.source for r in role_reports}
    if synth_source == "nemotron" and role_sources == {"nemotron"}:
        overall_source = "nemotron"
    elif synth_source == "template" and role_sources == {"template"}:
        overall_source = "template"
    else:
        overall_source = "partial"

    response = AnalysisRunResponse(
        run_id=packet.run_id,
        status="completed",
        pipe_id=pipe_id,
        roles=role_reports,
        final_markdown=final_md,
        action_plan=action_plan,
        bill_of_materials=bill_of_materials,
        source=overall_source,
        models={
            "workflow2": model_name,
            "risk_model": f"{packet.risk_model.model_name}:{packet.risk_model.model_version}",
        },
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    storage_path = save_run(response)
    response.storage_dir = str(storage_path)
    return response


def workflow2_run_sync(
    pipe_id: str,
    *,
    use_real: bool = True,
    df: pd.DataFrame | None = None,
    caller_report: CallerReport | None = None,
    use_latest_voice_transcript: bool = True,
    transcript_path: str | None = None,
) -> AnalysisRunResponse:
    return asyncio.run(
        workflow2_run(
            pipe_id,
            use_real=use_real,
            df=df,
            caller_report=caller_report,
            use_latest_voice_transcript=use_latest_voice_transcript,
            transcript_path=transcript_path,
        )
    )
