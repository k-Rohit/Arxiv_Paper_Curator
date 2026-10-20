"""One-time copy of every indexed chunk from OpenSearch into Pinecone, then a test search.

Chunks keep their OpenSearch ids, so results from both stores can be compared side by side.
Dense vectors are re-made with the same OpenAI embedder the app uses for queries.

Needs:  docker compose up -d postgres opensearch
Run:    uv run python -m scripts.migrate_opensearch_to_pinecone
"""

# ruff: noqa: I001  — Paper must register on Base before make_database
import asyncio
import time

from src.models.paper import Paper  # noqa: F401
from src.db.factory import make_database
from src.repositories.paper import PaperRepository
from src.services.embeddings.factory import make_openai_embeddings_client
from src.services.opensearch.factory import make_opensearch_client
from src.services.pinecone_.factory import make_pinecone_client

TEST_QUERY = "How are SWE-bench style benchmarks checked for problems?"


def processed_arxiv_ids() -> list[str]:
    db = make_database()
    with db.get_session() as session:
        papers = PaperRepository(session).get_processed_papers(limit=10_000)
        return [p.arxiv_id for p in papers]


def wait_for_vector_count(pinecone, expected: int, timeout_s: int = 60) -> int:
    """Pinecone is eventually consistent: upserted vectors take a few seconds to show up."""
    count = 0
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        count = pinecone.index.describe_index_stats().total_vector_count
        if count >= expected:
            break
        time.sleep(2)
    return count


async def main() -> None:
    opensearch = make_opensearch_client()
    embedder = make_openai_embeddings_client()
    pinecone = make_pinecone_client()

    pinecone.setup_index()
    print(f"Pinecone index '{pinecone.index_name}' ready")

    total = 0
    for arxiv_id in processed_arxiv_ids():
        chunks = opensearch.get_chunks_by_paper(arxiv_id)
        if not chunks:
            continue  # processed in Postgres but never indexed
        dense = await embedder.embed_batch([c["chunk_text"] for c in chunks])
        pinecone.upsert_chunks(chunks, dense)
        total += len(chunks)
        print(f"  {arxiv_id}: {len(chunks)} chunks")

    count = wait_for_vector_count(pinecone, total)
    print(f"Upserted {total} chunks — Pinecone reports {count} vectors")

    query_vec = await embedder.embed_text(TEST_QUERY)
    print(f"\nTest search: {TEST_QUERY!r}")
    for hit in pinecone.search(TEST_QUERY, query_vec, top_k=3):
        print(f"  {hit['score']:.3f}  {hit['arxiv_id']}  {hit['title'][:70]} {hit['pdf_url']} ")


if __name__ == "__main__":
    asyncio.run(main())
