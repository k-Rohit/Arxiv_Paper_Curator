"""FastAPI application entrypoint.

Builds the app, configures the lifespan (services constructed once at startup
and stored on app.state), wires the request logging middleware, and includes
the routers (added incrementally as they're built).
"""

import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from src.config import get_settings
from src.db.factory import make_database
from src.middlewares import RequestLoggingMiddleware
from src.services.arxiv.factory import make_arxiv_client
from src.services.embeddings.factory import make_openai_embeddings_client
from src.services.opensearch.factory import make_opensearch_client
from src.services.pdf_parser.factory import make_pdf_parser_service
from src.routers import ping
from src.routers import hybrid_search
# from src.routers.ask import ask_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Build singletons at startup, store on app.state, tear down on shutdown."""
    logger.info("Starting RAG API...")

    # Settings + database
    app.state.settings = get_settings()
    app.state.database = make_database()
    logger.info("Database connected")

    # OpenSearch — verify + setup index
    opensearch_client = make_opensearch_client()
    app.state.opensearch_client = opensearch_client
    if opensearch_client.health_check():
        opensearch_client.setup_indices(force=False)
        logger.info("OpenSearch ready and index verified")
    else:
        logger.warning("OpenSearch connection failed — search will not work")

    # Other services
    app.state.arxiv_client       = make_arxiv_client()
    app.state.pdf_parser         = make_pdf_parser_service()
    app.state.embeddings_service = make_openai_embeddings_client()
    logger.info("All services initialized: arxiv, pdf_parser, embeddings")

    logger.info("API ready")
    yield

    # Shutdown
    app.state.database.teardown()
    logger.info("API shutdown complete")


app = FastAPI(
    title="arXiv Paper Curator API",
    description="Personal arXiv CS.AI paper curator with hybrid search + RAG.",
    version=os.getenv("APP_VERSION", "0.1.0"),
    lifespan=lifespan,
)

# Middleware
app.add_middleware(RequestLoggingMiddleware)

# Routers — added incrementally
app.include_router(ping.router,prefix="/api/v1")
app.include_router(hybrid_search.router,  prefix="/api/v1")
# app.include_router(ask_router,            prefix="/api/v1")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
