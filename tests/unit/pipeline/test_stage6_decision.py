"""Unit tests for Stage 6 — Decision Engine.

100% branch coverage required: every ESCALATE / ANSWER / CLARIFY path must be
exercised, including all four ESCALATE reasons and the DEFAULT_SAFE fallback.
"""
from __future__ import annotations

from cmart.pipeline import stage6_decision
from cmart.schemas.pipeline import (
    AnalysisResult,
    GCSignal,
    PipelineContext,
    QCSignal,
    RetrievalResult,
    RSSignal,
    SASignal,
    ValidationResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_retrieval(rs: RSSignal) -> RetrievalResult:
    return RetrievalResult(docs=[], rs_signal=rs, top_score=0.0)


def _make_validation(gc: GCSignal, sa: SASignal) -> ValidationResult:
    return ValidationResult(gc=gc, sa=sa)


def _make_analysis(qc: QCSignal) -> AnalysisResult:
    return AnalysisResult(qc=qc)


def _ctx(
    rs: RSSignal = RSSignal.STRONG,
    gc: GCSignal = GCSignal.FULLY_SUPPORTED,
    sa: SASignal = SASignal.AGREES,
    qc: QCSignal = QCSignal.CLEAR,
    clarify_rounds: int = 0,
) -> PipelineContext:
    ctx = PipelineContext(query="test", user_id="u1", account_id="acc1")
    ctx.retrieval = _make_retrieval(rs)
    ctx.validation = _make_validation(gc, sa)
    ctx.analysis = _make_analysis(qc)
    ctx.clarify_rounds = clarify_rounds
    return ctx


# ---------------------------------------------------------------------------
# ESCALATE paths
# ---------------------------------------------------------------------------

def test_escalate_low_grounding() -> None:
    ctx = _ctx(gc=GCSignal.NOT_SUPPORTED)
    result = stage6_decision.run(ctx)
    assert result.decision_result is not None
    assert result.decision_result.decision == "escalate"
    assert result.decision_result.reason == "LOW_GROUNDING"


def test_escalate_source_conflict() -> None:
    ctx = _ctx(gc=GCSignal.FULLY_SUPPORTED, sa=SASignal.CONFLICT)
    result = stage6_decision.run(ctx)
    assert result.decision_result is not None
    assert result.decision_result.decision == "escalate"
    assert result.decision_result.reason == "SOURCE_CONFLICT"


def test_escalate_low_retrieval() -> None:
    ctx = _ctx(gc=GCSignal.FULLY_SUPPORTED, sa=SASignal.AGREES, rs=RSSignal.WEAK)
    result = stage6_decision.run(ctx)
    assert result.decision_result is not None
    assert result.decision_result.decision == "escalate"
    assert result.decision_result.reason == "LOW_RETRIEVAL"


def test_escalate_clarification_limit_reached() -> None:
    ctx = _ctx(
        gc=GCSignal.FULLY_SUPPORTED,
        sa=SASignal.AGREES,
        rs=RSSignal.STRONG,
        clarify_rounds=2,  # == max_clarify_rounds default
    )
    result = stage6_decision.run(ctx)
    assert result.decision_result is not None
    assert result.decision_result.decision == "escalate"
    assert result.decision_result.reason == "CLARIFICATION_LIMIT_REACHED"


def test_escalate_priority_over_answer() -> None:
    """GC=NOT_SUPPORTED fires ESCALATE even when clarify_rounds would also trigger it."""
    ctx = _ctx(gc=GCSignal.NOT_SUPPORTED, clarify_rounds=2)
    result = stage6_decision.run(ctx)
    assert result.decision_result is not None
    assert result.decision_result.reason == "LOW_GROUNDING"


# ---------------------------------------------------------------------------
# ANSWER path
# ---------------------------------------------------------------------------

def test_answer_high_confidence() -> None:
    ctx = _ctx(
        rs=RSSignal.STRONG,
        gc=GCSignal.FULLY_SUPPORTED,
        qc=QCSignal.CLEAR,
        sa=SASignal.AGREES,
        clarify_rounds=0,
    )
    result = stage6_decision.run(ctx)
    assert result.decision_result is not None
    assert result.decision_result.decision == "answer"
    assert result.decision_result.reason == "HIGH_CONFIDENCE"


# ---------------------------------------------------------------------------
# CLARIFY paths (DEFAULT_SAFE fallback)
# ---------------------------------------------------------------------------

def test_clarify_ambiguous_query() -> None:
    ctx = _ctx(
        rs=RSSignal.STRONG, gc=GCSignal.FULLY_SUPPORTED, sa=SASignal.AGREES, qc=QCSignal.AMBIGUOUS
    )
    result = stage6_decision.run(ctx)
    assert result.decision_result is not None
    assert result.decision_result.decision == "clarify"
    assert result.decision_result.reason == "DEFAULT_SAFE"


def test_clarify_incomplete_query() -> None:
    ctx = _ctx(
        rs=RSSignal.STRONG, gc=GCSignal.FULLY_SUPPORTED, sa=SASignal.AGREES, qc=QCSignal.INCOMPLETE
    )
    result = stage6_decision.run(ctx)
    assert result.decision_result is not None
    assert result.decision_result.decision == "clarify"


def test_clarify_moderate_retrieval() -> None:
    ctx = _ctx(
        rs=RSSignal.MODERATE, gc=GCSignal.FULLY_SUPPORTED, sa=SASignal.AGREES, qc=QCSignal.CLEAR
    )
    result = stage6_decision.run(ctx)
    assert result.decision_result is not None
    assert result.decision_result.decision == "clarify"


def test_clarify_partially_supported() -> None:
    ctx = _ctx(
        rs=RSSignal.STRONG, gc=GCSignal.PARTIALLY_SUPPORTED, sa=SASignal.AGREES, qc=QCSignal.CLEAR
    )
    result = stage6_decision.run(ctx)
    assert result.decision_result is not None
    assert result.decision_result.decision == "clarify"


def test_clarify_partial_agreement() -> None:
    ctx = _ctx(
        rs=RSSignal.STRONG, gc=GCSignal.FULLY_SUPPORTED, sa=SASignal.PARTIAL, qc=QCSignal.CLEAR
    )
    result = stage6_decision.run(ctx)
    assert result.decision_result is not None
    assert result.decision_result.decision == "clarify"


# ---------------------------------------------------------------------------
# Missing signals → safe defaults → ESCALATE
# ---------------------------------------------------------------------------

def test_missing_all_signals_escalates() -> None:
    ctx = PipelineContext(query="test", user_id="u1", account_id="acc1")
    # No analysis, retrieval, or validation set
    result = stage6_decision.run(ctx)
    assert result.decision_result is not None
    # qc defaults to AMBIGUOUS → short-circuit → CLARIFY (RS=WEAK no longer escalates here)
    assert result.decision_result.decision == "clarify"
    assert result.decision_result.reason == "DEFAULT_SAFE"


def test_missing_validation_escalates() -> None:
    ctx = PipelineContext(query="test", user_id="u1", account_id="acc1")
    ctx.retrieval = _make_retrieval(RSSignal.STRONG)
    ctx.analysis = _make_analysis(QCSignal.CLEAR)
    # validation intentionally None
    result = stage6_decision.run(ctx)
    assert result.decision_result is not None
    assert result.decision_result.decision == "escalate"
    assert result.decision_result.reason == "LOW_GROUNDING"


def test_escalate_retrieval_failure() -> None:
    """retrieval_failed=True fires RETRIEVAL_FAILURE before any signal checks."""
    ctx = _ctx(rs=RSSignal.STRONG, gc=GCSignal.FULLY_SUPPORTED, sa=SASignal.AGREES)
    assert ctx.retrieval is not None
    ctx.retrieval.retrieval_failed = True
    result = stage6_decision.run(ctx)
    assert result.decision_result is not None
    assert result.decision_result.decision == "escalate"
    assert result.decision_result.reason == "RETRIEVAL_FAILURE"


# ---------------------------------------------------------------------------
# QC short-circuit paths (stages 4+5 skipped when QC != CLEAR)
# ---------------------------------------------------------------------------


def test_ambiguous_weak_retrieval_clarifies() -> None:
    """QC=AMBIGUOUS + RS=WEAK → CLARIFY (weak RS on a vague query is expected; clarify first)."""
    ctx = _ctx(qc=QCSignal.AMBIGUOUS, rs=RSSignal.WEAK)
    ctx.validation = None  # stages 4+5 were skipped
    result = stage6_decision.run(ctx)
    assert result.decision_result is not None
    assert result.decision_result.decision == "clarify"
    assert result.decision_result.reason == "DEFAULT_SAFE"


def test_ambiguous_clarification_limit_escalates() -> None:
    """QC=AMBIGUOUS + clarify_rounds at max → ESCALATE (CLARIFICATION_LIMIT_REACHED)."""
    ctx = _ctx(qc=QCSignal.AMBIGUOUS, rs=RSSignal.STRONG)
    ctx.validation = None  # stages 4+5 were skipped
    ctx.clarify_rounds = 2
    result = stage6_decision.run(ctx)
    assert result.decision_result is not None
    assert result.decision_result.decision == "escalate"
    assert result.decision_result.reason == "CLARIFICATION_LIMIT_REACHED"
