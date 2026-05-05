"""Unit tests for Stage 5 — Validation (GC + SA signals)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from cmart.pipeline import stage5_validation
from cmart.schemas.pipeline import (
    AgreementResult,
    GCSignal,
    GenerationResult,
    GroundingResult,
    PipelineContext,
    RetrievalResult,
    RetrievedDoc,
    RSSignal,
    SASignal,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _doc(doc_id: str, chunk_id: str, content: str, title: str = "Doc") -> RetrievedDoc:
    return RetrievedDoc(chunk_id=chunk_id, doc_id=doc_id, content=content, score=0.70, title=title)


def _ctx(docs: list[RetrievedDoc]) -> PipelineContext:
    ctx = PipelineContext(query="test query", user_id="u1", account_id="acc1")
    ctx.retrieval = RetrievalResult(docs=docs, rs_signal=RSSignal.STRONG, top_score=0.70)
    ctx.generation = GenerationResult(answer="Test answer.")
    return ctx


def _mock_gemini(mocker: MagicMock, gc: GCSignal, sa: SASignal) -> None:
    async def _dispatch(prompt: str, schema: type) -> object:
        if schema is GroundingResult:
            return GroundingResult(gc=gc)
        return AgreementResult(sa=sa)

    mock_client = MagicMock(invoke_structured=AsyncMock(side_effect=_dispatch))
    mocker.patch("cmart.pipeline.stage5_validation.GeminiClient", return_value=mock_client)


# ---------------------------------------------------------------------------
# Signal paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fully_supported_agrees(mocker: MagicMock) -> None:
    _mock_gemini(mocker, GCSignal.FULLY_SUPPORTED, SASignal.AGREES)
    result = await stage5_validation.run(_ctx([_doc("d1", "c1", "content")]))
    assert result.validation is not None
    assert result.validation.gc == GCSignal.FULLY_SUPPORTED
    assert result.validation.sa == SASignal.AGREES


@pytest.mark.asyncio
async def test_partially_supported_partial(mocker: MagicMock) -> None:
    _mock_gemini(mocker, GCSignal.PARTIALLY_SUPPORTED, SASignal.PARTIAL)
    result = await stage5_validation.run(_ctx([_doc("d1", "c1", "content")]))
    assert result.validation is not None
    assert result.validation.gc == GCSignal.PARTIALLY_SUPPORTED
    assert result.validation.sa == SASignal.PARTIAL


@pytest.mark.asyncio
async def test_not_supported_conflict(mocker: MagicMock) -> None:
    _mock_gemini(mocker, GCSignal.NOT_SUPPORTED, SASignal.CONFLICT)
    result = await stage5_validation.run(_ctx([_doc("d1", "c1", "content")]))
    assert result.validation is not None
    assert result.validation.gc == GCSignal.NOT_SUPPORTED
    assert result.validation.sa == SASignal.CONFLICT


# ---------------------------------------------------------------------------
# Failure safe-defaults
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gc_failure_defaults_to_not_supported(mocker: MagicMock) -> None:
    async def _dispatch(prompt: str, schema: type) -> object:
        if schema is GroundingResult:
            raise Exception("LLM timeout")
        return AgreementResult(sa=SASignal.AGREES)

    mock_client = MagicMock(invoke_structured=AsyncMock(side_effect=_dispatch))
    mocker.patch("cmart.pipeline.stage5_validation.GeminiClient", return_value=mock_client)

    result = await stage5_validation.run(_ctx([_doc("d1", "c1", "content")]))
    assert result.validation is not None
    assert result.validation.gc == GCSignal.NOT_SUPPORTED


@pytest.mark.asyncio
async def test_sa_failure_defaults_to_conflict(mocker: MagicMock) -> None:
    async def _dispatch(prompt: str, schema: type) -> object:
        if schema is GroundingResult:
            return GroundingResult(gc=GCSignal.FULLY_SUPPORTED)
        raise Exception("LLM timeout")

    mock_client = MagicMock(invoke_structured=AsyncMock(side_effect=_dispatch))
    mocker.patch("cmart.pipeline.stage5_validation.GeminiClient", return_value=mock_client)

    result = await stage5_validation.run(_ctx([_doc("d1", "c1", "content")]))
    assert result.validation is not None
    assert result.validation.sa == SASignal.CONFLICT


@pytest.mark.asyncio
async def test_both_fail_use_safe_defaults(mocker: MagicMock) -> None:
    mock_client = MagicMock(invoke_structured=AsyncMock(side_effect=Exception("LLM down")))
    mocker.patch("cmart.pipeline.stage5_validation.GeminiClient", return_value=mock_client)

    result = await stage5_validation.run(_ctx([_doc("d1", "c1", "content")]))
    assert result.validation is not None
    assert result.validation.gc == GCSignal.NOT_SUPPORTED
    assert result.validation.sa == SASignal.CONFLICT


# ---------------------------------------------------------------------------
# _format_context — pure function tests
# ---------------------------------------------------------------------------


def test_format_context_no_retrieval() -> None:
    ctx = PipelineContext(query="test", user_id="u1", account_id="acc1")
    assert stage5_validation._format_context(ctx) == "No context available."


def test_format_context_empty_docs() -> None:
    ctx = PipelineContext(query="test", user_id="u1", account_id="acc1")
    ctx.retrieval = RetrievalResult(docs=[], rs_signal=RSSignal.WEAK, top_score=0.0)
    assert stage5_validation._format_context(ctx) == "No context available."


def test_format_context_multiple_docs() -> None:
    ctx = PipelineContext(query="test", user_id="u1", account_id="acc1")
    ctx.retrieval = RetrievalResult(
        docs=[
            _doc("doc_001", "c1", "Content A", title="Doc A"),
            _doc("doc_002", "c2", "Content B", title="Doc B"),
        ],
        rs_signal=RSSignal.STRONG,
        top_score=0.70,
    )
    result = stage5_validation._format_context(ctx)
    assert "[1]" in result and "[2]" in result
    assert "Doc A" in result and "Doc B" in result


def test_format_context_merges_same_doc_chunks() -> None:
    """Two chunks from the same doc appear as a single numbered source entry."""
    ctx = PipelineContext(query="test", user_id="u1", account_id="acc1")
    ctx.retrieval = RetrievalResult(
        docs=[
            _doc("doc_001", "c1", "First chunk.", title="Security Guide"),
            _doc("doc_001", "c2", "Second chunk.", title="Security Guide"),
        ],
        rs_signal=RSSignal.STRONG,
        top_score=0.70,
    )
    result = stage5_validation._format_context(ctx)
    assert "[1]" in result
    assert "[2]" not in result
    assert "First chunk." in result
    assert "Second chunk." in result


@pytest.mark.asyncio
async def test_chunks_grouped_in_llm_prompt(mocker: MagicMock) -> None:
    """Verify the SA validator sees only one source entry for same-doc chunks."""
    captured: list[str] = []

    async def _dispatch(prompt: str, schema: type) -> object:
        captured.append(prompt)
        if schema is GroundingResult:
            return GroundingResult(gc=GCSignal.FULLY_SUPPORTED)
        return AgreementResult(sa=SASignal.AGREES)

    mock_client = MagicMock(invoke_structured=AsyncMock(side_effect=_dispatch))
    mocker.patch("cmart.pipeline.stage5_validation.GeminiClient", return_value=mock_client)

    docs = [
        _doc("doc_001", "chunk_a", "Passwords must be 8 chars.", title="Security Guide"),
        _doc("doc_001", "chunk_b", "Passwords must include a number.", title="Security Guide"),
    ]
    await stage5_validation.run(_ctx(docs))

    for prompt in captured:
        if "[1]" in prompt:
            assert "[2]" not in prompt, "Same-doc chunks must be merged into one source"
