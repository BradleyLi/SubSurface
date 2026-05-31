"""Resolve a caller's spoken location to a Toronto neighbourhood centroid.

The City of Toronto "Neighbourhoods (historical 140)" polygons (EPSG:4326) are
loaded from a GeoJSON file. We compute each neighbourhood's centroid so a fuzzy
or LLM-resolved area name can be turned into (lat, lon) coordinates, which the
voice→watermain matcher then snaps to the nearest pipe.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

from shapely.geometry import shape

from agent.harness.endpoints import WorkflowProfile
from agent.json_utils import parse_json_object

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_GEOJSON = _REPO_ROOT / "data" / "neighbourhoods_140_4326.geojson"

# Trailing " (123)" area code the City appends to AREA_NAME, e.g. "Leaside (56)".
_AREA_CODE_SUFFIX = re.compile(r"\s*\(\d+\)\s*$")
# Directional / filler tokens that are too generic to anchor a fuzzy match.
_WEAK_TOKENS = {"west", "east", "north", "south", "the", "of", "and", "park", "village"}

_LLM_MAX_TOKENS = 120
_LLM_TEMPERATURE = 0.0
_FUZZY_THRESHOLD = 0.62


@dataclass(frozen=True)
class Neighbourhood:
    name: str  # cleaned, e.g. "Brookhaven-Amesbury"
    raw_name: str  # original AREA_NAME, e.g. "Brookhaven-Amesbury (30)"
    lat: float
    lon: float


@dataclass(frozen=True)
class NeighbourhoodMatch:
    name: str
    lat: float
    lon: float
    confidence: float
    method: str  # "llm" | "fuzzy"


def geojson_path() -> Path:
    """Path to the neighbourhoods GeoJSON (override via NEIGHBOURHOODS_GEOJSON)."""
    return Path(os.getenv("NEIGHBOURHOODS_GEOJSON", str(_DEFAULT_GEOJSON)))


def _clean_name(area_name: str) -> str:
    return _AREA_CODE_SUFFIX.sub("", area_name).strip()


@lru_cache(maxsize=4)
def load_neighbourhoods(path: str | None = None) -> tuple[Neighbourhood, ...]:
    """Load neighbourhoods and their polygon centroids from the GeoJSON file."""
    geo_path = Path(path) if path else geojson_path()
    if not geo_path.is_file():
        logger.warning("Neighbourhoods GeoJSON not found at %s", geo_path)
        return ()

    data = json.loads(geo_path.read_text(encoding="utf-8"))
    out: list[Neighbourhood] = []
    for feature in data.get("features") or []:
        props = feature.get("properties") or {}
        raw_name = str(props.get("AREA_NAME") or props.get("AREA_DESC") or "").strip()
        geometry = feature.get("geometry")
        if not raw_name or not geometry:
            continue
        try:
            centroid = shape(geometry).centroid
        except Exception as exc:  # pragma: no cover - defensive against bad geometry
            logger.warning("Bad geometry for %s: %s", raw_name, exc)
            continue
        out.append(
            Neighbourhood(
                name=_clean_name(raw_name),
                raw_name=raw_name,
                lat=float(centroid.y),
                lon=float(centroid.x),
            )
        )
    return tuple(out)


def neighbourhood_names(path: str | None = None) -> list[str]:
    return [n.name for n in load_neighbourhoods(path)]


def _by_name(path: str | None = None) -> dict[str, Neighbourhood]:
    return {n.name.lower(): n for n in load_neighbourhoods(path)}


def centroid_for_name(name: str, path: str | None = None) -> tuple[float, float] | None:
    hit = _by_name(path).get(_clean_name(name).lower())
    return (hit.lat, hit.lon) if hit else None


# ---------------------------------------------------------------------------
# Fuzzy fallback (used when the LLM is unreachable or returns nothing usable)
# ---------------------------------------------------------------------------


def _fuzzy_match(text: str, neighbourhoods: tuple[Neighbourhood, ...]) -> NeighbourhoodMatch | None:
    text_norm = re.sub(r"\s+", " ", text.lower()).strip()
    if not text_norm:
        return None
    text_tokens = set(re.findall(r"[a-z']+", text_norm))

    best: NeighbourhoodMatch | None = None
    best_score = 0.0
    for nb in neighbourhoods:
        name_norm = nb.name.lower()
        if name_norm and name_norm in text_norm:
            score = 0.95
        else:
            parts = [p for p in re.split(r"[^a-z']+", name_norm) if len(p) >= 4]
            strong = [p for p in parts if p not in _WEAK_TOKENS]
            token_hits = [p for p in strong if p in text_tokens]
            if token_hits and strong:
                score = 0.7 + 0.1 * (len(token_hits) / len(strong))
            else:
                # Only accept very close near-misses (speech-to-text typos), to
                # avoid spurious matches on unrelated words. The LLM resolver is
                # the primary semantic engine; this fuzzy path stays conservative.
                near = max(
                    (
                        SequenceMatcher(None, p, t).ratio()
                        for p in strong
                        if len(p) >= 5
                        for t in text_tokens
                        if len(t) >= 5
                    ),
                    default=0.0,
                )
                score = near if near >= 0.86 else 0.0
        if score > best_score:
            best_score = score
            best = NeighbourhoodMatch(
                name=nb.name,
                lat=nb.lat,
                lon=nb.lon,
                confidence=round(min(score, 1.0), 3),
                method="fuzzy",
            )

    if best is None or best.confidence < _FUZZY_THRESHOLD:
        return None
    return best


# ---------------------------------------------------------------------------
# LLM semantic match (existing Ollama harness, Workflow 1 / Nano profile)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_match_system_prompt() -> str:
    path = _REPO_ROOT / "agent" / "prompts" / "neighbourhood_match_system.txt"
    return path.read_text(encoding="utf-8").strip()


def _build_match_messages(text: str, names: list[str]) -> list[dict[str, str]]:
    candidates = "\n".join(f"{i + 1}. {name}" for i, name in enumerate(names))
    user = (
        "LOCATION TEXT:\n"
        f"{text.strip()}\n\n"
        "CANDIDATES:\n"
        f"{candidates}"
    )
    return [
        {"role": "system", "content": _load_match_system_prompt()},
        {"role": "user", "content": user},
    ]


async def _match_llm_async(
    text: str, neighbourhoods: tuple[Neighbourhood, ...]
) -> NeighbourhoodMatch | None:
    from agent.harness.client import chat as harness_chat

    names = [n.name for n in neighbourhoods]
    raw = await harness_chat(
        WorkflowProfile.WORKFLOW1,
        _build_match_messages(text, names),
        max_tokens=_LLM_MAX_TOKENS,
        temperature=_LLM_TEMPERATURE,
        json_mode=True,
    )
    data = parse_json_object(raw)
    chosen = data.get("neighbourhood")
    if not chosen:
        return None
    hit = _by_name()[chosen.lower()] if chosen.lower() in _by_name() else None
    if hit is None:
        logger.info("LLM returned off-list neighbourhood %r", chosen)
        return None
    try:
        confidence = float(data.get("confidence", 0.8))
    except (TypeError, ValueError):
        confidence = 0.8
    return NeighbourhoodMatch(
        name=hit.name,
        lat=hit.lat,
        lon=hit.lon,
        confidence=round(min(max(confidence, 0.0), 1.0), 3),
        method="llm",
    )


def resolve_neighbourhood(
    text: str,
    *,
    use_llm: bool = True,
    path: str | None = None,
) -> NeighbourhoodMatch | None:
    """Resolve free-text location to a neighbourhood centroid.

    Tries the LLM (semantic) first, then falls back to fuzzy name matching. Returns
    ``None`` when no Toronto neighbourhood can be confidently identified.
    """
    neighbourhoods = load_neighbourhoods(path)
    if not neighbourhoods or not (text or "").strip():
        return None

    if use_llm:
        try:
            match = asyncio.run(_match_llm_async(text, neighbourhoods))
            if match is not None:
                return match
        except RuntimeError as exc:
            # Already inside an event loop (rare in Streamlit/sync callers).
            logger.info("Skipping LLM neighbourhood match (event loop active): %s", exc)
        except Exception as exc:
            logger.warning("LLM neighbourhood match failed, using fuzzy fallback: %s", exc)

    return _fuzzy_match(text, neighbourhoods)
