from typing import Optional

from src.config import Settings, get_settings
from src.services.embeddings.factory import make_openai_embeddings_client
from src.services.opensearch.factory import make_opensearch_client_fresh

from .hybrid_indexer import HybridIndexingService
from .text_chunker import TextChunker


def make_hybrid_indexing_service(
    settings: Optional[Settings] = None, opensearch_host: Optional[str] = None
) -> HybridIndexingService:
    """Factory function to create hybrid indexing service.

    Creates a new service instance each time (not cached — the Airflow task
    calls it once per run).

    :param settings: Optional settings instance
    :param opensearch_host: Optional OpenSearch host override
    :returns: HybridIndexingService instance
    """
    if settings is None:
        settings = get_settings()

    chunker           = TextChunker()  # defaults: 600 words, 100 overlap
    embeddings_client = make_openai_embeddings_client()
    opensearch_client = make_opensearch_client_fresh(settings, host=opensearch_host)

    return HybridIndexingService(
        chunker=chunker,
        embeddings_client=embeddings_client,
        opensearch_client=opensearch_client,
    )
