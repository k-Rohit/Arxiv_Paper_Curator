# ruff: noqa: I001  — import order matters: Paper must register on Base before make_database
from src.models.paper import Paper  # noqa: F401
from src.db.factory import make_database
from src.repositories.paper import PaperRepository
from src.services.opensearch.factory import make_opensearch_client


def load_context(max_papers: int = 5, chunks_per_paper = 3) -> list[list[str]]:
    db = make_database()
    os_client = make_opensearch_client()
    with db.get_session() as session:
        papers = PaperRepository(session).get_processed_papers(limit=max_papers)
        arxiv_ids = [p.arxiv_id for p in papers]
    contexts = []
    for arxiv_id in arxiv_ids:
        chunks = os_client.get_chunks_by_paper(arxiv_id)
        good = [c["chunk_text"] for c in chunks if len(c["chunk_text"]) > 300]
        contexts.extend([[text] for text in good[:chunks_per_paper]])
    return contexts
