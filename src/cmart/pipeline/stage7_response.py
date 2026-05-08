from __future__ import annotations

# Stage 7: Response — handles session side-effects and builds the escalation context.
# CLARIFY → creates or increments a session to track clarification rounds.
# ANSWER / ESCALATE → resolves and deletes the session.
# ESCALATE → packages all signals, the query, the answer attempt, and retrieved docs
#             into escalation_context for the human agent handoff.
# Does not format the final API response — that happens in the API service layer.
from typing import Any

from cmart.schemas.pipeline import PipelineContext
from cmart.services.session_store import SessionStore


async def run(
    ctx: PipelineContext,
    session_store: SessionStore | None = None,
) -> PipelineContext:
    """Handle session side-effects and build escalation context."""
    if ctx.decision_result is None:
        return ctx

    decision = ctx.decision_result.decision

    if decision == "clarify":
        if session_store:
            if ctx.session_id:
                await session_store.increment_round(ctx.session_id)
            else:
                session = await session_store.create(
                    account_id=ctx.account_id,
                    user_id=ctx.user_id,
                    original_query=ctx.query,
                )
                ctx.session_id = session.session_id
                await session_store.increment_round(ctx.session_id)

    else:
        # ANSWER or ESCALATE resolves the session
        if ctx.session_id and session_store:
            await session_store.delete(ctx.session_id)
            if decision == "answer":
                ctx.session_id = None

    if decision == "escalate":
        ctx.escalation_context = _build_escalation_context(ctx)

    return ctx


def _build_escalation_context(ctx: PipelineContext) -> dict[str, Any]:
    return {
        "reason": ctx.decision_result.reason if ctx.decision_result else "UNKNOWN",
        "signals": {
            "rs": ctx.retrieval.rs_signal.value if ctx.retrieval else None,
            "qc": ctx.analysis.qc.value if ctx.analysis else None,
            "gc": ctx.validation.gc.value if ctx.validation else None,
            "sa": ctx.validation.sa.value if ctx.validation else None,
        },
        "query": ctx.query,
        "answer_attempt": ctx.generation.answer if ctx.generation else None,
        "retrieved_docs": [
            {"doc_id": d.doc_id, "title": d.title or d.doc_id, "score": d.score}
            for d in (ctx.retrieval.docs if ctx.retrieval else [])
        ],
    }
