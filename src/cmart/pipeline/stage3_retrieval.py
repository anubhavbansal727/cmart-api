from __future__ import annotations

# Stage 3: Retrieval — embeds the query and searches Pinecone for the top-5 KB chunks.
# Sets the Retrieval Strength (RS) signal: STRONG (>=0.65), MODERATE (0.50–0.65), WEAK (<0.50).
# RS is based on the top document score only, not an average.
# On failure → RS=WEAK + retrieval_failed=True, which forces ESCALATE in the Decision Engine.
import time

import structlog

from cmart.config import get_settings
from cmart.schemas.pipeline import (
    PipelineContext,
    RetrievalResult,
    RetrievedDoc,
    RSSignal,
)
from cmart.services.embeddings.openai import OpenAIEmbeddingClient
from cmart.services.vector_store.pinecone import PineconeVectorStoreClient

logger = structlog.get_logger(__name__)

_TOP_K = 5


async def run(ctx: PipelineContext) -> PipelineContext:
    settings = get_settings()
    t0 = time.monotonic()

    try:
        embedding_client = OpenAIEmbeddingClient()
        vector_client = PineconeVectorStoreClient()

        query_vector = await embedding_client.embed(ctx.query)
        raw_results = await vector_client.query(
            namespace=ctx.account_id,
            vector=query_vector,
            top_k=_TOP_K,
        )

        docs = [
            RetrievedDoc(
                chunk_id=r["id"],
                doc_id=r["metadata"].get("doc_id", ""),
                content=r["metadata"].get("content", ""),
                score=r["score"],
                title=r["metadata"].get("title"),
                source_url=r["metadata"].get("source_url"),
            )
            for r in raw_results
        ]

        top_score = docs[0].score if docs else 0.0

        if top_score >= settings.rs_strong_threshold:
            rs = RSSignal.STRONG
        elif top_score >= settings.rs_moderate_threshold:
            rs = RSSignal.MODERATE
        else:
            rs = RSSignal.WEAK

        ctx.retrieval = RetrievalResult(docs=docs, rs_signal=rs, top_score=top_score)

    except Exception as exc:
        logger.error("stage3_retrieval.failed", error=str(exc))
        ctx.retrieval = RetrievalResult(
            docs=[],
            rs_signal=RSSignal.WEAK,
            top_score=0.0,
            retrieval_failed=True,
        )

    ctx.stage_latencies["retrieval"] = int((time.monotonic() - t0) * 1000)
    return ctx
