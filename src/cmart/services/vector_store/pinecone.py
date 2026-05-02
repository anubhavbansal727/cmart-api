from __future__ import annotations

import asyncio
from functools import partial
from typing import Any

from pinecone import Pinecone

from cmart.config import get_settings
from cmart.services.vector_store.base import VectorStoreClient

_UPSERT_BATCH_SIZE = 100


class PineconeVectorStoreClient(VectorStoreClient):
    """Vector store client backed by Pinecone (pinecone-client v3).

    The Pinecone SDK is synchronous, so all blocking calls are dispatched
    to a thread pool via asyncio.get_event_loop().run_in_executor so they
    do not block the event loop.

    Multi-tenant isolation is enforced by always scoping every operation to
    the namespace derived from account_id (UUID string). No cross-namespace
    reads or writes are permitted.

    The underlying index handle is created lazily on first use so that the
    class can be instantiated without I/O at import time.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._pc = Pinecone(api_key=settings.pinecone_api_key)
        self._index_name = settings.pinecone_index_name
        self._index: Any = None  # lazy-initialised in _get_index()

    def _get_index(self) -> Any:
        if self._index is None:
            self._index = self._pc.Index(self._index_name)
        return self._index

    # ------------------------------------------------------------------
    # Internal sync helpers — run inside executor
    # ------------------------------------------------------------------

    def _sync_upsert(self, namespace: str, vectors: list[dict]) -> None:
        index = self._get_index()
        for batch_start in range(0, len(vectors), _UPSERT_BATCH_SIZE):
            batch = vectors[batch_start : batch_start + _UPSERT_BATCH_SIZE]
            index.upsert(vectors=batch, namespace=namespace)

    def _sync_query(
        self,
        namespace: str,
        vector: list[float],
        top_k: int,
    ) -> list[dict]:
        index = self._get_index()
        response = index.query(
            vector=vector,
            top_k=top_k,
            namespace=namespace,
            include_metadata=True,
        )
        results = []
        for match in response.get("matches", []):
            results.append(
                {
                    "id": match["id"],
                    "score": float(match["score"]),
                    "metadata": match.get("metadata", {}),
                }
            )
        return results

    def _sync_delete(self, namespace: str, doc_id: str) -> None:
        index = self._get_index()
        index.delete(filter={"doc_id": doc_id}, namespace=namespace)

    # ------------------------------------------------------------------
    # Public async interface
    # ------------------------------------------------------------------

    async def upsert(self, namespace: str, vectors: list[dict]) -> None:
        """Upsert vectors in batches of 100 into the given namespace."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, partial(self._sync_upsert, namespace, vectors))

    async def query(
        self,
        namespace: str,
        vector: list[float],
        top_k: int = 5,
    ) -> list[dict]:
        """Return top-k nearest neighbours scoped to namespace."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, partial(self._sync_query, namespace, vector, top_k)
        )

    async def delete(self, namespace: str, doc_id: str) -> None:
        """Delete all vectors with metadata.doc_id == doc_id in namespace."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, partial(self._sync_delete, namespace, doc_id))
