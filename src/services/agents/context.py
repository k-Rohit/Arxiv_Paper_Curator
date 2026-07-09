"""Runtime DI bundle handed to every node in the LangGraph workflow.

Nodes read services (clients) and config values from this object instead of
importing module-level globals. Makes testing easy — inject fake clients.
"""

from pydantic import BaseModel, ConfigDict

from src.services.embeddings.openai_client import OpenAIEmbeddingsClient
from src.services.openai_ import OpenAIClient
from src.services.opensearch.client import OpenSearchClient

from .config import GraphConfig


class Context(BaseModel):
    """The dependencies + config every node needs at runtime."""

    # Services (clients built once at app startup)
    opensearch_client: OpenSearchClient
    embeddings_client: OpenAIEmbeddingsClient
    openai_client:     OpenAIClient

    # Config (tunables — top_k, temperature, threshold, …)
    graph_config: GraphConfig

    # Pydantic needs this because OpenSearchClient etc. aren't pure Pydantic types
    model_config = ConfigDict(arbitrary_types_allowed=True)
