"""Stage 1 — retrieval eval, tracked in LangSmith so before/after comparisons are real.

Run this NOW (before touching retrieval) to save a baseline experiment. Then when you
try the two-stage hierarchical retrieval idea — retrieve the right paper(s) first, then
search chunks restricted to those papers — edit ONLY `run_retrieval()`'s body below,
re-run with a new --tag, and diff the two experiments in the LangSmith UI. Everything
else (dataset, metrics, latency capture) stays identical, which is what makes the
comparison mean something.

Requires: uv run python evals/langsmith_setup.py   (once, or whenever golden.py changes)

Usage:
    uv run python evals/langsmith_retrieval_eval.py --tag hybrid-baseline-topk3
    uv run python evals/langsmith_retrieval_eval.py --tag two-stage-hierarchical
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

from langsmith import aevaluate  # noqa: E402
from langsmith.evaluation import EvaluationResult, EvaluationResults  # noqa: E402
from langsmith.utils import tracing_is_enabled  # noqa: E402

from src.services.opensearch.factory import make_opensearch_client  # noqa: E402
from src.services.embeddings.factory import make_openai_embeddings_client  # noqa: E402
from evals.retrieval_eval import METRICS, dedupe_to_papers  # noqa: E402  — reuse, don't reimplement
from evals.langsmith_setup import DATASET_NAME  # noqa: E402

TOP_K = 3   # matches GraphConfig.top_k — the real production setting, NOT the dev-loop
            # script's K=5. This eval is tracking what's actually deployed.


# ══════════════════════════════════════════════════════════════════════
# The system under test. THIS is what you swap for the two-stage idea —
# everything below this function is plumbing that shouldn't need to change.
# ══════════════════════════════════════════════════════════════════════

async def run_retrieval(osc, emb, query: str) -> dict:
    """Today's strategy: hybrid RRF search, top_k=3, no paper-level pre-filter.

    For the two-stage hierarchical version: first call osc.search_papers(...) or
    search_unified(...) to rank papers, take the top N, then re-run chunk search
    with a `categories`/paper_id filter restricted to those papers (search_unified
    already accepts a filter list — see QueryBuilder._build_filters). Return the
    same shape: {"paper_ranked": [...], "chunk_ranked": [...]}.
    """
    qv = await emb.embed_text(query)
    hits = osc.search_unified(query=query, query_embedding=qv, size=TOP_K, use_hybrid=True)["hits"]
    return {
        "paper_ranked": dedupe_to_papers(hits),
        "chunk_ranked": [h["chunk_id"] for h in hits],
    }


# ══════════════════════════════════════════════════════════════════════

def make_target(osc, emb):
    """Wraps run_retrieval with latency capture — aevaluate() traces this whole
    call automatically, but we log latency as an explicit scored metric too, so it
    sits in the same comparison table as retrieval quality instead of being
    something you have to go find in a separate part of the LangSmith UI."""

    async def target(inputs: dict) -> dict:
        t0 = time.perf_counter()
        result = await run_retrieval(osc, emb, inputs["query"])
        result["latency_ms"] = (time.perf_counter() - t0) * 1000
        return result

    return target


def retrieval_metrics(run, example) -> EvaluationResults:
    outputs = run.outputs or {}
    expected = example.outputs or {}

    correct_papers = set(expected.get("expected_paper_id", []))
    correct_chunks = set(expected.get("expected_chunk_id", []))
    paper_ranked = outputs.get("paper_ranked", [])
    chunk_ranked = outputs.get("chunk_ranked", [])

    results = [EvaluationResult(key="latency_ms", score=outputs.get("latency_ms", 0.0))]

    # Skip quality metrics on out_of_scope/corpus-gap cases (empty ground truth) —
    # same reasoning as the dev-loop script: hit/recall/precision/mrr against an
    # empty correct-set is a degenerate always-0, not a real signal.
    if not correct_papers:
        return EvaluationResults(results=results)

    for level, ranked, correct in (
        ("paper", paper_ranked, correct_papers),
        ("chunk", chunk_ranked, correct_chunks),
    ):
        for metric_name, fn in METRICS.items():
            results.append(EvaluationResult(key=f"{level}_{metric_name}", score=fn(ranked, correct)))

    return EvaluationResults(results=results)


# ══════════════════════════════════════════════════════════════════════

async def main(tag: str) -> None:
    if not tracing_is_enabled():
        print("LANGCHAIN_TRACING_V2 is not enabled — set it in .env first.")
        return

    osc = make_opensearch_client()
    emb = make_openai_embeddings_client()

    print(f"running experiment {tag!r} over {DATASET_NAME} (top_k={TOP_K})...")
    results = await aevaluate(
        make_target(osc, emb),
        data=DATASET_NAME,
        evaluators=[retrieval_metrics],
        experiment_prefix=tag,
        metadata={"top_k": TOP_K},
        max_concurrency=4,
    )
    print(f"done -> {getattr(results, 'experiment_name', tag)}")
    print("compare experiments in smith.langchain.com -> Datasets & Experiments")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--tag", required=True,
                    help="experiment name, e.g. 'hybrid-baseline-topk3' or 'two-stage-hierarchical'")
    a = p.parse_args()
    asyncio.run(main(a.tag))
