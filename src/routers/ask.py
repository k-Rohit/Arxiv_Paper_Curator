"""RAG Q&A endpoint — retrieve relevant chunks, ground an LLM, return an answer."""

import logging

from fastapi import APIRouter, HTTPException

from src.dependencies import EmbeddingsDep, LLMDep, OpenSearchDep
from src.schemas.api.ask import AskRequest, AskResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ask"])


@router.post("/ask", response_model=AskResponse)
async def ask(
    request: AskRequest,
    opensearch: OpenSearchDep,
    embedder: EmbeddingsDep,
    llm: LLMDep,
) -> AskResponse:
    """Answer a question grounded in retrieved arXiv paper chunks.

    1. Embed the user query (for hybrid search).
    2. Retrieve top-K relevant chunks from OpenSearch.
    3. Build a prompt with chunks as context, call the LLM.
    4. Return the answer + sources.
    """
    # 1. Embed the query if hybrid search is requested
    query_embedding = None
    search_mode = "bm25"
    if request.use_hybrid:
        try:
            query_embedding = await embedder.embed_text(request.query)
            search_mode = "hybrid"
        except Exception as e:
            logger.warning(f"Embedding failed, falling back to BM25: {e}")

    # 2. Retrieve top-K chunks
    logger.info(f"Retrieving top {request.top_k} chunks for query: '{request.query[:60]}'")
    search_results = opensearch.search_unified(
        query=request.query,
        query_embedding=query_embedding,
        size=request.top_k,
        from_=0,
        categories=request.categories,
        use_hybrid=request.use_hybrid and query_embedding is not None,
        min_score=0.0,
    )

    hits = search_results.get("hits", [])
    if not hits:
        raise HTTPException(status_code=404, detail="No relevant papers found for this query.")

    # 3. Build chunks for the LLM (minimal payload — text + arxiv_id only)
    chunks_for_llm = [
        {
            "arxiv_id":   hit.get("arxiv_id", ""),
            "chunk_text": hit.get("chunk_text", hit.get("abstract", "")),
        }
        for hit in hits
    ]

    # 4. Call the LLM
    try:
        rag_result = await llm.generate_rag_response(query=request.query, chunks=chunks_for_llm)
    except Exception as e:
        logger.error(f"LLM generation failed: {e}")
        raise HTTPException(status_code=502, detail=f"LLM generation failed: {e}")

    # 5. Build the response — extract unique source URLs from hits
    sources = list({hit.get("pdf_url", "") for hit in hits if hit.get("pdf_url")})

    return AskResponse(
        query=request.query,
        answer=rag_result.get("answer", ""),
        sources=sources,
        chunks_used=len(hits),
        search_mode=search_mode,
    )
