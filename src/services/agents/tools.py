import logging

from langchain_core.documents import Document
from langchain_core.tools import tool

from src.services.embeddings.openai_client import OpenAIEmbeddingsClient
from src.services.opensearch.client import OpenSearchClient

logger = logging.getLogger(__name__)

def create_retriever_tool(
    opensearch_clent: OpenSearchClient,
    embeddings_client: OpenAIEmbeddingsClient,
    top_k: int = 3,
    use_hybrid: bool = True
):
    """Create a retriever tool that wraps OpenSearch service.

    :param opensearch_client: Existing OpenSearch service
    :param embeddings_client: Existing Jina embeddings service
    :param top_k: Number of chunks to retrieve
    :param use_hybrid: Use hybrid search (BM25 + vector)
    :returns: LangChain tool for retrieving papers
    """
    
    @tool
    async def retrieve_papers(query: str) -> list[Document]:
        
        """Search and return relevant arXiv research papers.

        Use this tool when the user asks about:
            - Machine learning concepts or techniques
            - Deep learning architectures
            - Natural language processing
            - Computer vision methods
            - AI research topics
            - Specific algorithms or models

            :param query: The search query describing what papers to find
            :returns: List of relevant paper excerpts with metadata
        """
        logger.info(f"Retrieving papers for the query: {query[:100]}")
        logger.debug(f"Search mode: {'hybrid' if use_hybrid else 'bm25'}, top_k: {top_k}")
        
        # Generate query embeddings
        logger.debug("Generating query embedding")
        query_embeddings = await embeddings_client.embed_text(text=query)
        logger.debug(f"Generated embedding with {len(query_embeddings)} dimensions")
        
        # Search using OpenSearch
        logger.debug("Searching OpenSearch")
        search_results = opensearch_clent.search_unified(
            query=query,
            query_embedding=query_embeddings,
            size=top_k,
            use_hybrid=use_hybrid
        )
        
        # Convert SearchHit to Langchain Document
        documents = []
        hits = search_results.get("hits", [])
        logger.info(f"Found {len(hits)} documents from OpenSearch")
        
        for hit in hits:
            doc = Document(
                page_content=hit['chunk_text'],
                metadata = {
                    "arxiv_id": hit["arxiv_id"],
                    "title": hit.get("title",""),
                    "authors": hit.get("authors",""),
                    "score": hit.get("score", 0.0),
                    "source": f"https://arxiv.org/pdf/{hit['arxiv_id']}.pdf",
                    "section": hit.get("section_name",""),
                    "search_mode": "hybrid" if use_hybrid else "bm25",
                    "top_k": top_k
                }
            )
            documents.append(doc)
        logger.debug(f"Converted {len(documents)} hits to Langchain Documents.")
        logger.info(f"✓ Retrieved {len(documents)} papers successfully")
        
        return documents
    return retrieve_papers
        
        
        