"""FastAPI dependency injection helpers.

Services are constructed once at app startup (see main.py's lifespan) and
stored on `app.state`. Each request gets them via FastAPI's DI system.

Routes import the `*Dep` aliases below and use them as type-annotated
parameters. FastAPI auto-injects the dependency at call time.

Example:
    @router.get("/")
    def my_endpoint(opensearch: OpenSearchDep, db: SessionDep):
        ...
"""

from functools import lru_cache
from typing import Annotated, Generator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from src.config import Settings
from src.db.interfaces.base import BaseDatabase
from src.services.arxiv.client import ArxivClient
from src.services.cache.client import CacheClient
from src.services.embeddings.openai_client import OpenAIEmbeddingsClient
from src.services.openai_.client import OpenAIClient
from src.services.opensearch.client import OpenSearchClient
from src.services.pdf_parser.parser import PDFParserService


# ─── Settings ───────────────────────────────────────────────────────────

@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()


def get_request_settings(request: Request) -> Settings:
    """Get settings from the request's app state."""
    return request.app.state.settings


# ─── Database ───────────────────────────────────────────────────────────

def get_database(request: Request) -> BaseDatabase:
    """Get the database instance from app state."""
    return request.app.state.database


def get_db_session(
    database: Annotated[BaseDatabase, Depends(get_database)],
) -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session, committing on success and rolling back on error."""
    with database.get_session() as session:
        yield session


# ─── Services (singletons stored on app.state at startup) ───────────────

def get_opensearch_client(request: Request) -> OpenSearchClient:
    """Get the shared OpenSearch client."""
    return request.app.state.opensearch_client


def get_arxiv_client(request: Request) -> ArxivClient:
    """Get the shared arXiv client."""
    return request.app.state.arxiv_client


def get_pdf_parser(request: Request) -> PDFParserService:
    """Get the shared PDF parser service."""
    return request.app.state.pdf_parser


def get_embeddings_service(request: Request) -> OpenAIEmbeddingsClient:
    """Get the shared OpenAI embeddings client."""
    return request.app.state.embeddings_service


def get_llm_client(request: Request) -> OpenAIClient:
    """Get the shared OpenAI LLM (chat-completion) client."""
    return request.app.state.llm_client


def get_cache(request: Request) -> CacheClient | None:
    """Get the shared cache client (may be None if Redis is unavailable)."""
    return request.app.state.cache


# ─── Annotated type aliases (what routes actually use) ──────────────────

SettingsDep    = Annotated[Settings, Depends(get_request_settings)]
DatabaseDep    = Annotated[BaseDatabase, Depends(get_database)]
SessionDep     = Annotated[Session, Depends(get_db_session)]
OpenSearchDep  = Annotated[OpenSearchClient, Depends(get_opensearch_client)]
ArxivDep       = Annotated[ArxivClient, Depends(get_arxiv_client)]
PDFParserDep   = Annotated[PDFParserService, Depends(get_pdf_parser)]
EmbeddingsDep  = Annotated[OpenAIEmbeddingsClient, Depends(get_embeddings_service)]
LLMDep         = Annotated[OpenAIClient, Depends(get_llm_client)]
CacheDep       = Annotated[CacheClient | None, Depends(get_cache)]
