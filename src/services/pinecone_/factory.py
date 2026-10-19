from functools import lru_cache

from src.config import get_settings
from src.services.pinecone_.client import PineconeClient


@lru_cache(maxsize=1)
def make_pinecone_client() -> PineconeClient:
    return PineconeClient(settings=get_settings().pinecone_)
