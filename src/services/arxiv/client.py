import asyncio
import logging
import time
import xml.etree.ElementTree as ET
from functools import cached_property
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote, urlencode

import httpx
from src.config import ArxivSettings
from src.exceptions import ArxivAPIException, ArxivAPIRateLimitError, ArxivAPITimeoutError, ArxivParseError, PDFDownloadException, PDFDownloadTimeoutError
from src.schemas.arxiv.paper import ArxivPaper

logger = logging.getLogger(__name__)

class ArxivClient:
     '''
     Client for fetching papers from arxiv API
     '''
     
     def __init__(self, settings:ArxivSettings):
          self._settings = settings
          self.__last_request_time: Optional[float] = None
     
     @cached_property
     def pdf_cache_dir(self) -> Path:
          cache_dir = Path(self._settings.pdf_cache_dir)
          cache_dir.mkdir(parents=True,exist_ok=True)
          return cache_dir
     
     @property
     def get_base_url(self) -> str:
          return self._settings.base_url
     
     @property
     def get_namespaces(self) -> str:
          return self._settings.namespaces

     @property
     def get_rate_limit_delay(self) -> float:
          return self._settings.rate_limit_delay

     @property
     def get_timeout_seconds(self) -> int:
          return self._settings.timeout_seconds

     @property
     def get_max_results(self) -> int:
          return self._settings.max_results

     @property
     def get_search_category(self) -> str:
          return self._settings.search_category
     
     async def fetch_papers(
          self,
          max_results: Optional[int] = None,
          start: int = 0,
          sort_by: str = "submittedDate",
          sort_order: str = "descending",
          from_date: Optional[str] = None,
          to_date: Optional[str] = None,
     ) -> List[ArxivPaper]:
          """Fetch papers from arXiv for the configured category.

          Args:
                    max_results: Maximum number of papers to fetch (uses settings default if None)
                    start: Starting index for pagination
                    sort_by: Sort criteria (submittedDate, lastUpdatedDate, relevance)
                    sort_order: Sort order (ascending, descending)
                    from_date: Filter papers submitted after this date (format: YYYYMMDD)
                    to_date: Filter papers submitted before this date (format: YYYYMMDD)

          Returns:
               List of ArxivPaper objects for the configured category

          """
          if max_results is None:
               max_results = self.get_max_results
          
          # Build search query
          search_query = f"cat:{self.get_search_category}"
          
          # Add date filtering if provided
          if from_date or to_date:
          # Convert dates to arXiv format (YYYYMMDDHHMM) - use 0000 for start of day, 2359 for end
            date_from = f"{from_date}0000" if from_date else "*"
            date_to = f"{to_date}2359" if to_date else "*"
            # Use correct arXiv API syntax with + symbols
            search_query += f" AND submittedDate:[{date_from}+TO+{date_to}]"

          params = {
               "search_query": search_query,
               "start": start,
               "max_results": min(max_results, 2000),
               "sortBy": sort_by,
               "sortOrder": sort_order,
          }

          safe = ":+[]"  # Don't encode :, +, [, ] characters needed for arXiv queries
          url = f"{self.base_url}?{urlencode(params, quote_via=quote, safe=safe)}"
          
          try:
               logger.info(f"Fetching {max_results} {self.get_search_category} papers from arxiv")
               
               if self.__last_request_time is not None:
                    time_since_last_req = time.time() - self.__last_request_time
                    if time_since_last_req < self.get_rate_limit_delay:
                         sleep_time = self.get_rate_limit_delay - time_since_last_req
                         await asyncio.sleep(sleep_time)
               
               self.__last_request_time = time.time()
               
               async with httpx.AsyncClient(timeout=self.get_timeout_seconds) as client:
                    response = await client.get(url)
                    response.raise_for_status()
                    xml_data = response.text
               
               papers = self._parse_response(xml_data)
               logger.info(f"Fetched {len(papers)} papers.")
          
          except httpx.TimeoutException as e:
               logger.error(f"arXiv API timeout: {e}")
               raise ArxivAPITimeoutError(f"arXiv API request timed out: {e}")
          
          except httpx.HTTPStatusError as e:
               logger.error(f"arXiv API HTTP error: {e}")
               raise ArxivAPIException(f"arXiv API returned error {e.response.status_code}: {e}")
          except Exception as e:
            logger.error(f"Failed to fetch papers from arXiv: {e}")
            raise ArxivAPIException(f"Unexpected error fetching papers from arXiv: {e}")
               
     async def fetch_papers_with_query(
        self,
        search_query: str,
        max_results: Optional[int] = None,
        start: int = 0,
        sort_by: str = "submittedDate",
        sort_order: str = "descending",
    ) -> List[ArxivPaper]:
        """
        Fetch papers from arXiv using a custom search query.

        Args:
            search_query: Custom arXiv search query (e.g., "cat:cs.AI AND submittedDate:[20240101 TO 20241231]")
            max_results: Maximum number of papers to fetch (uses settings default if None)
            start: Starting index for pagination
            sort_by: Sort criteria (submittedDate, lastUpdatedDate, relevance)
            sort_order: Sort order (ascending, descending)

        Returns:
            List of ArxivPaper objects matching the search query

        Examples:
            # Papers from last 30 days
            "cat:cs.AI AND submittedDate:[20240101 TO *]"

            # Papers by specific author
            "au:LeCun AND cat:cs.AI"

            # Papers with specific keywords in title
            "ti:transformer AND cat:cs.AI"
        """
        if max_results is None:
            max_results = self.max_results

        params = {
            "search_query": search_query,
            "start": start,
            "max_results": min(max_results, 2000),
            "sortBy": sort_by,
            "sortOrder": sort_order,
        }

        safe = ":+[]*"  # Don't encode :, +, [, ], *, characters needed for arXiv queries
        url = f"{self.base_url}?{urlencode(params, quote_via=quote, safe=safe)}"

        try:
            # Add rate limiting delay between all requests (arXiv recommends 3 seconds)
            if self._last_request_time is not None:
                time_since_last = time.time() - self._last_request_time
                if time_since_last < self.rate_limit_delay:
                    sleep_time = self.rate_limit_delay - time_since_last
                    await asyncio.sleep(sleep_time)

            self._last_request_time = time.time()

            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(url)
                response.raise_for_status()
                xml_data = response.text

            papers = self._parse_response(xml_data)
            logger.info(f"Query returned {len(papers)} papers")

            return papers

        except httpx.TimeoutException as e:
            logger.error(f"arXiv API timeout: {e}")
            raise ArxivAPITimeoutError(f"arXiv API request timed out: {e}")
        except httpx.HTTPStatusError as e:
            logger.error(f"arXiv API HTTP error: {e}")
            raise ArxivAPIException(f"arXiv API returned error {e.response.status_code}: {e}")
        except Exception as e:
            logger.error(f"Failed to fetch papers from arXiv: {e}")
            raise ArxivAPIException(f"Unexpected error fetching papers from arXiv: {e}")
               
     async def fetch_paper_by_id(self,arxiv_id: str) -> Optional[ArxivPaper]:
          
        """
        Fetch a specific paper by its arXiv ID.

        Args:
            arxiv_id: arXiv paper ID (e.g., "2507.17748v1" or "2507.17748")

        Returns:
            ArxivPaper object or None if not found
        """ 
        # clean the arxiv id
        clean_id = arxiv_id.split('v')[0] if "v" in arxiv_id else arxiv_id
        params = {
             "id_list":clean_id,
             "max_results" : 1
        }
        safe = ":+[]*" # Don't ecode these characters, these are needed for query
        url = f"{self.get_base_url}?{urlencode(params,safe=safe,quote_via=quote)}"
        
        try:
             async with httpx.AsyncClient() as client:
                  response = await client.get(url=url)
                  response.raise_for_status()
                  xml_data = response.text
             papers = self._parse_response(xml_data)
             
             if papers:
                  return papers[0]
             else:
                  logger.warning(f"Paper {arxiv_id} not found")
                  return None
        except httpx.TimeoutException as e:
            logger.error(f"arXiv API timeout for paper {arxiv_id}: {e}")
            raise ArxivAPITimeoutError(f"arXiv API request timed out for paper {arxiv_id}: {e}")
        except httpx.HTTPStatusError as e:
            logger.error(f"arXiv API HTTP error for paper {arxiv_id}: {e}")
            raise ArxivAPIException(f"arXiv API returned error {e.response.status_code} for paper {arxiv_id}: {e}")
        except Exception as e:
            logger.error(f"Failed to fetch paper {arxiv_id} from arXiv: {e}")
            raise ArxivAPIException(f"Unexpected error fetching paper {arxiv_id} from arXiv: {e}")
     
     def _parse_response(self, xml_data: str) -> List[ArxivPaper]:
          
          try:
               root = ET.fromstring(xml_data)
               entries = root.findall("atom:entry",self.get_namespaces)
               
               papers = []
               for entry in entries:
                    paper = self._parse_single_entry(entry)
                    if paper:
                         papers.append(paper)
               
               return papers
          except ET.ParseError as e:
               logger.error(f"Failed to parse arXiv XML response: {e}")
               raise ArxivParseError(f"Failed to parse arXiv XML response: {e}")
          except Exception as e:
               logger.error(f"Unexpected error parsing arXiv response: {e}")
               raise ArxivParseError(f"Unexpected error parsing arXiv response: {e}")
     
     def _parse_single_entry(self,entry:ET.Element) -> Optional[ArxivPaper]:
          """ 
          Parse a single entry from arxiv XML response
          
          Args:
               entry: XML text
          Returns:
               ArxivPaper object or None if parsing fails
          """ 
          try:
               arxiv_id = self._get_arxiv_id(entry)
               if not arxiv_id:
                    return None
               title = self._get_text(entry,"atom:title",clean_newlines=True)
               authors = self._get_authors(entry)
               abstract = self.get_text(entry,"atom:summary",clean_newlines=True)
               published = self._get_text(entry,"atom:published")
               categories = self._get_categories(entry)
               pdf_url = self._get_pdf_url(entry)
               
               return ArxivPaper(
                    arxiv_id=arxiv_id,
                    title=title,
                    authors=authors,
                    abstract=abstract,
                    published_date=published,
                    categories=categories,
                    pdf_url=pdf_url
               )
          except Exception as e:
               logger.error(f"Failed to parse entry: {e}")
               return None
          


