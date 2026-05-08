from __future__ import annotations

# Stage 2: Query Clarity (QC) classification — does NOT touch the knowledge base.
# Classifies the query as CLEAR / AMBIGUOUS / INCOMPLETE using an LLM.
# CLEAR means "well-formed enough to search"; the KB check happens in stages 3 & 5.
# Non-CLEAR queries short-circuit to CLARIFY in the Decision Engine before retrieval.
# LLM failure → safe default of AMBIGUOUS so the pipeline never crashes here.

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
- If AMBIGUOUS or INCOMPLETE, you MUST provide a clarification_question — \
a single focused question that is the minimum information needed to resolve the ambiguity.
- If CLEAR, set clarification_question to null.

Query: {query}\
"""

_DEFAULT_CLARIFICATION: dict[QCSignal, str] = {
    QCSignal.AMBIGUOUS: "Could you clarify what specifically you need help with?",
    QCSignal.INCOMPLETE: "Could you provide more context, such as the product area or version?",
}


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

    # Ensure clarification_question is always populated for non-CLEAR classifications
    if result.qc != QCSignal.CLEAR and result.clarification_question is None:
        result = AnalysisResult(
            qc=result.qc,
            clarification_question=_DEFAULT_CLARIFICATION[result.qc],
        )

    ctx.analysis = result
    ctx.stage_latencies["analysis"] = int((time.monotonic() - t0) * 1000)
    return ctx
