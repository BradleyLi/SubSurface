"""
Pydantic contracts for Workflow 1 and Workflow 2.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ShapContributor(BaseModel):
    feature_label: str
    feature_value: str | int | float | bool
    impact: Literal["increase_risk", "decrease_risk"]
    shap_contribution: float | None = None


class PipeRiskEvidence(BaseModel):
    pipe_id: str
    predicted_break_probability: float = Field(ge=0.0, le=1.0)
    risk_percentile: float = Field(ge=0.0, le=100.0)
    risk_category: str
    ward: str | None = None
    material: str | None = None
    age_years: int | None = None
    diameter_mm: int | None = None
    length_m: int | None = None
    properties_affected: int | None = None
    emergency_cost: int | None = None
    top_shap_contributors: list[ShapContributor] = Field(min_length=1, max_length=8)


class Workflow1Summary(BaseModel):
    pipe_id: str
    headline: str = Field(max_length=160)
    risk_sentence: str = Field(max_length=280)
    top_reasons: list[str] = Field(min_length=1, max_length=5)
    recommended_next_step: str = Field(max_length=220)
    caveats: list[str] = Field(max_length=3)


class RiskSummaryResponse(BaseModel):
    """API envelope for Workflow 1."""

    summary: Workflow1Summary
    source: Literal["nemotron", "template"]
    model: str | None = None
    evidence: PipeRiskEvidence


# --- Workflow 2 ---


class RoleName(str, Enum):
    ENGINEER = "engineer"
    POLICE = "police"
    FIELD = "field"
    OPERATIONS = "operations"


class AnalysisScope(BaseModel):
    scope_type: Literal["single_pipe"] = "single_pipe"
    pipe_ids: list[str] = Field(min_length=1)
    generated_at: str


class RiskModelInfo(BaseModel):
    model_name: str = "watermain_risk_composite"
    model_version: str = "2026-hackathon"
    target: str = "break_next_year"
    calibration_note: str = (
        "Probability is model-estimated annual break probability from composite risk score."
    )


class AnalysisConstraints(BaseModel):
    do_not_invent_missing_fields: bool = True
    human_approval_required_for_dispatch: bool = True
    output_format: Literal["markdown"] = "markdown"


class NetworkContext(BaseModel):
    properties_affected: int | None = None
    emergency_cost: int | None = None
    note: str = "Topological cascade proxy; not a hydraulic EPANET simulation."


class CallerReport(BaseModel):
    session_id: str
    ended_at: str | None = None
    location: dict[str, Any] | None = None
    transcript: list[dict[str, str]] = Field(default_factory=list)
    match_confidence: float | None = None
    match_method: str | None = None


class PerRoleCallerContext(BaseModel):
    """Orchestrator output: one focused context string per W2 role."""

    engineer: str = ""
    police: str = ""
    field: str = ""
    operations: str = ""
    synthesis: str = ""


class AnalysisPacket(BaseModel):
    run_id: str
    analysis_scope: AnalysisScope
    risk_model: RiskModelInfo
    assets: list[PipeRiskEvidence] = Field(min_length=1)
    network_context: NetworkContext | None = None
    constraints: AnalysisConstraints = Field(default_factory=AnalysisConstraints)
    caller_report: CallerReport | None = None


class RoleReport(BaseModel):
    role: RoleName
    markdown: str
    source: Literal["nemotron", "template"]
    filename: str


class RecommendedAction(BaseModel):
    action: str
    owner: str
    urgency: Literal["immediate", "near_term", "routine"] = "near_term"
    requires_human_approval: bool = True
    evidence: list[str] = Field(default_factory=list)


class ActionPlan(BaseModel):
    run_id: str
    priority: str
    recommended_actions: list[RecommendedAction] = Field(min_length=1)
    missing_data: list[str] = Field(default_factory=list)
    model_versions: dict[str, str] = Field(default_factory=dict)


class AnalysisRunResponse(BaseModel):
    run_id: str
    status: Literal["completed", "failed"] = "completed"
    pipe_id: str
    roles: list[RoleReport]
    final_markdown: str
    action_plan: ActionPlan
    source: Literal["nemotron", "template", "partial"]
    models: dict[str, str] = Field(default_factory=dict)
    created_at: str
    storage_dir: str | None = None


class AnalysisRunRequest(BaseModel):
    pipe_id: str
    use_real: bool = False
    use_latest_voice_transcript: bool = True
    transcript_path: str | None = None
