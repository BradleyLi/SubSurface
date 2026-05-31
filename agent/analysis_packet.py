"""
Build Workflow 2 analysis packets from pipe dataframe rows.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from agent.evidence import build_evidence_from_row
from agent.schemas import (
    AnalysisConstraints,
    AnalysisPacket,
    AnalysisScope,
    CallerReport,
    NetworkContext,
    RiskModelInfo,
)
from ml_predictions import find_pipe_row


def make_run_id(pipe_id: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_id = pipe_id.replace("/", "-").replace(" ", "_")
    return f"risk_review_{ts}_{safe_id}"


def _risk_model_info(row: pd.Series) -> RiskModelInfo:
    if pd.notna(row.get("predicted_break_probability")):
        year = str(row.get("prediction_date", "2016"))[:4]
        return RiskModelInfo(
            model_name="xgb_break_risk_gpu",
            model_version=f"panel-{year}",
            target="break_next_year",
            calibration_note=(
                "XGBoost annual break probability with TreeSHAP feature attributions."
            ),
        )
    return RiskModelInfo()


def build_analysis_packet(
    pipe_id: str,
    df: pd.DataFrame,
    *,
    run_id: str | None = None,
    caller_report: CallerReport | None = None,
) -> AnalysisPacket:
    row = find_pipe_row(df, pipe_id)
    if row is None:
        raise KeyError(f"Pipe not found: {pipe_id}")

    evidence = build_evidence_from_row(row, df=df)
    rid = run_id or make_run_id(pipe_id)
    resolved_id = str(row["pipe_id"])

    network = NetworkContext(
        properties_affected=int(row["properties_affected"])
        if pd.notna(row.get("properties_affected"))
        else None,
        emergency_cost=int(row["emergency_cost"])
        if pd.notna(row.get("emergency_cost"))
        else None,
    )

    return AnalysisPacket(
        run_id=rid,
        analysis_scope=AnalysisScope(
            scope_type="single_pipe",
            pipe_ids=[resolved_id],
            generated_at=datetime.now(timezone.utc).isoformat(),
        ),
        risk_model=_risk_model_info(row),
        assets=[evidence],
        network_context=network,
        constraints=AnalysisConstraints(),
        caller_report=caller_report,
    )
