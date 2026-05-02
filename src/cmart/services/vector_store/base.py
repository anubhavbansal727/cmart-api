from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class VectorStoreClient(ABC):
    """Abstract interface for vector store providers.

    All methods are namespaced by account_id to enforce multi-tenant isolation.
    A namespace must always be supplied — never query across the full index.
    """

    @abstractmethod
    async def upsert(self, namespace: str, vectors: list[dict[str, Any]]) -> None:
        """Write or overwrite a batch of vectors in the given namespace.

        Each dict in *vectors* must have the shape:
            {"id": str, "values": list[float], "metadata": dict}
        """
        ...

    @abstractmethod
    async def query(
        self,
        namespace: str,
        vector: list[float],
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Return the top-k nearest neighbours from *namespace*.

        Each returned dict has the shape:
            {"id": str, "score": float, "metadata": dict}
        """
        ...

    @abstractmethod
    async def delete(self, namespace: str, doc_id: str) -> None:
        """Delete all vectors whose metadata.doc_id equals *doc_id*."""
        ...
