from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingClient(ABC):
    """Abstract interface for embedding providers."""

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Embed a single text string and return its vector."""
        ...

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts and return all vectors in the same order."""
        ...
