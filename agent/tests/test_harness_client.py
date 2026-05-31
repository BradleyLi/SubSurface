"""Tests for shared harness HTTP client lifecycle."""

from __future__ import annotations

import asyncio

from agent.harness import client as harness_client


class DummyAsyncClient:
    def __init__(self, *args, **kwargs):
        self.is_closed = False


async def _client_for_current_loop():
    return harness_client._get_shared_client()


def test_shared_client_is_scoped_to_running_event_loop(monkeypatch):
    created: list[DummyAsyncClient] = []

    def make_client(*args, **kwargs):
        _ = args, kwargs
        client = DummyAsyncClient()
        created.append(client)
        return client

    harness_client._shared_clients.clear()
    monkeypatch.setattr(harness_client.httpx, "AsyncClient", make_client)

    first = asyncio.run(_client_for_current_loop())
    second = asyncio.run(_client_for_current_loop())

    assert first is created[0]
    assert second is created[1]
    assert first is not second


def test_shared_client_reused_within_running_event_loop(monkeypatch):
    created: list[DummyAsyncClient] = []

    def make_client(*args, **kwargs):
        _ = args, kwargs
        client = DummyAsyncClient()
        created.append(client)
        return client

    async def get_twice():
        return harness_client._get_shared_client(), harness_client._get_shared_client()

    harness_client._shared_clients.clear()
    monkeypatch.setattr(harness_client.httpx, "AsyncClient", make_client)

    first, second = asyncio.run(get_twice())

    assert first is second
    assert created == [first]
