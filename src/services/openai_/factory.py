"""Factory for the OpenAI LLM client."""

from functools import lru_cache

from src.config import get_settings
from src.services.openai_.client import OpenAIClient


@lru_cache(maxsize=1)
def make_openai_client() -> OpenAIClient:
    """Create and return a singleton OpenAI LLM client.

    :returns: Configured OpenAIClient
    """
    settings = get_settings()
    return OpenAIClient(settings.openai_client)
