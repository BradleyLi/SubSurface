"""Extract and parse JSON from LLM responses."""

from __future__ import annotations

import json
import re


def extract_json_object(text: str) -> str:
    """Pull the first JSON object from model output."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model response")
    return cleaned[start : end + 1]


def parse_json_object(text: str) -> dict:
    return json.loads(extract_json_object(text))
