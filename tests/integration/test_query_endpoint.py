"""Integration tests for POST /query.

These tests run against the full ASGI stack (no real DB or Redis required)
and assert the expected HTTP contract at each phase of implementation.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_query_returns_501_until_implemented(client: AsyncClient) -> None:
    """POST /query must return HTTP 501 while the route is a stub.

    Once the pipeline is wired up this test should be replaced with a
    proper happy-path test that asserts a 200 response with a QueryResponse
    body.
    """
    response = await client.post("/query", json={"query": "What is CMART?"})
    assert response.status_code == 501
    body = response.json()
    assert body["status_code"] == 501
    assert "error" in body
