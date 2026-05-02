from __future__ import annotations

from cmart.pipeline import (
    stage1_intake,
    stage2_analysis,
    stage3_retrieval,
    stage4_generation,
    stage5_validation,
    stage6_decision,
    stage7_response,
)
from cmart.schemas.pipeline import PipelineContext
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
    ctx = await stage2_analysis.run(ctx)
    ctx = await stage3_retrieval.run(ctx)
    ctx = await stage4_generation.run(ctx)
    ctx = await stage5_validation.run(ctx)
    ctx = stage6_decision.run(ctx)
    ctx = await stage7_response.run(ctx, session_store=session_store)
    return ctx
