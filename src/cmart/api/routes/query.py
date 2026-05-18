from __future__ import annotations

import time
import uuid
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends

from cmart.api.dependencies import get_current_account, get_redis
from cmart.db.engine import AsyncSessionLocal
from cmart.db.models import Account
from cmart.db.repositories.query_log import insert_log
from cmart.pipeline.orchestrator import run as run_pipeline
from cmart.rate_limit.redis_limiter import RedisRateLimiter
from cmart.schemas.pipeline import PipelineContext
from cmart.schemas.query import DecisionType, QueryRequest, QueryResponse, RetrievedDoc
from cmart.services.session_store import SessionStore

router = APIRouter()
logger = structlog.get_logger(__name__)


async def _log_query(
    account_id: uuid.UUID,
    ctx: PipelineContext,
    decision: str,
    reason: str,
    latency_ms: int,
) -> None:
    """Write a QueryLog row in a background task — pipeline response never waits on this."""
    async with AsyncSessionLocal() as db:
        try:
            await insert_log(
                db,
                account_id=account_id,
                query=ctx.query,
                decision=decision,
                reason=reason,
                rs_signal=ctx.retrieval.rs_signal.value if ctx.retrieval else None,
                qc_signal=ctx.analysis.qc.value if ctx.analysis else None,
                gc_signal=ctx.validation.gc.value if ctx.validation else None,
                sa_signal=ctx.validation.sa.value if ctx.validation else None,
                latency_ms=latency_ms,
                session_id=ctx.session_id,
            )
            await db.commit()
        except Exception as exc:
            logger.warning("query_log.write_failed", error=str(exc))


@router.post("", response_model=QueryResponse)
async def submit_query(
    request: QueryRequest,
    background_tasks: BackgroundTasks,
    account: Account = Depends(get_current_account),
    redis: Any = Depends(get_redis),
) -> QueryResponse:
    start = time.monotonic()

    await RedisRateLimiter(redis).check(str(account.id))

    ctx = PipelineContext(
        query=request.query,
        user_id=request.user_id,
        account_id=str(account.id),
        session_id=request.session_id,
        metadata=request.metadata,
    )

    session_store = SessionStore(redis) if redis else None
    ctx = await run_pipeline(ctx, session_store=session_store)

    latency_ms = int((time.monotonic() - start) * 1000)
    dr = ctx.decision_result
    decision = DecisionType(dr.decision) if dr else DecisionType.ESCALATE
    reason = dr.reason if dr else "PIPELINE_ERROR"

    background_tasks.add_task(_log_query, account.id, ctx, decision.value, reason, latency_ms)

    sources = []
    if ctx.retrieval:
        sources = [
            RetrievedDoc(
                chunk_id=d.chunk_id,
                doc_id=d.doc_id,
                content=d.content,
                score=d.score,
                title=d.title,
                source_url=d.source_url,
            )
            for d in ctx.retrieval.docs
        ]

    signals = {
        "rs": ctx.retrieval.rs_signal.value if ctx.retrieval else None,
        "qc": ctx.analysis.qc.value if ctx.analysis else None,
        "gc": ctx.validation.gc.value if ctx.validation else None,
        "sa": ctx.validation.sa.value if ctx.validation else None,
    }

    if decision == DecisionType.ANSWER:
        return QueryResponse(
            decision=decision,
            answer=ctx.generation.answer if ctx.generation else None,
            sources=sources,
            reason=reason,
            latency_ms=latency_ms,
            signals=signals,
        )

    if decision == DecisionType.CLARIFY:
        clarification_question = ctx.analysis.clarification_question if ctx.analysis else None
        # DEFAULT_SAFE fallback: RS=MODERATE with QC=CLEAR has no LLM-generated question
        if clarification_question is None:
            clarification_question = (
                "Could you provide more detail about your issue so I can find the most "
                "relevant information for you?"
            )
        return QueryResponse(
            decision=decision,
            clarification_question=clarification_question,
            session_id=ctx.session_id,
            sources=sources,
            reason=reason,
            latency_ms=latency_ms,
            signals=signals,
        )

    # ESCALATE
    return QueryResponse(
        decision=decision,
        escalation_context=ctx.escalation_context,
        sources=sources,
        reason=reason,
        latency_ms=latency_ms,
        signals=signals,
    )
