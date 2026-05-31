"""Tests for voice transcript → pipe matching."""

from __future__ import annotations

import pandas as pd

from agent.neighbourhoods import NeighbourhoodMatch
from agent.voice_pipe_match import match_transcript_to_pipe


def _sample_transcript_payload() -> dict:
    return {
        "session_id": "test-session",
        "incident": {
            "location": {
                "type": "intersection",
                "address": "Yonge Street & Bloor Street, Toronto, ON",
                "streets": ["Yonge Street", "Bloor Street"],
                "lat": 43.6708,
                "lon": -79.3868,
            }
        },
        "transcript": [
            {
                "role": "user",
                "content": "I see flooding near Yonge and Bloor",
            },
            {
                "role": "assistant",
                "content": "No injuries at Bloor-Yonge intersection.",
            },
        ],
    }


def test_match_transcript_yonge_bloor_street():
    df = pd.DataFrame(
        [
            {
                "pipe_id": "WM-OTHER",
                "street": "Queen Street West",
                "lat": 43.65,
                "lon": -79.40,
            },
            {
                "pipe_id": "WM-YONGE-BLOOR",
                "street": "Yonge Street & Bloor Street watermain",
                "lat": 43.6708,
                "lon": -79.3868,
            },
        ]
    )
    payload = _sample_transcript_payload()
    match = match_transcript_to_pipe(payload, df)
    assert match is not None
    assert match.pipe_id == "WM-YONGE-BLOOR"
    assert match.confidence >= 0.5


def test_match_transcript_geo_when_street_empty():
    df = pd.DataFrame(
        [
            {
                "pipe_id": "WM-NEAR",
                "street": "",
                "lat": 43.6710,
                "lon": -79.3870,
            },
            {
                "pipe_id": "WM-FAR",
                "street": "",
                "lat": 43.80,
                "lon": -79.50,
            },
        ]
    )
    payload = _sample_transcript_payload()
    match = match_transcript_to_pipe(payload, df)
    assert match is not None
    assert match.pipe_id == "WM-NEAR"
    assert match.method in ("geo", "street+geo")


def _neighbourhood_only_payload() -> dict:
    return {
        "session_id": "test-neighbourhood",
        "incident": {"location": None},
        "transcript": [
            {"role": "user", "content": "There is a water main break over in Leaside"},
        ],
    }


def test_match_via_neighbourhood_centroid_to_nearest_pipe():
    # No street intersection in the call, so geo coords come from the resolved
    # neighbourhood centroid; the nearest watermain should win.
    leaside_lat, leaside_lon = 43.7045, -79.3666
    df = pd.DataFrame(
        [
            {"pipe_id": "WM-NEAR", "street": "", "lat": 43.7050, "lon": -79.3670},
            {"pipe_id": "WM-FAR", "street": "", "lat": 43.6000, "lon": -79.5500},
        ]
    )

    def fake_resolver(_text: str) -> NeighbourhoodMatch:
        return NeighbourhoodMatch(
            name="Leaside",
            lat=leaside_lat,
            lon=leaside_lon,
            confidence=0.9,
            method="llm",
        )

    payload = _neighbourhood_only_payload()
    match = match_transcript_to_pipe(payload, df, neighbourhood_resolver=fake_resolver)
    assert match is not None
    assert match.pipe_id == "WM-NEAR"
    assert match.method == "neighbourhood"
    assert match.matched_neighbourhood == "Leaside"
    assert match.lat == leaside_lat and match.lon == leaside_lon


def test_no_match_when_no_geo_and_no_neighbourhood():
    df = pd.DataFrame(
        [{"pipe_id": "WM-X", "street": "", "lat": 43.70, "lon": -79.40}]
    )
    payload = _neighbourhood_only_payload()
    match = match_transcript_to_pipe(
        payload, df, neighbourhood_resolver=lambda _t: None
    )
    assert match is None
