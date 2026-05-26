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
        :param pdf_cache_dir: Directory for caching downloaded PDFs
        :param max_concurrent_downloads: Maximum concurrent PDF downloads
        :param max_concurrent_parsing: Maximum concurrent PDF parsing operations
        :param settings: Application settings instance
        """
        from src.config import get_settings

        self.arxiv_client = arxiv_client
        self.pdf_parser = pdf_parser
        self.pdf_cache_dir = pdf_cache_dir or self.arxiv_client.pdf_cache_dir
        self.max_concurrent_downloads = max_concurrent_downloads
        self.max_concurrent_parsing = max_concurrent_parsing
        self.settings = settings or get_settings()

    async def fetch_and_process_papers(
        self,
        max_results: Optional[int] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        process_pdfs: bool = True,
        store_to_db: bool = True,
        db_session: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """
        Fetch papers from arXiv, process PDFs, and store to database.

        :param max_results: Maximum papers to fetch
        :param from_date: Filter papers from this date (YYYYMMDD)
        :param to_date: Filter papers to this date (YYYYMMDD)
        :param process_pdfs: Whether to download and parse PDFs
        :param store_to_db: Whether to store results in database
        :param db_session: Database session (required if store_to_db=True)
        :returns: Dictionary with processing results and statistics
        """
        results = {
            "papers_fetched": 0,
            "pdfs_downloaded": 0,
            "pdfs_parsed": 0,
            "papers_stored": 0,
            "papers_indexed": 0,
            "errors": [],
            "processing_time": 0,
        }

        start_time = datetime.now()

        try:
            # Step 1: fetch metadata from arXiv
            papers = await self.arxiv_client.fetch_papers(
                max_results=max_results,
                from_date=from_date,
                to_date=to_date,
                sort_by="submittedDate",
                sort_order="descending",
            )

            results["papers_fetched"] = len(papers)
            if not papers:
                logger.warning("No papers found")
                return results

            # Step 2: process PDFs if requested
            pdf_results = {}
            if process_pdfs:
                pdf_results = await self._process_pdfs_batch(papers)
                results["pdfs_downloaded"] = pdf_results["downloaded"]
                results["pdfs_parsed"] = pdf_results["parsed"]
                results["errors"].extend(pdf_results["errors"])

            # Step 3: store to database if requested
            if store_to_db and db_session:
                logger.info("Storing papers to database...")
                stored_count = self._store_papers_to_db(
                    papers,
                    pdf_results.get("parsed_papers", {}),
                    db_session,
                )
                results["papers_stored"] = stored_count
            elif store_to_db:
                logger.warning("Database storage requested but no session provided")
                results["errors"].append("Database session not provided for storage")

            # Step 4: bookkeeping
            processing_time = (datetime.now() - start_time).total_seconds()
            results["processing_time"] = processing_time

            logger.info(
                f"Pipeline completed in {processing_time:.1f}s: "
                f"{results['papers_fetched']} papers, "
                f"{results['pdfs_downloaded']} PDFs, "
                f"{len(results['errors'])} errors"
            )

            if results["errors"]:
                logger.warning("Errors summary:")
                for i, error in enumerate(results["errors"][:5], 1):
                    logger.warning(f"  {i}. {error}")
                if len(results["errors"]) > 5:
                    logger.warning(f"  ... and {len(results['errors']) - 5} more errors")

            return results

        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            results["errors"].append(f"Pipeline error: {str(e)}")
            raise PipelineException(f"Pipeline execution failed: {e}") from e
