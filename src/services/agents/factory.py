"""Factory for the AgenticRag service (singleton)."""

from functools import lru_cache

from src.services.embeddings.factory import make_openai_embeddings_client
from src.services.openai_.factory import make_openai_client
from src.services.opensearch.factory import make_opensearch_client

from .agentic_rag import AgenticRag
from .config import GraphConfig


@lru_cache(maxsize=1)
def make_agentic_rag() -> AgenticRag:
    """Build and return the singleton AgenticRag service.

    Wires all client dependencies (OpenSearch, embeddings, LLM) via their own
    factories, plus a default GraphConfig. Called once at app startup.
    """
    return AgenticRag(
        opensearch=make_opensearch_client(),
        openaiembeddings=make_openai_embeddings_client(),
        openai_=make_openai_client(),
        graph_config=GraphConfig(),
    )
