from functools import lru_cache

from src.config import get_settings

from .client import ArxivClient


@lru_cache(maxsize=1)
def make_arxiv_client() -> ArxivClient:
    """Factory function to create an arXiv client instance.

    Cached so every caller shares ONE client. This matters: the client tracks
    `_last_request_time` per instance to honour arXiv's ~1 req/3s limit. Two
    instances would each keep their own timer and could fire back-to-back
    requests, risking a temporary ban.

    :returns: An instance of the arXiv client
    :rtype: ArxivClient
    """
    settings = get_settings()
    client = ArxivClient(settings=settings.arxiv)
    
    return client
    
     