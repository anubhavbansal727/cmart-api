from __future__ import annotations

# Stage 5: Validation — runs two LLM checks in parallel to produce GC and SA signals.
# GC (Grounding Check): are all claims in the answer backed by the retrieved docs?
# SA (Source Agreement): do the retrieved docs contradict each other on this query?
# Both checks run concurrently via asyncio.gather for speed.
# On failure → GC=NOT_SUPPORTED / SA=CONFLICT, which forces ESCALATE in the Decision Engine.
# Chunks from the same doc are merged before SA validation so they aren't
# treated as separate potentially-conflicting sources.
import asyncio
import time

import structlog

from cmart.schemas.pipeline import (
    AgreementResult,
    GCSignal,
    GroundingResult,
    PipelineContext,
    SASignal,
    ValidationResult,
)
from cmart.services.llm.gemini import GeminiClient

_GC_PROMPT = """\
You are a grounding verification component.
Check whether every factual claim in the generated answer is explicitly \
supported by the provided context documents.

FULLY_SUPPORTED     — Every claim traces back to the context.
PARTIALLY_SUPPORTED — Most claims are supported; one or more have no basis in the context.
NOT_SUPPORTED       — The answer contains significant claims absent from the context.

Context:
{context}

Generated answer:
{answer}\
"""

_SA_PROMPT = """\
You are a source consistency checker.
Identify whether the provided context documents contradict each other \
on the topic of the customer's query.

AGREES   — All documents present consistent information.
PARTIAL  — Minor inconsistencies (different wording, version differences) \
but no direct contradictions.
CONFLICT — Documents directly contradict each other on a fact relevant to the query \
(e.g. different steps, opposite instructions, conflicting feature descriptions).

Query: {query}

Context:
{context}\
"""


def _format_context(ctx: PipelineContext) -> str:
    if not ctx.retrieval or not ctx.retrieval.docs:
        return "No context available."
    # Group chunks by doc_id so the SA validator treats them as one source,
    # not as separate potentially-conflicting documents.
    seen: dict[str, list[str]] = {}
    titles: dict[str, str] = {}
    for doc in ctx.retrieval.docs:
        seen.setdefault(doc.doc_id, []).append(doc.content)
        titles[doc.doc_id] = doc.title or doc.doc_id
    parts = []
    for i, (doc_id, chunks) in enumerate(seen.items(), 1):
        combined = " ".join(chunks)
        parts.append(f"[{i}] Title: {titles[doc_id]}\nContent: {combined}")
    return "\n\n".join(parts)


async def run(ctx: PipelineContext) -> PipelineContext:
    t0 = time.monotonic()
    llm = GeminiClient()
    context = _format_context(ctx)
    answer = ctx.generation.answer if ctx.generation else ""

    gc_task = llm.invoke_structured(
        _GC_PROMPT.format(context=context, answer=answer),
        GroundingResult,
    )
    sa_task = llm.invoke_structured(
        _SA_PROMPT.format(query=ctx.query, context=context),
        AgreementResult,
    )

    logger = structlog.get_logger()
    gc_raw, sa_raw = await asyncio.gather(gc_task, sa_task, return_exceptions=True)

    # Individual failures → safe defaults that will force ESCALATE in decision engine
    if not isinstance(gc_raw, GroundingResult):
        logger.error("stage5.gc_failed", error=repr(gc_raw))
    if not isinstance(sa_raw, AgreementResult):
        logger.error("stage5.sa_failed", error=repr(sa_raw))

    gc_result: GroundingResult = (
        gc_raw if isinstance(gc_raw, GroundingResult)
        else GroundingResult(gc=GCSignal.NOT_SUPPORTED)
    )
    sa_result: AgreementResult = (
        sa_raw if isinstance(sa_raw, AgreementResult)
        else AgreementResult(sa=SASignal.CONFLICT)
    )

    ctx.validation = ValidationResult(
        gc=gc_result.gc,
        sa=sa_result.sa,
        unsupported_claims=gc_result.unsupported_claims,
        conflict_summary=sa_result.conflict_summary,
    )
    ctx.stage_latencies["validation"] = int((time.monotonic() - t0) * 1000)
    return ctx
