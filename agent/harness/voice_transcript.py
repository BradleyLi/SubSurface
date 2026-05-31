"""Serialize voice-session messages to JSON."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


_STREET_ALIASES: dict[str, tuple[str, ...]] = {
    "Yonge Street": ("yonge", "young", "younge"),
    "Bloor Street": ("bloor", "bloore", "blower", "blur", "poor"),
    "Queen Street": ("queen",),
    "King Street": ("king",),
    "Dundas Street": ("dundas",),
    "College Street": ("college",),
    "Spadina Avenue": ("spadina",),
    "University Avenue": ("university",),
    "Bay Street": ("bay",),
    "Bathurst Street": ("bathurst",),
}
_INTERSECTION_COORDS: dict[frozenset[str], tuple[float, float]] = {
    frozenset(("Yonge Street", "Bloor Street")): (43.6708, -79.3868),
}


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                elif "text" in item:
                    parts.append(str(item["text"]))
        return " ".join(p for p in parts if p).strip()
    return str(content)


def normalize_messages(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Turn chat messages into simple role/content records for JSON export."""
    records: list[dict[str, str]] = []
    for message in messages:
        role = str(message.get("role", "unknown"))
        content = _content_to_text(message.get("content"))
        if not content and role != "system":
            continue
        records.append({"role": role, "content": content})
    return records


def caller_transcript(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Caller and agent turns only (no system prompt) for dispatch handoff."""
    return [m for m in normalize_messages(messages) if m["role"] in ("user", "assistant")]


def _street_mentions(text: str) -> list[str]:
    normalized = text.lower()
    mentions: list[str] = []
    for street, aliases in _STREET_ALIASES.items():
        if any(re.search(rf"\b{re.escape(alias)}\b", normalized) for alias in aliases):
            mentions.append(street)
    return mentions


def extract_incident_location(
    transcript: list[dict[str, str]],
) -> dict[str, Any] | None:
    """Map spoken location mentions into a structured JSON location record."""
    best: tuple[dict[str, str], list[str]] | None = None
    for entry in reversed(transcript):
        mentions = _street_mentions(entry["content"])
        if len(mentions) >= 2:
            best = (entry, mentions[:2])
            break

    if best is None:
        return None

    entry, streets = best
    address = f"{streets[0]} & {streets[1]}, Toronto, ON"
    coords = _INTERSECTION_COORDS.get(frozenset(streets))
    location: dict[str, Any] = {
        "type": "intersection",
        "address": address,
        "streets": streets,
        "source_role": entry["role"],
        "source_text": entry["content"],
        "confidence": "high" if coords else "medium",
    }
    if coords:
        location["lat"] = coords[0]
        location["lon"] = coords[1]
    return location


def write_messages_json(
    *,
    messages: list[dict[str, Any]],
    output_dir: Path,
    session_id: str | None = None,
    started_at: datetime | None = None,
    model: str | None = None,
    base_url: str | None = None,
) -> Path:
    """Write call transcript JSON to ``output_dir`` (intended for End-call only)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    ended_at = datetime.now(timezone.utc)
    sid = session_id or str(uuid4())
    stamp = ended_at.strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"voice_transcript_{sid}_{stamp}.json"
    transcript = caller_transcript(messages)
    location = extract_incident_location(transcript)

    payload = {
        "session_id": sid,
        "started_at": (started_at or ended_at).isoformat(),
        "ended_at": ended_at.isoformat(),
        "model": model,
        "llm_base_url": base_url,
        "turn_count": sum(1 for entry in transcript if entry["role"] == "user"),
        "incident": {
            "location": location,
        },
        "transcript": transcript,
    }

    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
