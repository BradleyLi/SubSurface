"""Match a voice call transcript to a watermain in the pipe table."""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from difflib import SequenceMatcher

import pandas as pd

from agent.harness.voice_transcript import _STREET_ALIASES, extract_incident_location
from agent.neighbourhoods import NeighbourhoodMatch, resolve_neighbourhood
from agent.voice_context import load_voice_transcript

_MATCH_CONFIDENCE_THRESHOLD = 0.5
# Tight radius for precise intersection coordinates.
_GEO_MAX_METERS = 500.0
# Neighbourhood centroids are approximate (area-level), so snap to the nearest
# watermain within a much larger radius.
_NEIGHBOURHOOD_GEO_MAX_METERS = 6_000.0

NeighbourhoodResolver = Callable[[str], "NeighbourhoodMatch | None"]


@dataclass(frozen=True)
class VoicePipeMatch:
    pipe_id: str
    confidence: float
    method: str
    matched_street: str | None = None
    matched_neighbourhood: str | None = None
    lat: float | None = None
    lon: float | None = None


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _street_aliases_in_text(text: str) -> list[str]:
    normalized = text.lower()
    found: list[str] = []
    for street, aliases in _STREET_ALIASES.items():
        if any(re.search(rf"\b{re.escape(alias)}\b", normalized) for alias in aliases):
            found.append(street)
    return found


def _transcript_full_text(payload: dict) -> str:
    parts: list[str] = []
    for entry in payload.get("transcript") or []:
        parts.append(str(entry.get("content", "")))
    incident = payload.get("incident") or {}
    loc = incident.get("location") if isinstance(incident, dict) else None
    if isinstance(loc, dict):
        if loc.get("address"):
            parts.append(str(loc["address"]))
        for s in loc.get("streets") or []:
            parts.append(str(s))
    return " ".join(parts)


def _street_match_score(street_val: str, transcript_text: str, location_streets: list[str]) -> float:
    if not street_val or not street_val.strip():
        return 0.0
    street_norm = _normalize_text(street_val)
    text_norm = _normalize_text(transcript_text)
    ratio = SequenceMatcher(None, street_norm, text_norm).ratio()

    street_mentions = _street_aliases_in_text(street_val)
    loc_hits = sum(1 for s in location_streets if s in street_mentions or s.lower() in street_norm)
    if len(location_streets) >= 2 and loc_hits >= 2:
        return max(ratio, 0.85)
    if location_streets and loc_hits >= 1:
        return max(ratio, 0.65)

    mention_hits = sum(1 for s in street_mentions if any(a in text_norm for a in _STREET_ALIASES.get(s, ())))
    if mention_hits >= 2:
        return max(ratio, 0.75)
    return ratio


def _geo_score(
    row: pd.Series,
    lat: float,
    lon: float,
    max_meters: float = _GEO_MAX_METERS,
) -> float:
    if pd.isna(row.get("lat")) or pd.isna(row.get("lon")):
        return 0.0
    dist = _haversine_m(lat, lon, float(row["lat"]), float(row["lon"]))
    if dist > max_meters:
        return 0.0
    return max(0.0, 1.0 - dist / max_meters)


def match_transcript_to_pipe(
    payload: dict,
    df: pd.DataFrame,
    *,
    neighbourhood_resolver: NeighbourhoodResolver | None = None,
) -> VoicePipeMatch | None:
    """Score all pipes and return the best match, or None if below threshold.

    Geo coordinates come from a precise street intersection when available. When
    the caller only named an area, the transcript is semantically resolved to a
    Toronto neighbourhood centroid and the nearest watermain is selected.
    """
    transcript_text = _transcript_full_text(payload)
    transcript_list = payload.get("transcript") or []
    location = extract_incident_location(transcript_list) or {}
    location_streets: list[str] = list(location.get("streets") or [])

    lat = location.get("lat")
    lon = location.get("lon")
    has_geo = lat is not None and lon is not None
    geo_max = _GEO_MAX_METERS

    neighbourhood: NeighbourhoodMatch | None = None
    if not has_geo:
        resolver = neighbourhood_resolver or resolve_neighbourhood
        neighbourhood = resolver(transcript_text)
        if neighbourhood is not None:
            lat, lon = neighbourhood.lat, neighbourhood.lon
            has_geo = True
            geo_max = _NEIGHBOURHOOD_GEO_MAX_METERS

    best: VoicePipeMatch | None = None
    best_score = 0.0

    for _, row in df.iterrows():
        pipe_id = str(row["pipe_id"])
        street_val = str(row.get("street") or "")

        street_s = _street_match_score(street_val, transcript_text, location_streets)
        geo_s = _geo_score(row, float(lat), float(lon), geo_max) if has_geo else 0.0

        if street_s > 0 and geo_s > 0:
            score = 0.6 * street_s + 0.4 * geo_s
            method = "neighbourhood+street" if neighbourhood else "street+geo"
        elif street_s > 0:
            score = street_s
            method = "street"
        elif geo_s > 0:
            score = geo_s
            method = "neighbourhood" if neighbourhood else "geo"
        else:
            continue

        if score > best_score:
            best_score = score
            best = VoicePipeMatch(
                pipe_id=pipe_id,
                confidence=round(min(score, 1.0), 3),
                method=method,
                matched_street=street_val or None,
                matched_neighbourhood=neighbourhood.name if neighbourhood else None,
                lat=float(lat) if has_geo else None,
                lon=float(lon) if has_geo else None,
            )

    if best is None or best.confidence < _MATCH_CONFIDENCE_THRESHOLD:
        return None
    return best


def find_pipe_for_latest_transcript(
    df: pd.DataFrame,
    *,
    transcript_path: str | None = None,
) -> tuple[dict | None, VoicePipeMatch | None]:
    """Load latest (or explicit) transcript and match to a pipe."""
    payload = load_voice_transcript(transcript_path)
    if payload is None:
        return None, None
    match = match_transcript_to_pipe(payload, df)
    return payload, match
