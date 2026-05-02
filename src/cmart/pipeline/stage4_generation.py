from __future__ import annotations

import time

from cmart.schemas.pipeline import GenerationResult, PipelineContext
from cmart.services.llm.gemini import GeminiClient

_PROMPT = """\
You are a customer support answer generator for a B2B SaaS product.
Your ONLY job is to answer the query using the provided context documents.

MANDATORY rules — violating any of these is a critical failure:
1. Use ONLY information present in the context. Do not use external knowledge.
2. Every factual claim must include an inline citation: [Source: <doc_title>]
3. If the context does not contain enough information to answer fully, explicitly \
state what you cannot answer. Do not invent steps, URLs, or feature names.
4. Be concise and direct. Answer what was asked — nothing more.

Context:
{context}

Query: {query}\
"""


def _format_context(ctx: PipelineContext) -> str:
    if not ctx.retrieval or not ctx.retrieval.docs:
        return "No context available."
    parts = []
    for i, doc in enumerate(ctx.retrieval.docs, 1):
        title = doc.title or doc.doc_id
        parts.append(f"[{i}] Title: {title}\nContent: {doc.content}")
    return "\n\n".join(parts)


async def run(ctx: PipelineContext) -> PipelineContext:
    t0 = time.monotonic()
    llm = GeminiClient()
    context = _format_context(ctx)

    try:
        answer = await llm.invoke(_PROMPT.format(query=ctx.query, context=context))
    except Exception:
        answer = "I was unable to generate an answer at this time."

    ctx.generation = GenerationResult(answer=answer)
    ctx.stage_latencies["generation"] = int((time.monotonic() - t0) * 1000)
    return ctx
