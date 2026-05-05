"""Unit tests for Stage 3 — Retrieval."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from cmart.pipeline import stage3_retrieval
from cmart.schemas.pipeline import PipelineContext, RSSignal


def _ctx() -> PipelineContext:
    return PipelineContext(query="test query", user_id="u1", account_id="acc1")


def _raw_result(score: float) -> dict:
    return {
        "id": "chunk_001",
        "score": score,
        "metadata": {
            "doc_id": "doc_001",
            "content": "Some content",
            "title": "Test Doc",
            "source_url": None,
        },
    }


def _patch_clients(mocker: MagicMock, score: float | None) -> None:
    mock_embed = MagicMock(embed=AsyncMock(return_value=[0.1] * 1536))
    mocker.patch("cmart.pipeline.stage3_retrieval.OpenAIEmbeddingClient", return_value=mock_embed)

    results = [_raw_result(score)] if score is not None else []
    mock_vec = MagicMock(query=AsyncMock(return_value=results))
    mocker.patch("cmart.pipeline.stage3_retrieval.PineconeVectorStoreClient", return_value=mock_vec)

    mock_settings = MagicMock(rs_strong_threshold=0.60, rs_moderate_threshold=0.45)
    mocker.patch("cmart.pipeline.stage3_retrieval.get_settings", return_value=mock_settings)


@pytest.mark.asyncio
async def test_strong_retrieval(mocker: MagicMock) -> None:
    _patch_clients(mocker, score=0.65)
    ctx = await stage3_retrieval.run(_ctx())
    assert ctx.retrieval is not None
    assert ctx.retrieval.rs_signal == RSSignal.STRONG
    assert ctx.retrieval.retrieval_failed is False


@pytest.mark.asyncio
async def test_strong_threshold_boundary(mocker: MagicMock) -> None:
    """Score exactly at RS_STRONG_THRESHOLD qualifies as STRONG."""
    _patch_clients(mocker, score=0.60)
    ctx = await stage3_retrieval.run(_ctx())
    assert ctx.retrieval is not None
    assert ctx.retrieval.rs_signal == RSSignal.STRONG


@pytest.mark.asyncio
async def test_moderate_retrieval(mocker: MagicMock) -> None:
    _patch_clients(mocker, score=0.52)
    ctx = await stage3_retrieval.run(_ctx())
    assert ctx.retrieval is not None
    assert ctx.retrieval.rs_signal == RSSignal.MODERATE


@pytest.mark.asyncio
async def test_moderate_threshold_boundary(mocker: MagicMock) -> None:
    """Score exactly at RS_MODERATE_THRESHOLD qualifies as MODERATE."""
    _patch_clients(mocker, score=0.45)
    ctx = await stage3_retrieval.run(_ctx())
    assert ctx.retrieval is not None
    assert ctx.retrieval.rs_signal == RSSignal.MODERATE


@pytest.mark.asyncio
async def test_weak_retrieval(mocker: MagicMock) -> None:
    _patch_clients(mocker, score=0.30)
    ctx = await stage3_retrieval.run(_ctx())
    assert ctx.retrieval is not None
    assert ctx.retrieval.rs_signal == RSSignal.WEAK


@pytest.mark.asyncio
async def test_no_results_is_weak(mocker: MagicMock) -> None:
    _patch_clients(mocker, score=None)
    ctx = await stage3_retrieval.run(_ctx())
    assert ctx.retrieval is not None
    assert ctx.retrieval.rs_signal == RSSignal.WEAK
    assert ctx.retrieval.top_score == 0.0
    assert len(ctx.retrieval.docs) == 0


@pytest.mark.asyncio
async def test_exception_sets_retrieval_failed(mocker: MagicMock) -> None:
    mocker.patch(
        "cmart.pipeline.stage3_retrieval.OpenAIEmbeddingClient",
        side_effect=Exception("Service unavailable"),
    )
    mock_settings = MagicMock(rs_strong_threshold=0.60, rs_moderate_threshold=0.45)
    mocker.patch("cmart.pipeline.stage3_retrieval.get_settings", return_value=mock_settings)
    ctx = await stage3_retrieval.run(_ctx())
    assert ctx.retrieval is not None
    assert ctx.retrieval.retrieval_failed is True
    assert ctx.retrieval.rs_signal == RSSignal.WEAK


@pytest.mark.asyncio
async def test_doc_fields_mapped_correctly(mocker: MagicMock) -> None:
    _patch_clients(mocker, score=0.70)
    ctx = await stage3_retrieval.run(_ctx())
    assert ctx.retrieval is not None
    assert len(ctx.retrieval.docs) == 1
    doc = ctx.retrieval.docs[0]
    assert doc.chunk_id == "chunk_001"
    assert doc.doc_id == "doc_001"
    assert doc.content == "Some content"
    assert doc.score == 0.70
    assert doc.title == "Test Doc"


@pytest.mark.asyncio
async def test_stage_latency_recorded(mocker: MagicMock) -> None:
    _patch_clients(mocker, score=0.65)
    ctx = await stage3_retrieval.run(_ctx())
    assert "retrieval" in ctx.stage_latencies
    assert ctx.stage_latencies["retrieval"] >= 0
