"""One-time (or re-run-when-golden.py-changes) dataset upload to LangSmith.

Run this before either langsmith_retrieval_eval.py or langsmith_generation_eval.py —
they both read from the dataset this creates, not from retrieval_dataset.py directly.
That's deliberate: LangSmith is the source of truth for experiment comparison, so the
examples it diffs against need to actually live there.

Usage:
    uv run python evals/langsmith_setup.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

from langsmith import Client  # noqa: E402

from evals.retrieval_dataset import GOLDEN_RETRIEVAL  # noqa: E402

DATASET_NAME = "arxiv-curator-retrieval-golden"


def main() -> None:
    client = Client()

    if client.has_dataset(dataset_name=DATASET_NAME):
        ds = client.read_dataset(dataset_name=DATASET_NAME)
        existing = list(client.list_examples(dataset_id=ds.id))
        if existing:
            # Delete-and-recreate, not append: retrieval_dataset.py is the single
            # source of truth. If we only appended, an edited case in the Python file
            # would silently diverge from its stale LangSmith copy, and every
            # experiment after that point would be scored against the wrong label.
            client.delete_example(example_ids=[e.id for e in existing])
            print(f"cleared {len(existing)} existing examples")
    else:
        ds = client.create_dataset(
            dataset_name=DATASET_NAME,
            description="Retrieval golden set — source of truth is evals/retrieval_dataset.py",
        )
        print(f"created dataset {DATASET_NAME!r}")

    client.create_examples(
        dataset_id=ds.id,
        examples=[
            {
                "inputs": {"query": c["query"]},
                "outputs": {
                    "expected_paper_id": c["expected_paper_id"],
                    "expected_chunk_id": c["expected_chunk_id"],
                    "expected_answer": c["expected_answer"],
                },
                "metadata": {
                    "difficulty": c["difficulty"],
                    "query_type": c["query_type"],
                },
            }
            for c in GOLDEN_RETRIEVAL
        ],
    )
    print(f"uploaded {len(GOLDEN_RETRIEVAL)} examples -> {DATASET_NAME}")


if __name__ == "__main__":
    main()
