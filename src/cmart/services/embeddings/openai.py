from __future__ import annotations

import openai

from cmart.config import get_settings
from cmart.services.embeddings.base import EmbeddingClient

_MODEL = "text-embedding-3-small"
_BATCH_SIZE = 100


class OpenAIEmbeddingClient(EmbeddingClient):
    """Embedding client backed by OpenAI text-embedding-3-small.

    Batches up to 100 texts per API call to stay within OpenAI rate limits.
    All results are returned in the same order as the input list.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        self._dimensions = settings.pinecone_vector_dim

    async def embed(self, text: str) -> list[float]:
        """Embed a single text string."""
        results = await self.embed_batch([text])
        return results[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts, batching into groups of up to 100.

        Returns all embeddings in input order.
        """
        if not texts:
            return []

        all_embeddings: list[list[float]] = []

        for batch_start in range(0, len(texts), _BATCH_SIZE):
            batch = texts[batch_start : batch_start + _BATCH_SIZE]
            response = await self._client.embeddings.create(
                model=_MODEL,
                input=batch,
                dimensions=self._dimensions,
            )
            # OpenAI returns embeddings sorted by their index in the request
            sorted_data = sorted(response.data, key=lambda item: item.index)
            all_embeddings.extend(item.embedding for item in sorted_data)

        return all_embeddings
