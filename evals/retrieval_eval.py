"""Stage 1 — retrieval eval.

Runs BM25-only, vector-only, and hybrid RRF side by side against
evals/retrieval_dataset.py, and scores each at TWO levels:

    paper-level  did the right PAPER show up in the top-k?
    chunk-level  did the exact right PASSAGE show up in the top-k?

Paper-level uses set() semantics (order within a paper doesn't matter — many chunks
of the same paper collapse to one entry, see dedupe_to_papers). Chunk-level is
stricter: it demands the retriever surfaced that specific chunk, not just any part
of the right paper.

out_of_scope cases are skipped entirely — they have no expected paper/chunk, so
retrieval metrics don't apply; that's a guardrail question, not a retrieval one.

Usage:
    uv run python evals/retrieval_eval.py                  # all cases
    uv run python evals/retrieval_eval.py --difficulty hard
    uv run python evals/retrieval_eval.py --type factual_lookup
"""

import argparse
import asyncio
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

from src.services.opensearch.factory import make_opensearch_client  # noqa: E402
from src.services.embeddings.factory import make_openai_embeddings_client  # noqa: E402
from evals.retrieval_dataset import GOLDEN_RETRIEVAL  # noqa: E402

K = 5  # size for all three retrievers — bigger than production top_k=3 so a paper
       # ranked 4th or 5th still shows up as a partial signal instead of vanishing


# ── metrics — each takes (ranked_ids, correct_ids) as plain lists/sets ──────
def hit(ranked, correct) -> int:
    return int(any(x in correct for x in ranked))

def recall_at_k(ranked, correct) -> float:
    if not correct:
        return 0.0
    return len(set(ranked) & set(correct)) / len(correct)

def precision_at_k(ranked, correct) -> float:
    if not ranked:
        return 0.0
    return len(set(ranked) & set(correct)) / len(ranked)

def reciprocal_rank(ranked, correct) -> float:
    for i, x in enumerate(ranked, start=1):
        if x in correct:
            return 1 / i
    return 0.0

METRICS = {"hit": hit, "recall": recall_at_k, "precision": precision_at_k, "mrr": reciprocal_rank}


def dedupe_to_papers(hits: list[dict]) -> list[str]:
    """Chunk hits -> paper ids, first occurrence wins (= that paper's best rank)."""
    seen, ordered = set(), []
    for h in hits:
        aid = h["arxiv_id"]
        if aid not in seen:
            seen.add(aid)
            ordered.append(aid)
    return ordered


async def run_query(osc, emb, query: str) -> dict[str, dict[str, list[str]]]:
    """Run all 3 retrievers, return both paper-level and chunk-level ranked lists."""
    qv = await emb.embed_text(query)
    bm25   = osc.search_papers(query=query, size=K, latest=False)["hits"]
    vector = osc.search_chunks_vector(query_embedding=qv, size=K)["hits"]
    hybrid = osc.search_unified(query=query, query_embedding=qv, size=K, use_hybrid=True)["hits"]

    out = {}
    for name, hits in (("bm25", bm25), ("vector", vector), ("hybrid", hybrid)):
        out[name] = {
            "paper": dedupe_to_papers(hits),
            "chunk": [h["chunk_id"] for h in hits],
        }
    return out


async def main(difficulty: str | None, query_type: str | None) -> int:
    cases = [c for c in GOLDEN_RETRIEVAL if c["query_type"] != "out_of_scope"]
    if difficulty:
        cases = [c for c in cases if c["difficulty"] == difficulty]
    if query_type:
        cases = [c for c in cases if c["query_type"] == query_type]
    if not cases:
        print("No cases match that filter.")
        return 1

    osc = make_opensearch_client()
    emb = make_openai_embeddings_client()

    # scores[retriever][level][metric] -> list of per-case scores
    scores = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    # also bucketed by difficulty and query_type, for the breakdown tables
    by_difficulty = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    by_type = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    print(f"Running {len(cases)} case(s)...\n")
    for case in cases:
        results = await run_query(osc, emb, case["query"])
        correct_papers = set(case["expected_paper_id"])
        correct_chunks = set(case["expected_chunk_id"])

        row = f"{case['query'][:52]:<54} [{case['difficulty']:<6} {case['query_type']}]"
        print(row)

        for retriever, ranked in results.items():
            for level, correct in (("paper", correct_papers), ("chunk", correct_chunks)):
                ranked_list = ranked[level]
                for metric_name, fn in METRICS.items():
                    s = fn(ranked_list, correct)
                    scores[retriever][level][metric_name].append(s)
                    by_difficulty[case["difficulty"]][f"{retriever}/{level}"][metric_name].append(s)
                    by_type[case["query_type"]][f"{retriever}/{level}"][metric_name].append(s)

            paper_hit = scores[retriever]["paper"]["hit"][-1]
            chunk_hit = scores[retriever]["chunk"]["hit"][-1]
            mark = "OK" if paper_hit else "XX"
            print(f"   {retriever:<7} paper_hit={mark}  chunk_hit={'OK' if chunk_hit else 'XX'}"
                  f"  mrr(paper)={scores[retriever]['paper']['mrr'][-1]:.2f}")
        print()

    # ── overall scorecard: retriever x level x metric ──────────────────
    print(f"{'═' * 78}\n  OVERALL — {len(cases)} case(s)\n{'═' * 78}")
    header = f"{'retriever/level':<16}" + "".join(f"{m:>12}" for m in METRICS)
    print(header)
    for retriever in ("bm25", "vector", "hybrid"):
        for level in ("paper", "chunk"):
            vals = scores[retriever][level]
            row = f"{retriever + '/' + level:<16}"
            for m in METRICS:
                avg = sum(vals[m]) / len(vals[m]) if vals[m] else 0.0
                row += f"{avg:>12.3f}"
            print(row)
        print()

    # ── breakdown by difficulty (paper-level hybrid only, the headline number) ──
    print(f"{'─' * 78}\n  BY DIFFICULTY (hybrid, paper-level)\n{'─' * 78}")
    for diff in ("easy", "medium", "hard"):
        vals = by_difficulty[diff].get("hybrid/paper")
        if not vals:
            continue
        n = len(vals["hit"])
        row = f"{diff:<10} n={n:<4}"
        for m in METRICS:
            avg = sum(vals[m]) / len(vals[m])
            row += f"  {m}={avg:.2f}"
        print(row)

    # ── breakdown by query_type (paper-level hybrid) ────────────────────
    print(f"\n{'─' * 78}\n  BY QUERY TYPE (hybrid, paper-level)\n{'─' * 78}")
    for qt, vals_by_key in by_type.items():
        vals = vals_by_key.get("hybrid/paper")
        if not vals:
            continue
        n = len(vals["hit"])
        row = f"{qt:<28} n={n:<4}"
        for m in METRICS:
            avg = sum(vals[m]) / len(vals[m])
            row += f"  {m}={avg:.2f}"
        print(row)

    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--difficulty", choices=["easy", "medium", "hard"])
    p.add_argument("--type", dest="query_type",
                   choices=["factual_lookup", "summarize_main_contribution",
                            "multi_paper_comparison", "vague"])
    a = p.parse_args()
    raise SystemExit(asyncio.run(main(a.difficulty, a.query_type)))
