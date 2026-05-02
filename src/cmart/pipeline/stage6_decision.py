from __future__ import annotations

from cmart.config import get_settings
from cmart.schemas.pipeline import (
    DecisionResult,
    GCSignal,
    PipelineContext,
    QCSignal,
    RSSignal,
    SASignal,
)


def run(ctx: PipelineContext) -> PipelineContext:
    """Pure decision engine — synchronous, no I/O.

    Evaluates the four pipeline signals and returns the appropriate decision.
    Priority order: ESCALATE > ANSWER > CLARIFY (safe default).
    """
    settings = get_settings()

    # Safe defaults when upstream stages failed
    gc = ctx.validation.gc if ctx.validation else GCSignal.NOT_SUPPORTED
    sa = ctx.validation.sa if ctx.validation else SASignal.CONFLICT
    rs = ctx.retrieval.rs_signal if ctx.retrieval else RSSignal.WEAK
    qc = ctx.analysis.qc if ctx.analysis else QCSignal.AMBIGUOUS

    # --- Priority 1: ESCALATE ---
    if ctx.retrieval and ctx.retrieval.retrieval_failed:
        ctx.decision_result = DecisionResult(decision="escalate", reason="RETRIEVAL_FAILURE")
        return ctx

    if gc == GCSignal.NOT_SUPPORTED:
        ctx.decision_result = DecisionResult(decision="escalate", reason="LOW_GROUNDING")
        return ctx

    if sa == SASignal.CONFLICT:
        ctx.decision_result = DecisionResult(decision="escalate", reason="SOURCE_CONFLICT")
        return ctx

    if rs == RSSignal.WEAK:
        ctx.decision_result = DecisionResult(decision="escalate", reason="LOW_RETRIEVAL")
        return ctx

    if ctx.clarify_rounds >= settings.max_clarify_rounds:
        ctx.decision_result = DecisionResult(
            decision="escalate", reason="CLARIFICATION_LIMIT_REACHED"
        )
        return ctx

    # --- Priority 2: ANSWER ---
    if (
        rs == RSSignal.STRONG
        and gc == GCSignal.FULLY_SUPPORTED
        and qc == QCSignal.CLEAR
        and sa == SASignal.AGREES
    ):
        ctx.decision_result = DecisionResult(decision="answer", reason="HIGH_CONFIDENCE")
        return ctx

    # --- Priority 3: CLARIFY (default safe) ---
    ctx.decision_result = DecisionResult(decision="clarify", reason="DEFAULT_SAFE")
    return ctx
