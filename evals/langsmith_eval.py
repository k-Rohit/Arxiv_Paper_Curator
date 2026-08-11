"""Run the golden set as a LangSmith experiment.

Why bother, when run_eval.py already prints a scorecard? One reason: **run-to-run diffs.**
LangSmith stores each run as an experiment, so you can compare "before prompt change" vs
"after" side by side and see which individual cases moved. That's the question a local
scorecard can't answer — not "is it good" but "did my change help".

Usage:
    uv run python evals/langsmith_eval.py --upload      # create/refresh the dataset (once)
    uv run python evals/langsmith_eval.py               # run router-only experiment
    uv run python evals/langsmith_eval.py --full        # run the whole graph
    uv run python evals/langsmith_eval.py --full --tag "grader-prompt-v2"

Requires LANGCHAIN_API_KEY and LANGCHAIN_TRACING_V2=true (both already in your .env).
Results upload to the LangSmith cloud and count against your quota.
"""

import argparse
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

from langsmith import Client, aevaluate  # noqa: E402
from langsmith.utils import tracing_is_enabled  # noqa: E402

from src.models.paper import Paper  # noqa: F401,E402  (ORM registration — CLAUDE.md gotcha #1)
from evals.golden import GOLDEN  # noqa: E402
from evals.run_eval import (  # noqa: E402  — reuse the SAME comparison logic
    NON_ANSWERS,
    answered_correctly,
    found_expected_papers,
    routed_correctly,
)

DATASET = "arxiv-curator-golden"


# ══════════════════════════════════════════════════════════════════════
# Dataset — one-time upload, safe to re-run
# ══════════════════════════════════════════════════════════════════════

def upload() -> None:
    """Create the dataset if missing, then replace its examples with golden.py.

    Deleting and recreating the examples (rather than appending) keeps golden.py the
    single source of truth — otherwise edits there silently diverge from the cloud copy.
    """
    client = Client()

    if client.has_dataset(dataset_name=DATASET):
        ds = client.read_dataset(dataset_name=DATASET)
        existing = list(client.list_examples(dataset_id=ds.id))
        if existing:
            client.delete_example(example_ids=[e.id for e in existing])
            print(f"cleared {len(existing)} old examples")
    else:
        ds = client.create_dataset(
            dataset_name=DATASET,
            description="Golden Q&A set for the arXiv Paper Curator agent. "
                        "Source of truth: evals/golden.py",
        )
        print(f"created dataset {DATASET!r}")

    client.create_examples(
        dataset_id=ds.id,
        examples=[
            {
                "inputs": {"query": c["query"]},
                # everything except the query is the EXPECTATION
                "outputs": {k: v for k, v in c.items() if k != "query"},
            }
            for c in GOLDEN
        ],
    )
    print(f"uploaded {len(GOLDEN)} examples → {DATASET}")


# ══════════════════════════════════════════════════════════════════════
# Targets — what gets evaluated. Same two tiers as run_eval.py.
# ══════════════════════════════════════════════════════════════════════

async def target_router(inputs: dict) -> dict:
    from langchain_core.messages import HumanMessage

    from src.services.agents.config import GraphConfig
    from src.services.agents.nodes.router_node import select_tool

    runtime = SimpleNamespace(context=SimpleNamespace(graph_config=GraphConfig()))
    state = {"messages": [HumanMessage(content=inputs["query"])], "original_query": None}
    out = await select_tool(state, runtime)
    return {"tool": out.get("tool_selection"), "topic": out.get("target_topic")}


def make_target_full():
    """Build the agent ONCE and close over it — constructing it per case would reload
    Docling's model weights and rebuild the graph on every example."""
    from src.services.agents.factory import make_agentic_rag

    agent = make_agentic_rag()

    async def target_full(inputs: dict) -> dict:
        q = inputs["query"]
        result = await agent.ask(q, thread_id=f"eval-{abs(hash(q)) % 10**8}")
        steps = result.get("reasoning_steps", [])
        return {
            "tool": "fetch_live_papers"
                    if any("Fetched" in s or "Searched arXiv" in s for s in steps)
                    else "retrieve",
            "answered": not any(s.startswith(NON_ANSWERS) for s in steps),
            "source_ids": [s.get("arxiv_id") for s in result.get("sources", [])],
            "answer": result.get("answer", ""),
            "steps": steps,
        }

    return target_full


# ══════════════════════════════════════════════════════════════════════
# Evaluators — thin adapters onto the functions run_eval.py already has.
# LangSmith hands us (run, example); our functions want (case, result).
# ══════════════════════════════════════════════════════════════════════

def _adapt(fn):
    def evaluator(run, example):
        out = fn(example.outputs or {}, run.outputs or {})
        # A skipped metric (case doesn't declare that field) must not be scored 0 —
        # that would drag the average down for cases the metric doesn't apply to.
        return out if out else {"key": fn.__name__, "score": None}
    evaluator.__name__ = fn.__name__
    return evaluator


EVALUATORS = [_adapt(f) for f in (routed_correctly, answered_correctly, found_expected_papers)]


# ══════════════════════════════════════════════════════════════════════

async def run(full: bool, tag: str | None) -> None:
    if not tracing_is_enabled():
        print("LANGCHAIN_TRACING_V2 is not enabled — set it in .env first.")
        return

    target = make_target_full() if full else target_router
    prefix = tag or ("full-graph" if full else "router-only")

    print(f"running experiment {prefix!r} over {DATASET} ({len(GOLDEN)} cases)…")
    results = await aevaluate(
        target,
        data=DATASET,
        evaluators=EVALUATORS,
        experiment_prefix=prefix,
        metadata={"tier": "full" if full else "router"},
        # 1 keeps arXiv rate limiting safe on the full tier and makes logs readable
        max_concurrency=1 if full else 4,
    )
    print(f"\ndone → {getattr(results, 'experiment_name', prefix)}")
    print("open smith.langchain.com → Datasets & Experiments to compare runs")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--upload", action="store_true", help="create/refresh the dataset, then exit")
    p.add_argument("--full", action="store_true", help="run the whole graph (slow, costs money)")
    p.add_argument("--tag", help="experiment name prefix, e.g. 'grader-prompt-v2'")
    a = p.parse_args()

    if a.upload:
        upload()
    else:
        asyncio.run(run(a.full, a.tag))
