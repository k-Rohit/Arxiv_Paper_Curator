import json
import logging
import re
from typing import Dict, Optional, List, Union
from src.schemas.indexing.models import TextChunk, ChunkMetadata

logger = logging.getLogger(__name__)

class TextChunker:
     """
     Service for chunking text into overlapping segments.
     
     Uses word-based chunking with configurable chunk size and overlap
     Default: 600 words per chunk with 100 word overlap.

     """
     
     def __init__(self
                  ,chunk_size: int = 600
                  ,overlap_size: int = 600
                  ,min_chunk_size: int = 100):
          """Initialize text chunker.

          :param chunk_size: Target number of words per chunk
          :param overlap_size: Number of overlapping words between chunks
          :param min_chunk_size: Minimum words for a chunk to be valid
          """
          
          self.chunk_size = chunk_size
          self.overlap_size = overlap_size
          self.min_chunk_size = min_chunk_size
          
          if overlap_size >= chunk_size:
               raise ValueError("Overlap size must be less than chunk size")
          
          logger.info(
          f"Text chunker initialized: chunk_size={chunk_size}, overlap_size={overlap_size}, min_chunk_size={min_chunk_size}"
          )
     
     def _split_into_words(self, text:str) -> list[str]:
          """Split text into words while preserving whitespace information.
          :param text: Input text
          :returns: List of words
          """  
          return text.split()
     
     def _reconstruct_text(self, words: list[str]) -> str:
          """ 
          Reconstuct the splitted text from the words
          
          :param words: List of words
          :returns: Reconstruct text
          """
          
          return " ".join(words)
     
     def chunk_paper(
          self,
          title: str,
          abstract: str,
          full_text: str,
          arxiv_id: str,
          paper_id: str,
          sections: Optional[Union[Dict[str, str], str, list]] = None,
     ) -> List[TextChunk]:
          pass
          

          

