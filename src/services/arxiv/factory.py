from src.config import get_settings
from .client import ArxivClient

def make_arxiv_client() -> ArxivClient:
    """Factory function to create an arXiv client instance.

    :returns: An instance of the arXiv client
    :rtype: ArxivClient
    """
    settings = get_settings()
    client = ArxivClient(settings=settings.arxiv)
    
    return client
    
     