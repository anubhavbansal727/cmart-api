"""Unit tests for SessionStore (Redis-backed clarification session state)."""
from __future__ import annotations

import json
from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock

import pytest

from cmart.services.session_store import SessionState, SessionStore

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store(mocker: MagicMock) -> tuple[SessionStore, MagicMock]:
    mock_settings = MagicMock(session_ttl_seconds=1800)
    mocker.patch("cmart.services.session_store.get_settings", return_value=mock_settings)

    mock_redis = MagicMock()
    mock_redis.setex = AsyncMock(return_value=True)
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.delete = AsyncMock(return_value=1)

    return SessionStore(mock_redis), mock_redis


def _serialized(state: SessionState) -> str:
    return json.dumps(asdict(state))


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_returns_session_with_uuid(store: tuple[SessionStore, MagicMock]) -> None:
    session_store, _ = store
    state = await session_store.create(
        account_id="acc1", user_id="u1", original_query="test query"
    )
    assert state.session_id
    assert len(state.session_id) == 36  # UUID format
    assert state.account_id == "acc1"
    assert state.user_id == "u1"
    assert state.original_query == "test query"
    assert state.clarify_rounds == 0


@pytest.mark.asyncio
async def test_create_stores_json_with_ttl(store: tuple[SessionStore, MagicMock]) -> None:
    session_store, mock_redis = store
    state = await session_store.create(
        account_id="acc1", user_id="u1", original_query="test query"
    )
    mock_redis.setex.assert_awaited_once()
    key, ttl, value = mock_redis.setex.call_args[0]
    assert key == f"session:{state.session_id}"
    assert ttl == 1800
    stored = json.loads(value)
    assert stored["original_query"] == "test query"
    assert stored["clarify_rounds"] == 0


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_returns_session_state(store: tuple[SessionStore, MagicMock]) -> None:
    session_store, mock_redis = store
    state = SessionState(
        session_id="sess-123",
        account_id="acc1",
        user_id="u1",
        original_query="test",
        clarify_rounds=1,
    )
    mock_redis.get = AsyncMock(return_value=_serialized(state))
    result = await session_store.get("sess-123")
    assert result is not None
    assert result.session_id == "sess-123"
    assert result.clarify_rounds == 1
    mock_redis.get.assert_awaited_once_with("session:sess-123")


@pytest.mark.asyncio
async def test_get_returns_none_for_missing_key(store: tuple[SessionStore, MagicMock]) -> None:
    session_store, mock_redis = store
    mock_redis.get = AsyncMock(return_value=None)
    result = await session_store.get("nonexistent")
    assert result is None


# ---------------------------------------------------------------------------
# increment_round
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_increment_round_increments_and_returns_count(
    store: tuple[SessionStore, MagicMock]
) -> None:
    session_store, mock_redis = store
    initial = SessionState(
        session_id="sess-abc",
        account_id="acc1",
        user_id="u1",
        original_query="test",
        clarify_rounds=0,
    )
    mock_redis.get = AsyncMock(return_value=_serialized(initial))
    count = await session_store.increment_round("sess-abc")
    assert count == 1
    mock_redis.setex.assert_awaited()


@pytest.mark.asyncio
async def test_increment_round_sequential_counts(
    store: tuple[SessionStore, MagicMock]
) -> None:
    session_store, mock_redis = store
    state = SessionState(
        session_id="sess-abc",
        account_id="acc1",
        user_id="u1",
        original_query="test",
        clarify_rounds=1,
    )
    mock_redis.get = AsyncMock(return_value=_serialized(state))
    count = await session_store.increment_round("sess-abc")
    assert count == 2


@pytest.mark.asyncio
async def test_increment_round_returns_zero_for_missing(
    store: tuple[SessionStore, MagicMock]
) -> None:
    session_store, mock_redis = store
    mock_redis.get = AsyncMock(return_value=None)
    count = await session_store.increment_round("nonexistent")
    assert count == 0
    mock_redis.setex.assert_not_awaited()


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_removes_correct_key(store: tuple[SessionStore, MagicMock]) -> None:
    session_store, mock_redis = store
    await session_store.delete("sess-xyz")
    mock_redis.delete.assert_awaited_once_with("session:sess-xyz")
