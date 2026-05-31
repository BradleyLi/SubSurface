"""Harness health checks (mocked HTTP)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.harness.endpoints import WorkflowProfile
from agent.harness.health import check_profile


@pytest.mark.asyncio
async def test_check_profile_ok_when_model_listed():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "data": [{"id": "nemotron-nano:12b-v2"}],
    }

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("agent.harness.health.httpx.AsyncClient", return_value=mock_client):
        result = await check_profile(WorkflowProfile.WORKFLOW1)

    assert result.profile is WorkflowProfile.WORKFLOW1
    assert result.ok is True


@pytest.mark.asyncio
async def test_check_profile_fails_on_http_error():
    mock_client = AsyncMock()
    import httpx

    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("agent.harness.health.httpx.AsyncClient", return_value=mock_client):
        result = await check_profile(WorkflowProfile.WORKFLOW1)

    assert result.ok is False
    assert "connection refused" in result.detail
