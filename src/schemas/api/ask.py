from pydantic import BaseModel, Field
from typing import List, Optional

class AskRequest(BaseModel):
    """Request model for RAG question answering."""
    
    query: str = Field(...,description="The user's question or query.",min_length=1,max_length=1000)
    top_k: Optional[int] = Field(5, description="Number of top relevant documents to retrieve for answering the query.", ge=1, le=10)
    use_hybrid: bool = Field(True, description="Use hybrid search (BM25 + vector)")
    categories: Optional[List[str]] = Field(None, description="Filter by arxiv categories")
    
    class Config:
        json_schema_extra = {
        "example": {
        "query": "What are transformers in machine learning?",
        "top_k": 3,
        "use_hybrid": True,
        "categories": ["cs.AI", "cs.LG"],
        }
    }


class AskResponse(BaseModel):
    """Response model for RAG question answering."""

    query: str = Field(..., description="Original user question")
    answer: str = Field(..., description="Generated answer from LLM")
    sources: List[str] = Field(..., description="PDF URLs of source papers")
    chunks_used: int = Field(..., description="Number of chunks used for generation")
    search_mode: str = Field(..., description="Search mode used: bm25 or hybrid")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "What are transformers in machine learning?",
                "answer": "Transformers are a neural network architecture...",
                "sources": ["https://arxiv.org/pdf/1706.03762.pdf", "https://arxiv.org/pdf/1810.04805.pdf"],
                "chunks_used": 3,
                "search_mode": "hybrid",
            }
        }