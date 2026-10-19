from pinecone import Pinecone, ServerlessSpec

from src.config import PineconeSettings


class PineconeClient:
    def __init__(self, settings: PineconeSettings):
        self.pc = Pinecone(api_key=settings.api_key)
        self.index_name = settings.index_name

    def setup_index(self, dimension: int = 1024) -> None:
        if not self.pc.has_index(self.index_name):
            self.pc.create_index(
                name=self.index_name, dimension=dimension, metric="cosine", spec=ServerlessSpec(cloud="aws", region="us-east-1")
            )

    def upsert_chunks(self, chunks: list[dict], embeddings: list[list[float]]) -> None:
        vectors = [
            {
                "id": c["chunk_id"],
                "values": e,
                "metadata": {
                    "arxiv_id": c["arxiv_id"],
                    "chunk_text": c["chunk_text"],
                    "title": c.get("title", ""),
                    "pdf_url": c.get("pdf_url", ""),
                },
            }
            for c, e in zip(chunks, embeddings)  # noqa: B905
        ]
        self.index.upsert(vectors=vectors)

    def search(self, query_embedding: list[float], top_k: int = 5) -> list[dict]:
        result = self.index.query(vector=query_embedding, top_k=top_k, include_metadata=True)
        return [{**m.metadata, "score": m.score} for m in result.matches]
