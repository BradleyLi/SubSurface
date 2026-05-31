"""Tests for Workflow 1 UI helpers (no Streamlit runtime)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from frontend.nav import w1_session_key
from frontend.workflow1_ui import (
    _fetch_w1_payload,
    _template_payload,
    ensure_w1_summaries,
)


def test_w1_session_key_format():
    assert w1_session_key("WM-001") == "w1_summary_WM-001"


def test_template_payload_has_pending_flag():
    row = pd.Series(
        {
            "pipe_id": "WM-TEST",
            "risk_score": 70.0,
            "risk_level": "High",
            "material": "Cast Iron",
            "age": 80,
            "tree_count_5m": 2,
            "complaints_12mo": 0,
            "break_count_10yr": 1,
            "years_since_resurfacing": 10,
            "lead_exceedance_pct": 0.0,
            "utility_cuts_18mo": 0,
        }
    )
    payload = _template_payload(row, df=None)
    assert payload["source"] == "template"
    assert payload["pending_nemotron"] is True
    assert payload["summary"]["pipe_id"] == "WM-TEST"


@patch("frontend.workflow1_ui.get_risk_summary_api")
def test_fetch_w1_payload_success(mock_api):
    mock_api.return_value = {
        "summary": {"headline": "Test", "pipe_id": "WM-001"},
        "source": "nemotron",
    }
    out = _fetch_w1_payload("WM-001", use_real=False)
    assert out["source"] == "nemotron"
    assert out["use_real"] is False


@patch("frontend.workflow1_ui.get_risk_summary_api")
def test_ensure_w1_summaries_skips_cached(mock_api):
    state: dict = {
        w1_session_key("WM-001"): {"use_real": False, "source": "nemotron", "summary": {}},
    }
    result = ensure_w1_summaries(
        ["WM-001"],
        use_real=False,
        session_state=state,
        show_spinner=False,
    )
    assert result == []
    mock_api.assert_not_called()


@patch("frontend.workflow1_ui.get_risk_summary_api")
def test_ensure_w1_summaries_fetches_missing(mock_api):
    mock_api.return_value = {"summary": {"pipe_id": "WM-002"}, "source": "nemotron"}
    state: dict = {}
    with patch("frontend.workflow1_ui.st") as mock_st:
        mock_st.spinner = MagicMock(return_value=MagicMock(__enter__=lambda s: s, __exit__=lambda *a: None))
        result = ensure_w1_summaries(
            ["WM-002"],
            use_real=False,
            session_state=state,
            show_spinner=False,
        )
    assert result == ["WM-002"]
    assert state[w1_session_key("WM-002")]["source"] == "nemotron"
    mock_api.assert_called_once()
