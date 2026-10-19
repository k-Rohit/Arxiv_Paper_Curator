"""Run every golden's question through the /ask RAG pipeline and save the filled-in goldens.

Goldens come out of the synthesizer with `input`, `expected_output` and `context`.
This script fills `actual_output` (our answer) and `retrieval_context` (the chunks we
retrieved), which is everything the DeepEval metrics need.

Mirrors src/routers/ask.py (embed → hybrid search → LLM) but skips the Redis cache and
keeps the chunk texts, which AskResponse throws away.

Run from the repo root:  uv run python -m evals.data.generate_evaluation_dataset
"""

import asyncio
from pathlib import Path

from deepeval.dataset import EvaluationDataset, Golden

from evals.eval_utils import latest_goldens_file
from src.services.embeddings.factory import make_openai_embeddings_client
from src.services.openai_.factory import make_openai_client
from src.services.opensearch.factory import make_opensearch_client

DATA_DIR = Path(__file__).parent
EVALUATION_DIR = DATA_DIR / "evaluation"
TOP_K = 5
MAX_CONCURRENT = 5


async def answer_golden(golden: Golden, opensearch, embedder, llm, semaphore: asyncio.Semaphore) -> None:
    async with semaphore:
        query_embedding = await embedder.embed_text(golden.input)
        results = opensearch.search_unified(
            query=golden.input,
            query_embedding=query_embedding,
            size=TOP_K,
            from_=0,
            use_hybrid=True,
            min_score=0.0,
        )
        hits = results.get("hits", [])
        chunks = [{"arxiv_id": h.get("arxiv_id", ""), "chunk_text": h.get("chunk_text", h.get("abstract", ""))} for h in hits]

        golden.retrieval_context = [c["chunk_text"] for c in chunks]
        if not chunks:
            golden.actual_output = "No relevant papers found for this query."
            return

        rag_result = await llm.generate_rag_response(query=golden.input, chunks=chunks)
        golden.actual_output = rag_result.get("answer", "")


async def main() -> None:
    goldens_file = latest_goldens_file()
    dataset = EvaluationDataset()
    dataset.add_goldens_from_json_file(str(goldens_file))
    print(f"Loaded {len(dataset.goldens)} goldens from {goldens_file}")

    opensearch = make_opensearch_client()
    embedder = make_openai_embeddings_client()
    llm = make_openai_client()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    await asyncio.gather(*(answer_golden(g, opensearch, embedder, llm, semaphore) for g in dataset.goldens))

    path = dataset.save_as(file_type="json", directory=str(EVALUATION_DIR))
    print(f"Saved evaluation dataset to {path}")


if __name__ == "__main__":
    asyncio.run(main())
