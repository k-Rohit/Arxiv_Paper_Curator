import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    force=True,
)

from src.models.paper import Paper  # noqa: F401  register the table
from src.services.arxiv.factory import make_arxiv_client
from src.services.metadata_fetcher import make_metadata_fetcher
from src.db.factory import make_database
from src.repositories.paper import PaperRepository


class FakeParser:
    """No Docling — isolate the fetch -> store path."""

    async def parse_pdf(self, pdf_path):
        return None


async def main():
    print(">>> 1. Building arxiv client + fetcher", flush=True)
    fetcher = make_metadata_fetcher(
        arxiv_client=make_arxiv_client(),
        pdf_parser=FakeParser(),
    )

    print(">>> 2. Connecting to DB", flush=True)
    db = make_database()

    print(">>> 3. Running pipeline (fetch + store, no PDFs)", flush=True)
    with db.get_session() as session:
        results = await fetcher.fetch_and_process_papers(
            max_results=2,
            process_pdfs=False,
            store_to_db=True,
            db_session=session,
        )
    print(">>> 4. Results:", results, flush=True)

    with db.get_session() as session:
        print(">>> 5. Papers in DB:", PaperRepository(session).get_count(), flush=True)

    db.teardown()
    print(">>> DONE", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
