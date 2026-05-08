from __future__ import annotations

# Stage 1: Query intake — sanitizes the raw query before anything else runs.
# Currently just strips leading/trailing whitespace. Entry point of the pipeline.
from cmart.schemas.pipeline import PipelineContext


async def run(ctx: PipelineContext) -> PipelineContext:
    ctx.query = ctx.query.strip()
    return ctx
