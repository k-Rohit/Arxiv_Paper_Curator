from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

class ArxivPaper(BaseModel):
     '''
     Schema for the Arxiv API response
     '''
     arxiv_id: str = Field(..., description="Arxiv Paper Id")
     title: str = Field(..., description="Paper title")
     authors: List[str] = Field(...,description="Paper abstract")
     abstract: str = Field(..., description="Paper abstract")
     published_date: str = Field(..., description="Date published on arXiv (ISO format)")
     categories: List[str] = Field(...,description="Paper categories")
     pdf_url: str = Field(..., description="URL to PDF")

class PaperBase(BaseModel):
    # Core arXiv metadata
    arxiv_id: str = Field(..., description="arXiv paper ID")
    title: str = Field(..., description="Paper title")
    authors: List[str] = Field(..., description="List of author names")
    abstract: str = Field(..., description="Paper abstract")
    categories: List[str] = Field(..., description="Paper categories")
    published_date: datetime = Field(..., description="Date published on arXiv")
    pdf_url: str = Field(..., description="URL to PDF")

