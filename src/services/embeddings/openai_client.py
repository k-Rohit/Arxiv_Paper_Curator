"""OpenAI embeddings client (async)."""

import logging
from typing import List

from openai import AsyncOpenAI

from src.config import OpenAIEmbeddingsSettings

logger = logging.getLogger(__name__)


class OpenAIEmbeddingsClient:
     
    """Async client for OpenAI text embeddings.

    Wraps the async OpenAI SDK to produce vectors from text. Auto-batches
    large inputs to stay within OpenAI's per-request limits.
    """

    def __init__(self, settings: OpenAIEmbeddingsSettings):
        self.settings = settings
        self._client = AsyncOpenAI(
            api_key=settings.api_key or None,  # None lets SDK fall back to OPENAI_API_KEY env var
            max_retries=settings.max_retries,
            timeout=settings.timeout_seconds,
        )
        logger.info(
            f"OpenAI embeddings client initialized: "
            f"model={settings.model}, dimensions={settings.dimensions}"
        )

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed multiple texts. Auto-batches into groups of self.settings.batch_size.

        :param texts: List of input strings.
        :returns: One vector per input, in the same order.
        """
        if not texts:
            return []

        batch_size = self.settings.batch_size
        all_vectors: List[List[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]

            response = await self._client.embeddings.create(
                model=self.settings.model,
                input=batch,
                dimensions=self.settings.dimensions,
            )

            all_vectors.extend(item.embedding for item in response.data)

        num_batches = (len(texts) + batch_size - 1) // batch_size
        logger.info(f"Embedded {len(texts)} texts in {num_batches} batch(es)")

        return all_vectors

    async def embed_text(self, text: str) -> List[float]:
        """Embed a single string.

        :param text: Input string.
        :returns: One vector.
        """
        vectors = await self.embed_batch([text])
        return vectors[0]
