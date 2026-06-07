"""Factory for the OpenAI embeddings client."""

from functools import lru_cache
from typing import Optional

from src.config import OpenAIEmbeddingsSettings, get_settings

from .openai_client import OpenAIEmbeddingsClient


@lru_cache(maxsize=1)
def make_openai_embeddings_client(
    settings: Optional[OpenAIEmbeddingsSettings] = None,
) -> OpenAIEmbeddingsClient:
    """Create a cached OpenAI embeddings client (singleton).

    :param settings: Optional settings override. Defaults to global settings.
    :returns: Cached OpenAIEmbeddingsClient instance.
    """
    if settings is None:
        settings = get_settings().openai_embeddings

    return OpenAIEmbeddingsClient(settings=settings)
