import logging
from fastapi import APIRouter, HTTPException
from ..dependencies import EmbeddingsDep, OpenSearchDep
from src.schemas.api.search import HybridSearchRequest, SearchHit, SearchResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hybrid-search", tags=["hybrid-search"])

@router.post("/", response_model=SearchResponse)
async def hybrid_search(
    request: HybridSearchRequest, 
    opensearch_client: OpenSearchDep, 
    embeddings_service: EmbeddingsDep,   
) -> SearchResponse:
    
    """
    Hybrid search endpoint supporting multiple search modes.
    """
    try:
        if not opensearch_client.health_check():
            raise HTTPException(status_code=503, detail="Search Service is currently unavailable")
        
        query_embeddings = None
        if request.use_hybrid:
            try:
                query_embeddings = await embeddings_service.embed_text(request.query)
                logger.info("Generated query embedding for hybrid search")
            
            except Exception as e:
                logger.warning(f"Failed to generate embeddings, falling back to BM25: {e}")
        
        logger.info(f"Hybrid search: '{request.query}' (hybrid: {request.use_hybrid and query_embeddings is not None})")
    

        results = opensearch_client.search_unified(
            query=request.query,
            query_embedding=query_embeddings,
            size=request.size,
            from_=request.from_,
            categories=request.categories,
            latest=request.latest_papers,
            use_hybrid=request.use_hybrid,
            min_score=request.min_score,
        )
        
        hits = []
        for hit in results.get("hits",[]):
            hits.append(
                SearchHit(
                    arxiv_id=hit.get("arxiv_id", ""),
                    title=hit.get("title", ""),
                    authors=hit.get("authors"),
                    abstract=hit.get("abstract"),
                    published_date=hit.get("published_date"),
                    pdf_url=hit.get("pdf_url"),
                    score=hit.get("score", 0.0),
                    highlights=hit.get("highlights"),
                    chunk_text=hit.get("chunk_text"),
                    chunk_id=hit.get("chunk_id"),
                    section_name=hit.get("section_name"),
                )
            )
            
        search_response = SearchResponse(
        query=request.query,
        total=results.get("total", 0),
        hits=hits,
        size=request.size,
        **{"from": request.from_},
        search_mode="hybrid" if (request.use_hybrid and query_embeddings is not None) else "bm25",
    )
        logger.info(f"Search completed: {search_response.total} results returned")
        return search_response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during hybrid search: {e}")
        raise HTTPException(status_code=500, detail="An error occurred during search")
            
        
                
            
        
        
            