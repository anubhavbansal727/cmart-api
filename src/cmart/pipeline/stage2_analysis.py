from __future__ import annotations

import time

from cmart.schemas.pipeline import AnalysisResult, PipelineContext, QCSignal
from cmart.services.llm.gemini import GeminiClient

_PROMPT = """\
You are a query analysis component for a B2B SaaS customer support system.

Classify the customer's support query into one of three categories:

CLEAR      — Specific and answerable directly from a knowledge base.
AMBIGUOUS  — Could mean multiple things; needs clarification to answer correctly.
INCOMPLETE — Missing key context (e.g. product area, account type, version) \
required to give a useful answer.

Rules:
- Do NOT answer the query. Only classify it.
- If AMBIGUOUS or INCOMPLETE, provide a single focused clarification question — \
the minimum information needed to resolve the ambiguity. Do not ask multiple questions.
- If CLEAR, set clarification_question to null.

Query: {query}\
"""


async def run(ctx: PipelineContext) -> PipelineContext:
    t0 = time.monotonic()
    llm = GeminiClient()

    try:
        result = await llm.invoke_structured(
            _PROMPT.format(query=ctx.query),
            AnalysisResult,
        )
    except Exception:
        # LLM failure → safe default: treat as ambiguous, never crash pipeline
        result = AnalysisResult(qc=QCSignal.AMBIGUOUS)

    ctx.analysis = result
    ctx.stage_latencies["analysis"] = int((time.monotonic() - t0) * 1000)
    return ctx
