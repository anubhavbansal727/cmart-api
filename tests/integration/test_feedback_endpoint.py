"""Integration tests for POST /feedback.

Auth and DB are mocked; repository functions are patched per test.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from cmart.main import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_ACCOUNT_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
_FAKE_QUERY_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
_FAKE_FEEDBACK_ID = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")


def _make_account() -> MagicMock:
    account = MagicMock()
    account.id = _FAKE_ACCOUNT_ID
    return account


def _make_query_log(account_id: uuid.UUID = _FAKE_ACCOUNT_ID) -> MagicMock:
    log = MagicMock()
    log.id = _FAKE_QUERY_ID
    log.account_id = account_id
    return log


def _make_feedback() -> MagicMock:
    feedback = MagicMock()
    feedback.id = _FAKE_FEEDBACK_ID
    feedback.query_id = _FAKE_QUERY_ID
    feedback.created_at = datetime(2026, 5, 5, 12, 0, 0, tzinfo=timezone.utc)
    return feedback


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def feedback_client(mocker: MagicMock) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient with auth and DB dependencies mocked."""
    from cmart.api.dependencies import get_current_account, get_db

    mock_db = AsyncMock()

    async def _override_account() -> MagicMock:
        return _make_account()

    async def _override_db() -> AsyncGenerator:
        yield mock_db

    app.dependency_overrides[get_current_account] = _override_account
    app.dependency_overrides[get_db] = _override_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac

    app.dependency_overrides.pop(get_current_account, None)
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_feedback_happy_path_returns_201(
    feedback_client: AsyncClient, mocker: MagicMock
) -> None:
    mocker.patch(
        "cmart.api.routes.feedback.get_by_id",
        new=AsyncMock(return_value=_make_query_log()),
    )
    mocker.patch(
        "cmart.api.routes.feedback.insert_feedback",
        new=AsyncMock(return_value=_make_feedback()),
    )

    response = await feedback_client.post(
        "/feedback",
        json={
            "query_id": str(_FAKE_QUERY_ID),
            "rating": "correct",
            "note": "Accurate and well cited.",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == str(_FAKE_FEEDBACK_ID)
    assert body["query_id"] == str(_FAKE_QUERY_ID)
    assert body["rating"] == "correct"


@pytest.mark.asyncio
async def test_feedback_with_partial_rating(
    feedback_client: AsyncClient, mocker: MagicMock
) -> None:
    mocker.patch(
        "cmart.api.routes.feedback.get_by_id",
        new=AsyncMock(return_value=_make_query_log()),
    )
    mocker.patch(
        "cmart.api.routes.feedback.insert_feedback",
        new=AsyncMock(return_value=_make_feedback()),
    )

    response = await feedback_client.post(
        "/feedback",
        json={"query_id": str(_FAKE_QUERY_ID), "rating": "partial"},
    )

    assert response.status_code == 201


@pytest.mark.asyncio
async def test_feedback_query_not_found_returns_404(
    feedback_client: AsyncClient, mocker: MagicMock
) -> None:
    mocker.patch(
        "cmart.api.routes.feedback.get_by_id",
        new=AsyncMock(return_value=None),
    )

    response = await feedback_client.post(
        "/feedback",
        json={"query_id": str(_FAKE_QUERY_ID), "rating": "incorrect"},
    )

    assert response.status_code == 404
    assert "error" in response.json()


@pytest.mark.asyncio
async def test_feedback_wrong_account_returns_404(
    feedback_client: AsyncClient, mocker: MagicMock
) -> None:
    other_account_id = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    mocker.patch(
        "cmart.api.routes.feedback.get_by_id",
        new=AsyncMock(return_value=_make_query_log(account_id=other_account_id)),
    )

    response = await feedback_client.post(
        "/feedback",
        json={"query_id": str(_FAKE_QUERY_ID), "rating": "correct"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_feedback_missing_required_fields_returns_422(
    feedback_client: AsyncClient,
) -> None:
    response = await feedback_client.post(
        "/feedback",
        json={"note": "missing query_id and rating"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_feedback_invalid_rating_returns_422(
    feedback_client: AsyncClient,
) -> None:
    response = await feedback_client.post(
        "/feedback",
        json={"query_id": str(_FAKE_QUERY_ID), "rating": "unknown_value"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_feedback_without_auth_returns_401() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        response = await ac.post(
            "/feedback",
            json={"query_id": str(_FAKE_QUERY_ID), "rating": "correct"},
        )
    assert response.status_code == 401
