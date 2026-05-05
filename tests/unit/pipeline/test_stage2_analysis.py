"""Unit tests for Stage 2 — Query Analysis."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from cmart.pipeline import stage2_analysis
from cmart.schemas.pipeline import AnalysisResult, PipelineContext, QCSignal


def _ctx(query: str = "test query") -> PipelineContext:
    return PipelineContext(query=query, user_id="u1", account_id="acc1")


def _mock_llm(mocker: MagicMock, result: AnalysisResult) -> None:
    mock_client = MagicMock(invoke_structured=AsyncMock(return_value=result))
    mocker.patch("cmart.pipeline.stage2_analysis.GeminiClient", return_value=mock_client)


@pytest.mark.asyncio
async def test_clear_query(mocker: MagicMock) -> None:
    _mock_llm(mocker, AnalysisResult(qc=QCSignal.CLEAR))
    ctx = await stage2_analysis.run(_ctx("How do I reset my password?"))
    assert ctx.analysis is not None
    assert ctx.analysis.qc == QCSignal.CLEAR
    assert ctx.analysis.clarification_question is None


@pytest.mark.asyncio
async def test_ambiguous_query_with_llm_question(mocker: MagicMock) -> None:
    _mock_llm(
        mocker,
        AnalysisResult(
            qc=QCSignal.AMBIGUOUS,
            clarification_question="Which product are you asking about?",
        ),
    )
    ctx = await stage2_analysis.run(_ctx("It's not working"))
    assert ctx.analysis is not None
    assert ctx.analysis.qc == QCSignal.AMBIGUOUS
    assert ctx.analysis.clarification_question == "Which product are you asking about?"


@pytest.mark.asyncio
async def test_ambiguous_null_question_uses_default(mocker: MagicMock) -> None:
    _mock_llm(mocker, AnalysisResult(qc=QCSignal.AMBIGUOUS, clarification_question=None))
    ctx = await stage2_analysis.run(_ctx("something broken"))
    assert ctx.analysis is not None
    expected = stage2_analysis._DEFAULT_CLARIFICATION[QCSignal.AMBIGUOUS]
    assert ctx.analysis.clarification_question == expected


@pytest.mark.asyncio
async def test_incomplete_null_question_uses_default(mocker: MagicMock) -> None:
    _mock_llm(mocker, AnalysisResult(qc=QCSignal.INCOMPLETE, clarification_question=None))
    ctx = await stage2_analysis.run(_ctx("error"))
    assert ctx.analysis is not None
    expected = stage2_analysis._DEFAULT_CLARIFICATION[QCSignal.INCOMPLETE]
    assert ctx.analysis.clarification_question == expected


@pytest.mark.asyncio
async def test_incomplete_with_llm_question_preserved(mocker: MagicMock) -> None:
    _mock_llm(
        mocker,
        AnalysisResult(
            qc=QCSignal.INCOMPLETE,
            clarification_question="Which product version are you running?",
        ),
    )
    ctx = await stage2_analysis.run(_ctx("account not working"))
    assert ctx.analysis is not None
    assert ctx.analysis.clarification_question == "Which product version are you running?"


@pytest.mark.asyncio
async def test_llm_exception_defaults_to_ambiguous(mocker: MagicMock) -> None:
    mock_client = MagicMock(invoke_structured=AsyncMock(side_effect=Exception("LLM timeout")))
    mocker.patch("cmart.pipeline.stage2_analysis.GeminiClient", return_value=mock_client)
    ctx = await stage2_analysis.run(_ctx("some query"))
    assert ctx.analysis is not None
    assert ctx.analysis.qc == QCSignal.AMBIGUOUS
    assert ctx.analysis.clarification_question is not None


@pytest.mark.asyncio
async def test_stage_latency_recorded(mocker: MagicMock) -> None:
    _mock_llm(mocker, AnalysisResult(qc=QCSignal.CLEAR))
    ctx = await stage2_analysis.run(_ctx())
    assert "analysis" in ctx.stage_latencies
    assert ctx.stage_latencies["analysis"] >= 0
