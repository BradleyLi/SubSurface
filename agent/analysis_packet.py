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
    NetworkContext,
    RiskModelInfo,
)


def make_run_id(pipe_id: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_id = pipe_id.replace("/", "-").replace(" ", "_")
    return f"risk_review_{ts}_{safe_id}"


def build_analysis_packet(
    pipe_id: str,
    df: pd.DataFrame,
    *,
    run_id: str | None = None,
) -> AnalysisPacket:
    matches = df[df["pipe_id"] == pipe_id]
    if matches.empty:
        raise KeyError(f"Pipe not found: {pipe_id}")

    row = matches.iloc[0]
    evidence = build_evidence_from_row(row, df=df)
    rid = run_id or make_run_id(pipe_id)

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
            pipe_ids=[pipe_id],
            generated_at=datetime.now(timezone.utc).isoformat(),
        ),
        risk_model=RiskModelInfo(),
        assets=[evidence],
        network_context=network,
        constraints=AnalysisConstraints(),
    )
