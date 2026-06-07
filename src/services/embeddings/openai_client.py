"""OpenAI embeddings client (async)."""

import logging
from typing import List
from openai import AsyncOpenAI
from src.config import OpenAIEmbeddingsSettings

logger = logging.getLogger(__name__)


class OpenAIEmbeddingsClient:
    """Async client for OpenAI text embeddings."""

    def __init__(self, settings: OpenAIEmbeddingsSettings):
        self.settings = settings
        self._client = AsyncOpenAI(
            max_retries=settings.max_retries,
            timeout=settings.timeout_seconds,
        )
        logger.info(
            f"OpenAI embeddings client initialized: "
            f"model={settings.model}, dimensions={settings.dimensions}"
        )

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed multiple texts in one API call. Returns one vector per input."""
        if not texts:
            return []

        response = await self._client.embeddings.create(
            model=self.settings.model,
            input=texts,
            dimensions=self.settings.dimensions,
        )

        return [item.embedding for item in response.data]

    async def embed_text(self, text: str) -> List[float]:
        """Embed a single string. Returns one vector."""
        vectors = await self.embed_batch([text])
        return vectors[0]
