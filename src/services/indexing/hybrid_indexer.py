"""Hybrid indexing service: chunk papers, embed chunks, upsert into Pinecone."""

import logging

from langsmith import traceable

from src.services.embeddings.openai_client import OpenAIEmbeddingsClient
from src.services.pinecone_.client import PineconeClient

from .text_chunker import TextChunker

logger = logging.getLogger(__name__)


class HybridIndexingService:
    """Indexes papers with chunking + embeddings for hybrid (sparse + dense) search.

    Pipeline per paper:
        1. Chunk paper into overlapping section-aware segments
        2. Generate dense embeddings for each chunk (OpenAI)
        3. Upsert into Pinecone (which adds the sparse keyword vectors)
    """

    def __init__(
        self,
        chunker: TextChunker,
        embeddings_client: OpenAIEmbeddingsClient,
        pinecone_client: PineconeClient,
    ) -> None:
        self.chunker = chunker
        self.embeddings_client = embeddings_client
        self.pinecone_client = pinecone_client
        logger.info("Hybrid indexing service initialized")

    @traceable(name="index_paper")
    async def index_paper(self, paper_data: dict) -> dict[str, int]:
        """Index a single paper with chunking and embeddings."""
        arxiv_id = paper_data.get("arxiv_id")
        paper_id = str(paper_data.get("id", ""))

        if not arxiv_id:
            logger.error("Paper missing arxiv_id")
            return {"chunks_created": 0, "chunks_indexed": 0, "embeddings_generated": 0, "errors": 1}

        try:
            # 1. Chunk
            chunks = self.chunker.chunk_paper(
                title=paper_data.get("title", ""),
                abstract=paper_data.get("abstract", ""),
                full_text=paper_data.get("raw_text", paper_data.get("full_text", "")),
                arxiv_id=arxiv_id,
                paper_id=paper_id,
                sections=paper_data.get("sections"),
            )

            if not chunks:
                logger.warning(f"No chunks created for paper {arxiv_id}")
                return {"chunks_created": 0, "chunks_indexed": 0, "embeddings_generated": 0, "errors": 0}

            logger.info(f"Created {len(chunks)} chunks for paper {arxiv_id}")

            # 2. Embed (auto-batched inside the client per settings.batch_size)
            chunk_texts = [chunk.text for chunk in chunks]
            embeddings = await self.embeddings_client.embed_batch(chunk_texts)

            if len(embeddings) != len(chunks):
                logger.error(f"Embedding count mismatch: {len(embeddings)} != {len(chunks)}")
                return {
                    "chunks_created": len(chunks),
                    "chunks_indexed": 0,
                    "embeddings_generated": len(embeddings),
                    "errors": 1,
                }

            # 3. Build the chunk records Pinecone stores as metadata
            authors = paper_data.get("authors", "")
            if isinstance(authors, list):
                authors = ", ".join(authors)

            chunk_records = [
                {
                    # Deterministic id: re-indexing the same paper overwrites instead of duplicating
                    "chunk_id": f"{chunk.arxiv_id}#{chunk.metadata.chunk_index}",
                    "arxiv_id": chunk.arxiv_id,
                    "chunk_text": chunk.text,
                    "section_title": chunk.metadata.section_title,
                    "pdf_url": f"https://arxiv.org/pdf/{chunk.arxiv_id}.pdf",
                    "title": paper_data.get("title", ""),
                    "authors": authors,
                }
                for chunk in chunks
            ]

            # 4. Upsert
            self.pinecone_client.upsert_chunks(chunk_records, embeddings)
            logger.info(f"Indexed paper {arxiv_id}: {len(chunk_records)} chunks")

            return {
                "chunks_created": len(chunks),
                "chunks_indexed": len(chunk_records),
                "embeddings_generated": len(embeddings),
                "errors": 0,
            }

        except Exception as e:
            logger.error(f"Error indexing paper {arxiv_id}: {e}")
            return {"chunks_created": 0, "chunks_indexed": 0, "embeddings_generated": 0, "errors": 1}

    @traceable(name="index_paper_batch")
    async def index_papers_batch(
        self,
        papers: list[dict],
        replace_existing: bool = False,
    ) -> dict[str, int]:
        """Index multiple papers in batch."""
        total_stats = {
            "papers_processed": 0,
            "total_chunks_created": 0,
            "total_chunks_indexed": 0,
            "total_embeddings_generated": 0,
            "total_errors": 0,
        }

        for paper in papers:
            arxiv_id = paper.get("arxiv_id")

            if replace_existing and arxiv_id:
                self.pinecone_client.delete_paper_chunks(arxiv_id)

            stats = await self.index_paper(paper)

            total_stats["papers_processed"] += 1
            total_stats["total_chunks_created"] += stats["chunks_created"]
            total_stats["total_chunks_indexed"] += stats["chunks_indexed"]
            total_stats["total_embeddings_generated"] += stats["embeddings_generated"]
            total_stats["total_errors"] += stats["errors"]

        logger.info(
            f"Batch indexing complete: {total_stats['papers_processed']} papers, "
            f"{total_stats['total_chunks_indexed']} chunks indexed"
        )
        return total_stats

    async def reindex_paper(self, arxiv_id: str, paper_data: dict) -> dict[str, int]:
        """Reindex a paper by deleting old chunks and creating new ones."""
        self.pinecone_client.delete_paper_chunks(arxiv_id)
        logger.info(f"Deleted existing chunks for paper {arxiv_id}")
        return await self.index_paper(paper_data)
