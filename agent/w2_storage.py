"""Persist Workflow 2 analysis runs to disk."""

from __future__ import annotations

import json
from pathlib import Path

from agent.schemas import ActionPlan, AnalysisRunResponse, RoleReport

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = REPO_ROOT / "data" / "analysis_runs"


def run_dir(run_id: str) -> Path:
    return RUNS_DIR / run_id


def save_run(response: AnalysisRunResponse) -> Path:
    directory = run_dir(response.run_id)
    directory.mkdir(parents=True, exist_ok=True)

    for role in response.roles:
        (directory / role.filename).write_text(role.markdown, encoding="utf-8")

    (directory / "final_summary.md").write_text(response.final_markdown, encoding="utf-8")
    (directory / "action_plan.json").write_text(
        response.action_plan.model_dump_json(indent=2),
        encoding="utf-8",
    )

    manifest = response.model_dump()
    (directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2, default=str),
        encoding="utf-8",
    )
    return directory


def load_manifest(run_id: str) -> dict | None:
    path = run_dir(run_id) / "manifest.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_file(run_id: str, filename: str) -> str | None:
    path = run_dir(run_id) / filename
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")
