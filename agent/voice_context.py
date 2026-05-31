"""Load voice call transcripts and format them for the W2 orchestrator."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_OUTPUT_DIR = Path(
    os.getenv("VOICE_OUTPUT_DIR", str(_REPO_ROOT / "voice_sessions"))
)


def voice_output_dir() -> Path:
    return Path(os.getenv("VOICE_OUTPUT_DIR", str(_DEFAULT_OUTPUT_DIR)))


def load_voice_transcript(path: Path | str | None = None) -> dict[str, Any] | None:
    """Load a transcript JSON file, or the newest ``voice_transcript_*.json`` in the output dir."""
    if path is not None:
        p = Path(path)
        if not p.is_file():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    out_dir = voice_output_dir()
    if not out_dir.is_dir():
        return None

    candidates = sorted(
        out_dir.glob("voice_transcript_*.json"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None
    return json.loads(candidates[0].read_text(encoding="utf-8"))


def caller_report_from_payload(
    payload: dict[str, Any],
    *,
    match_confidence: float | None = None,
    match_method: str | None = None,
) -> dict[str, Any]:
    """Build kwargs for ``CallerReport`` from a saved transcript JSON."""
    incident = payload.get("incident") or {}
    location = incident.get("location") if isinstance(incident, dict) else None
    transcript = payload.get("transcript") or []
    return {
        "session_id": str(payload.get("session_id", "")),
        "ended_at": payload.get("ended_at"),
        "location": location,
        "transcript": transcript,
        "match_confidence": match_confidence,
        "match_method": match_method,
    }


def format_transcript_for_orchestrator(payload: dict[str, Any]) -> str:
    """Compact flat text of the call for the transcript triage orchestrator."""
    lines: list[str] = []
    session_id = payload.get("session_id")
    if session_id:
        lines.append(f"Session: {session_id}")
    if payload.get("ended_at"):
        lines.append(f"Ended: {payload['ended_at']}")

    incident = payload.get("incident") or {}
    location = incident.get("location") if isinstance(incident, dict) else None
    if isinstance(location, dict) and location:
        if location.get("address"):
            lines.append(f"Reported location: {location['address']}")
        if location.get("streets"):
            lines.append(f"Streets: {', '.join(location['streets'])}")
        if location.get("lat") is not None and location.get("lon") is not None:
            lines.append(f"Coordinates: {location['lat']}, {location['lon']}")

    lines.append("")
    lines.append("Call transcript:")
    for entry in payload.get("transcript") or []:
        role = entry.get("role", "unknown")
        content = (entry.get("content") or "").strip()
        if not content:
            continue
        label = "Caller" if role == "user" else "Agent"
        lines.append(f"- {label}: {content}")

    return "\n".join(lines).strip()
