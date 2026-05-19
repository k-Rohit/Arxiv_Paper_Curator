from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class ParserType(str, Enum):
     """ PDF parser types options """
     DOCKLING = "docling"

class PaperSection(BaseModel):
     """Represents a section of a paper."""
     title: str = Field(...,description="Section title")
     content: str = Field(..., description="Section content")
     level: int = Field(default=1, description="Section hierarchy level")
     

