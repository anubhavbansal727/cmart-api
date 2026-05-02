from __future__ import annotations

import asyncio
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from cmart.main import app as _app

# ---------------------------------------------------------------------------
# Event loop
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Session-scoped event loop shared by all async tests."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def app() -> object:
    """Return the FastAPI application instance."""
    return _app


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client(app: object) -> AsyncGenerator[AsyncClient, None]:  # type: ignore[type-arg]
    """AsyncClient backed by the ASGI transport — no real server needed."""
    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://testserver",
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# LLM mock
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_llm(mocker: MagicMock) -> MagicMock:
    """Patch the LLM service used inside the pipeline.

    TODO: Update the patch target to the real import path once the pipeline
    service module is created (e.g. 'cmart.services.llm.GeminiClient').
    """
    mock = mocker.patch(
        "cmart.services.llm.GeminiClient",
        autospec=True,
    )
    instance = mock.return_value
    instance.ainvoke = AsyncMock(return_value="mocked LLM response")
    return instance


# ---------------------------------------------------------------------------
# Pinecone mock
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_pinecone(mocker: MagicMock) -> MagicMock:
    """Patch the Pinecone client used inside the pipeline.

    TODO: Update the patch target to the real import path once the vector
    store service module is created (e.g. 'cmart.services.vector_store.PineconeStore').
    """
    mock = mocker.patch(
        "cmart.services.vector_store.PineconeStore",
        autospec=True,
    )
    instance = mock.return_value
    instance.query = AsyncMock(return_value=[])
    instance.upsert = AsyncMock(return_value=None)
    return instance
