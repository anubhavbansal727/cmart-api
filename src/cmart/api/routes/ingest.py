from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from cmart.api.dependencies import get_current_account, get_db
from cmart.db.models import Account
from cmart.db.repositories.doc_meta import get_by_doc_id, upsert_doc_meta
from cmart.schemas.ingest import DeleteResponse, IngestRequest, IngestResponse
from cmart.services.chunker import DocumentChunker
from cmart.services.embeddings.openai import OpenAIEmbeddingClient
from cmart.services.vector_store.pinecone import PineconeVectorStoreClient
from cmart.utils.errors import NotFoundError

router = APIRouter()
logger = structlog.get_logger(__name__)

# Module-level singletons — constructed once per worker process.
# Each class reads credentials from get_settings() at instantiation time.
_chunker = DocumentChunker()
_embedding_client = OpenAIEmbeddingClient()
_vector_store = PineconeVectorStoreClient()


@router.post("", response_model=IngestResponse)
async def ingest_documents(
    request: IngestRequest,
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
) -> IngestResponse:
    """POST /ingest — chunk, embed, and store documents for a given account.

    Each document is processed independently.  A per-document failure does not
    abort the batch — it is recorded in the ``failed`` list and processing
    continues for the remaining documents.

    Re-ingesting an existing doc_id is idempotent: existing Pinecone vectors
    are deleted first and the DocMeta row is updated in place.
    """
    namespace = str(account.id)
    ingested: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    for doc in request.documents:
        try:
            # Step 1 — Idempotency: purge any existing vectors for this doc
            existing = await get_by_doc_id(db, doc.doc_id, account.id)
            if existing is not None:
                await _vector_store.delete(namespace=namespace, doc_id=doc.doc_id)
                logger.info(
                    "ingest.existing_doc_purged",
                    doc_id=doc.doc_id,
                    account_id=namespace,
                )

            # Step 2 — Chunk
            chunks = _chunker.chunk(
                content=doc.content,
                doc_id=doc.doc_id,
                title=doc.title,
                source_url=doc.source_url,
                account_id=namespace,
            )

            # Step 3 — Embed all chunks in one batched call
            chunk_texts = [c["content"] for c in chunks]
            embeddings = await _embedding_client.embed_batch(chunk_texts)

            # Step 4 — Build Pinecone vector dicts
            vectors = [
                {
                    "id": chunk["id"],
                    "values": embedding,
                    "metadata": {
                        "doc_id": chunk["doc_id"],
                        "chunk_index": chunk["chunk_index"],
                        "content": chunk["content"],
                        "title": chunk["title"],
                        "source_url": chunk["source_url"],
                        "account_id": chunk["account_id"],
                    },
                }
                for chunk, embedding in zip(chunks, embeddings)
            ]

            # Step 5 — Upsert to Pinecone
            await _vector_store.upsert(namespace=namespace, vectors=vectors)

            # Step 6 — Persist DocMeta (insert or update)
            await upsert_doc_meta(
                db,
                doc_id=doc.doc_id,
                account_id=account.id,
                title=doc.title,
                source_url=doc.source_url,
                chunk_count=len(chunks),
            )

            chunk_count = len(chunks)
            ingested.append({"doc_id": doc.doc_id, "chunk_count": chunk_count, "status": "ok"})
            logger.info(
                "ingest.document_ingested",
                doc_id=doc.doc_id,
                chunk_count=chunk_count,
                account_id=namespace,
            )

        except Exception as exc:  # noqa: BLE001 — per-doc errors must not abort the batch
            failed.append({"doc_id": doc.doc_id, "error": str(exc)})
            logger.warning(
                "ingest.document_failed",
                doc_id=doc.doc_id,
                account_id=namespace,
                error=str(exc),
            )

    return IngestResponse(ingested=ingested, failed=failed)


@router.delete("/{doc_id}", response_model=DeleteResponse)
async def delete_document(
    doc_id: str,
    account: Account = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
) -> DeleteResponse:
    """DELETE /ingest/{doc_id} — remove a document and its vectors.

    Raises 404 when the document does not exist or was already deleted.
    Vectors are removed from Pinecone before the DB row is soft-deleted so that
    a partial failure leaves the DB record intact (recoverable by retrying).
    """
    namespace = str(account.id)

    existing = await get_by_doc_id(db, doc_id, account.id)
    if existing is None:
        raise NotFoundError(f"Document '{doc_id}' not found for this account.")

    # Delete vectors first — if this fails the DB record is still intact
    await _vector_store.delete(namespace=namespace, doc_id=doc_id)

    await _mark_deleted_in_db(db, doc_id, account)

    logger.info("ingest.document_deleted", doc_id=doc_id, account_id=namespace)
    return DeleteResponse(doc_id=doc_id, deleted=True)


async def _mark_deleted_in_db(db: AsyncSession, doc_id: str, account: Account) -> None:
    """Soft-delete the DocMeta row, raising NotFoundError if it disappears."""
    from cmart.db.repositories.doc_meta import mark_deleted

    deleted = await mark_deleted(db, doc_id, account.id)
    if not deleted:
        # Should not happen because we checked above, but handle defensively
        raise NotFoundError(f"Document '{doc_id}' not found for this account.")
