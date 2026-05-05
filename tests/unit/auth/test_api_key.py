"""Unit tests for API key authentication."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from cmart.auth.api_key import authenticate
from cmart.utils.errors import AuthError


def _make_request(authorization: str | None) -> MagicMock:
    request = MagicMock()
    headers: dict[str, str] = {}
    if authorization is not None:
        headers["Authorization"] = authorization
    request.headers = headers
    return request


def _make_db() -> MagicMock:
    return MagicMock()


# ---------------------------------------------------------------------------
# Header validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_header_raises_auth_error() -> None:
    with pytest.raises(AuthError, match="missing"):
        await authenticate(_make_request(None), _make_db())


@pytest.mark.asyncio
async def test_non_bearer_scheme_raises_auth_error() -> None:
    with pytest.raises(AuthError, match="Bearer"):
        await authenticate(_make_request("Token abc123"), _make_db())


@pytest.mark.asyncio
async def test_malformed_header_no_space_raises_auth_error() -> None:
    """'Bearer' with no space has no key part — not a valid Bearer header."""
    with pytest.raises(AuthError):
        await authenticate(_make_request("Bearer"), _make_db())


@pytest.mark.asyncio
async def test_empty_key_raises_auth_error() -> None:
    with pytest.raises(AuthError, match="empty"):
        await authenticate(_make_request("Bearer "), _make_db())


# ---------------------------------------------------------------------------
# DB lookup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_key_raises_auth_error(mocker: MagicMock) -> None:
    mocker.patch("cmart.auth.api_key.get_by_api_key", new=AsyncMock(return_value=None))
    with pytest.raises(AuthError, match="Invalid"):
        await authenticate(_make_request("Bearer sk-unknown"), _make_db())


@pytest.mark.asyncio
async def test_valid_key_returns_account(mocker: MagicMock) -> None:
    mock_account = MagicMock()
    mock_account.api_key = "sk-valid-key-abc123"
    mocker.patch("cmart.auth.api_key.get_by_api_key", new=AsyncMock(return_value=mock_account))
    result = await authenticate(_make_request("Bearer sk-valid-key-abc123"), _make_db())
    assert result is mock_account


@pytest.mark.asyncio
async def test_key_with_surrounding_whitespace_is_stripped(mocker: MagicMock) -> None:
    """Leading/trailing spaces around the key should be stripped before lookup."""
    mock_account = MagicMock()
    mock_account.api_key = "sk-valid-key"
    mocker.patch("cmart.auth.api_key.get_by_api_key", new=AsyncMock(return_value=mock_account))
    result = await authenticate(_make_request("Bearer  sk-valid-key "), _make_db())
    assert result is mock_account
