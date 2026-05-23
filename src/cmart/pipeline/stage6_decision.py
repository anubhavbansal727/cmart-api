from __future__ import annotations

# Stage 6: Decision Engine — pure rule-based routing; no ML, no I/O.
# Evaluates all four signals (RS, QC, GC, SA) and outputs ANSWER / CLARIFY / ESCALATE.
# Priority order: ESCALATE > ANSWER > CLARIFY (CLARIFY is the safe default).
# QC != CLEAR short-circuits before checking GC/SA (no answer was generated yet).
# ANSWER requires all four signals to be at their highest values simultaneously.
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

    rs = ctx.retrieval.rs_signal if ctx.retrieval else RSSignal.WEAK
    qc = ctx.analysis.qc if ctx.analysis else QCSignal.AMBIGUOUS

    # --- Priority 1: ESCALATE on retrieval failure ---
    if ctx.retrieval and ctx.retrieval.retrieval_failed:
        ctx.decision_result = DecisionResult(decision="escalate", reason="RETRIEVAL_FAILURE")
        return ctx

    # --- Short-circuit when QC != CLEAR ---
    # No answer was generated, so GC/SA are undefined. Weak retrieval does NOT
    # escalate here — the query is ambiguous so weak RS is expected and we should
    # clarify first. Only the clarification limit forces escalation.
    if qc != QCSignal.CLEAR:
        if ctx.clarify_rounds >= settings.max_clarify_rounds:
            ctx.decision_result = DecisionResult(
                decision="escalate", reason="CLARIFICATION_LIMIT_REACHED"
            )
            return ctx
        ctx.decision_result = DecisionResult(decision="clarify", reason="DEFAULT_SAFE")
        return ctx

    # --- QC=CLEAR path: GC/SA signals are meaningful ---
    gc = ctx.validation.gc if ctx.validation else GCSignal.NOT_SUPPORTED
    sa = ctx.validation.sa if ctx.validation else SASignal.CONFLICT

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
    # RS=STRONG is ideal; RS=MODERATE is acceptable when GC and SA are both at max,
    # because the validation layer has already confirmed grounding and source agreement.
    if (
        rs in (RSSignal.STRONG, RSSignal.MODERATE)
        and gc == GCSignal.FULLY_SUPPORTED
        and qc == QCSignal.CLEAR
        and sa == SASignal.AGREES
    ):
        reason = "HIGH_CONFIDENCE" if rs == RSSignal.STRONG else "MODERATE_CONFIDENCE"
        ctx.decision_result = DecisionResult(decision="answer", reason=reason)
        return ctx

    # --- Priority 3: CLARIFY (default safe) ---
    ctx.decision_result = DecisionResult(decision="clarify", reason="DEFAULT_SAFE")
    return ctx
