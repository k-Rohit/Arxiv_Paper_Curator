import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from dateutil import parser as date_parser
from sqlalchemy.orm import Session
from src.config import Settings
from src.exceptions import MetadataFetchingException, PipelineException
from src.repositories.paper import PaperRepository
from src.schemas.arxiv.paper import ArxivPaper, PaperCreate
from src.schemas.pdf_parser.models import ArxivMetadata, ParsedPaper, PdfContent
from src.services.arxiv.client import ArxivClient
from src.services.pdf_parser.parser import PDFParserService

logger = logging.getLogger(__name__)

class MetadataFetcher:
     """Service for fetching arXiv papers with PDF processing and database storage."""
     def __init__(
        self,
        arxiv_client: ArxivClient,
        pdf_parser: PDFParserService,
        pdf_cache_dir: Optional[Path] = None,
        max_concurrent_downloads: int = 5,
        max_concurrent_parsing: int = 3,
        settings: Optional[Settings] = None,
    ):
        """Initialize metadata fetcher with services and settings.

        :param arxiv_client: Client for arXiv API operations
        :param pdf_parser: Service for parsing PDF documents
        :param opensearch_client: Optional OpenSearch client for indexing
        :param pdf_cache_dir: Directory for caching downloaded PDFs
        :param max_concurrent_downloads: Maximum concurrent PDF downloads
        :param max_concurrent_parsing: Maximum concurrent PDF parsing operations
        :param settings: Application settings instance
        :type arxiv_client: ArxivClient
        :type pdf_parser: PDFParserService
        :type opensearch_client: Optional[OpenSearchClient]
        :type pdf_cache_dir: Optional[Path]
        :type max_concurrent_downloads: int
        :type max_concurrent_parsing: int
        :type settings: Optional[Settings]
        """
        from src.config import get_settings

        self.arxiv_client = arxiv_client
        self.pdf_parser = pdf_parser
        self.pdf_cache_dir = pdf_cache_dir or self.arxiv_client.pdf_cache_dir
        self.max_concurrent_downloads = max_concurrent_downloads
        self.max_concurrent_parsing = max_concurrent_parsing
        self.settings = settings or get_settings()

     
     