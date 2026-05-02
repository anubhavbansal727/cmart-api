from __future__ import annotations

from cmart.schemas.pipeline import PipelineContext


async def run(ctx: PipelineContext) -> PipelineContext:
    ctx.query = ctx.query.strip()
    return ctx
