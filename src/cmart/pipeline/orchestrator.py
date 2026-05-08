from __future__ import annotations

# Orchestrator — wires all 7 stages and controls execution order.
# Stages 2 (analysis) and 3 (retrieval) run concurrently to reduce end-to-end latency.
# Stages 4 (generation) and 5 (validation) are skipped when QC != CLEAR — no answer
# is generated for ambiguous/incomplete queries, so GC/SA signals would be meaningless.
# Session clarify_rounds is hydrated before the pipeline runs so stage 6 can enforce the limit.
import asyncio

from cmart.pipeline import (
    stage1_intake,
    stage2_analysis,
    stage3_retrieval,
    stage4_generation,
    stage5_validation,
    stage6_decision,
    stage7_response,
)
from cmart.schemas.pipeline import PipelineContext, QCSignal
from cmart.services.session_store import SessionStore


async def run(
    ctx: PipelineContext,
    session_store: SessionStore | None = None,
) -> PipelineContext:
    # Load clarify_rounds from an existing session before the decision engine runs
    if session_store and ctx.session_id:
        session = await session_store.get(ctx.session_id)
        if session:
            ctx.clarify_rounds = session.clarify_rounds

    ctx = await stage1_intake.run(ctx)

    # Stages 2 and 3 are independent: run concurrently to reduce end-to-end latency.
    # Both mutate ctx in place (different fields); asyncio is single-threaded, no races.
    await asyncio.gather(
        stage2_analysis.run(ctx),
        stage3_retrieval.run(ctx),
    )

    # Short-circuit: skip generation and validation when the query cannot be answered.
    # If QC != CLEAR, no answer is generated, so GC/SA signals would be meaningless.
    if ctx.analysis and ctx.analysis.qc == QCSignal.CLEAR:
        ctx = await stage4_generation.run(ctx)
        ctx = await stage5_validation.run(ctx)

    ctx = stage6_decision.run(ctx)
    ctx = await stage7_response.run(ctx, session_store=session_store)
    return ctx
