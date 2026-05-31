"""Deterministic Workflow 2 fallbacks when Nemotron Super is unavailable."""

from __future__ import annotations

from agent.schemas import (
    ActionPlan,
    AnalysisPacket,
    RecommendedAction,
    RoleName,
    RoleReport,
)


def _asset_summary(packet: AnalysisPacket) -> str:
    a = packet.assets[0]
    prob = round(a.predicted_break_probability * 100, 1)
    return (
        f"Pipe {a.pipe_id} ({a.material or 'unknown'}, {a.age_years or '?'} years) — "
        f"{a.risk_category} risk, {prob}% model-estimated break probability, "
        f"{a.risk_percentile:.1f}th percentile."
    )


def template_role_report(packet: AnalysisPacket, role: RoleName) -> RoleReport:
    summary = _asset_summary(packet)
    a = packet.assets[0]

    if role is RoleName.ENGINEER:
        md = f"""# Engineer Analysis

## Asset risk interpretation
{summary}

## Main technical drivers
{'; '.join(c.feature_label for c in a.top_shap_contributors[:3])}.

## Replacement vs inspection considerations
Review for targeted inspection before capital replacement.

## Hydraulic / network concerns
Insufficient data for hydraulic modeling in this packet.

## Missing engineering data
Valve isolation zone, recent CCTV inspection.

## Recommended engineering actions
Schedule engineering review and field verification (human approval required).

## Confidence
Medium — template fallback; model unavailable.
"""
    elif role is RoleName.POLICE:
        md = f"""# Police / Traffic Safety Analysis

## Public safety concerns
{summary}

## Traffic and road access considerations
Review traffic control if field verification confirms leak or road distress.

## Emergency access considerations
Confirm emergency vehicle access routes with operations.

## Suggested coordination points
Coordinate with operations and field crews.

## Missing information
Road classification, active traffic counts.

## Recommended safety actions
Monitor; escalate only after field confirmation (human approval required).

## Confidence
Medium — template fallback.
"""
    elif role is RoleName.FIELD:
        md = f"""# Field Investigation Crew Analysis

## Field verification objectives
Confirm active leak indicators and pipe condition at {a.pipe_id}.

## Site inspection checklist
- Visual surface distress
- Pressure complaints in area
- Corrosion at joints

## Leak / break indicators to check
Moisture, pressure loss reports, prior breaks.

## Data to collect
Photos, acoustic survey if available, GPS tie-in.

## Escalation triggers
Active leak, road undermining, pressure zone failure.

## Missing information
Recent work orders, valve status.

## Recommended field actions
Schedule field verification (human approval required).

## Confidence
Medium — template fallback.
"""
    else:
        md = f"""# Operations Analysis

## Operational priority
{a.risk_category} — prioritize after field verification.

## Crew and equipment considerations
Standard repair crew; confirm availability with dispatch.

## Valve / isolation planning considerations
Isolation plan required; not in evidence packet.

## Customer and service impacts
Approximately {a.properties_affected or 'unknown'} properties in impact proxy.

## Work order recommendations
Draft inspection work order pending approval.

## Missing operational data
Crew schedule, parts inventory, valve map.

## Recommended operational actions
Queue for operations review (human approval required).

## Confidence
Medium — template fallback.
"""

    from agent.w2_prompts import role_filename

    return RoleReport(
        role=role,
        markdown=md.strip(),
        source="template",
        filename=role_filename(role),
    )


def template_synthesis(
    packet: AnalysisPacket,
    role_reports: list[RoleReport],
) -> tuple[str, ActionPlan]:
    a = packet.assets[0]
    consensus = _asset_summary(packet)
    final_md = f"""# Final Watermain Risk Summary and Action Plan

## Executive summary
{consensus} Template fallback synthesis (Nemotron unavailable).

## Highest-risk assets
{a.pipe_id}

## Cross-role consensus
All roles recommend field verification before operational action.

## Disagreements or uncertainty
None identified in template mode.

## Immediate actions
Schedule field verification.

## Field verification plan
See Field Investigation report.

## Engineering recommendation
See Engineer report.

## Traffic / public safety coordination
See Police report.

## Operations plan
See Operations report.

## Data gaps
Valve isolation zone, road class, recent work orders.

## Human approvals required
All dispatch, closure, and excavation decisions.

## Appendix: evidence used
Evidence packet run_id {packet.run_id}.
"""

    plan = ActionPlan(
        run_id=packet.run_id,
        priority=a.risk_category,
        recommended_actions=[
            RecommendedAction(
                action="Schedule field verification",
                owner="Field Investigation Crew",
                urgency="near_term",
                requires_human_approval=True,
                evidence=[
                    f"risk_percentile={a.risk_percentile}",
                    f"predicted_break_probability={a.predicted_break_probability}",
                ],
            ),
        ],
        missing_data=[
            "valve isolation zone",
            "road classification",
            "recent work order history",
        ],
        model_versions={
            "risk_model": f"{packet.risk_model.model_name}:{packet.risk_model.model_version}",
            "llm": "template-fallback",
        },
    )
    return final_md.strip(), plan
