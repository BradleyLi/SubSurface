"""Tests for voice transcript → pipe matching."""

from __future__ import annotations

import pandas as pd

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
