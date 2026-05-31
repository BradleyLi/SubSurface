"""Serialize voice-session messages to JSON."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

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

    payload = {
        "session_id": sid,
        "started_at": (started_at or ended_at).isoformat(),
        "ended_at": ended_at.isoformat(),
        "model": model,
        "llm_base_url": base_url,
        "turn_count": sum(1 for entry in transcript if entry["role"] == "user"),
        "transcript": transcript,
    }

    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
