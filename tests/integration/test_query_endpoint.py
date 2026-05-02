"""Integration tests for POST /query.

All external I/O (pipeline LLM calls, Pinecone, Redis) is mocked so these
tests run without any real infrastructure beyond what conftest provides.
"""

from __future__ import annotations

import uuid
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from cmart.main import app
from cmart.schemas.pipeline import (
    DecisionResult,
    PipelineContext,
    RetrievalResult,
    RSSignal,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_ACCOUNT_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def _make_account() -> MagicMock:
    account = MagicMock()
    account.id = _FAKE_ACCOUNT_ID
    account.name = "Test Account"
    account.is_active = True
    return account


def _make_ctx(decision: str, reason: str) -> PipelineContext:
    ctx = PipelineContext(
        query="How do I reset my password?",
        user_id="u1",
        account_id=str(_FAKE_ACCOUNT_ID),
    )
    ctx.retrieval = RetrievalResult(docs=[], rs_signal=RSSignal.WEAK, top_score=0.0)
    ctx.decision_result = DecisionResult(decision=decision, reason=reason)
    if decision == "escalate":
        ctx.escalation_context = {
            "reason": reason,
            "signals": {"rs": "WEAK", "qc": None, "gc": None, "sa": None},
            "query": ctx.query,
            "answer_attempt": None,
            "retrieved_docs": [],
        }
    return ctx


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def query_client(mocker: MagicMock) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient with auth, Redis, and background logging mocked."""
    from cmart.api.dependencies import get_current_account, get_redis

    # Mock Redis so the rate limiter doesn't crash (incr always returns 1)
    mock_redis = MagicMock()
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock(return_value=True)

    async def _override_account() -> MagicMock:
        return _make_account()

    async def _override_redis() -> MagicMock:
        return mock_redis

    app.dependency_overrides[get_current_account] = _override_account
    app.dependency_overrides[get_redis] = _override_redis

    # Suppress background DB write — no real DB in unit-style integration tests
    mocker.patch("cmart.api.routes.query._log_query", new=AsyncMock(return_value=None))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unauthenticated_request_returns_401(client: AsyncClient) -> None:
    """Requests without an Authorization header must be rejected."""
    response = await client.post(
        "/query",
        json={"query": "How do I reset my password?", "user_id": "u1", "account_id": "acc1"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_missing_query_field_returns_422(query_client: AsyncClient) -> None:
    """Request body missing the required 'query' field must return 422."""
    response = await query_client.post("/query", json={"user_id": "u1"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_query_escalate_decision(
    query_client: AsyncClient, mocker: MagicMock
) -> None:
    """Pipeline returning ESCALATE should yield a 200 with escalation_context."""
    mocker.patch(
        "cmart.api.routes.query.run_pipeline",
        new=AsyncMock(return_value=_make_ctx("escalate", "LOW_RETRIEVAL")),
    )
    response = await query_client.post(
        "/query",
        json={"query": "How do I reset my password?", "user_id": "u1", "account_id": "acc1"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "escalate"
    assert body["reason"] == "LOW_RETRIEVAL"
    assert body["escalation_context"] is not None


@pytest.mark.asyncio
async def test_query_answer_decision(
    query_client: AsyncClient, mocker: MagicMock
) -> None:
    """Pipeline returning ANSWER should yield a 200 with an answer field."""
    from cmart.schemas.pipeline import AnalysisResult, GenerationResult, QCSignal

    ctx = _make_ctx("answer", "HIGH_CONFIDENCE")
    ctx.generation = GenerationResult(answer="Reset via Settings > Security.")
    ctx.analysis = AnalysisResult(qc=QCSignal.CLEAR)
    ctx.decision_result = DecisionResult(decision="answer", reason="HIGH_CONFIDENCE")

    mocker.patch(
        "cmart.api.routes.query.run_pipeline",
        new=AsyncMock(return_value=ctx),
    )
    response = await query_client.post(
        "/query",
        json={"query": "How do I reset my password?", "user_id": "u1", "account_id": "acc1"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "answer"
    assert body["answer"] == "Reset via Settings > Security."
    assert body["reason"] == "HIGH_CONFIDENCE"


@pytest.mark.asyncio
async def test_query_clarify_decision(
    query_client: AsyncClient, mocker: MagicMock
) -> None:
    """Pipeline returning CLARIFY should yield a 200 with clarification_question."""
    from cmart.schemas.pipeline import AnalysisResult, QCSignal

    ctx = _make_ctx("clarify", "DEFAULT_SAFE")
    ctx.analysis = AnalysisResult(
        qc=QCSignal.AMBIGUOUS,
        clarification_question="Which product area are you asking about?",
    )
    ctx.decision_result = DecisionResult(decision="clarify", reason="DEFAULT_SAFE")
    ctx.session_id = "sess-abc123"

    mocker.patch(
        "cmart.api.routes.query.run_pipeline",
        new=AsyncMock(return_value=ctx),
    )
    response = await query_client.post(
        "/query",
        json={"query": "Something is broken", "user_id": "u1", "account_id": "acc1"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "clarify"
    assert body["clarification_question"] == "Which product area are you asking about?"
    assert body["session_id"] == "sess-abc123"
