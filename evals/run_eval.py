"""Eval runner — prints a scorecard for the golden set.

Two tiers, because they cost wildly different amounts:

    --router   (default)  ONE LLM call per case. Seconds, cents. Run this constantly.
    --full                The whole graph: 4-7 LLM calls per case, and any
                          fetch_live_papers case really downloads and parses PDFs
                          (~40s each). Run this deliberately, not in a loop.

Usage:
    uv run python evals/run_eval.py            # router accuracy only
    uv run python evals/run_eval.py --full     # end-to-end (slow, costs money)
    uv run python evals/run_eval.py --full --no-fetch   # end-to-end, skip live-fetch cases

Every evaluator is a plain function returning {"key": str, "score": 0|1}. That's the same
shape langsmith.evaluate() expects, so these move over unchanged when you want hosted
experiment tracking and run-to-run diffs.
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

from src.models.paper import Paper  # noqa: F401,E402  (ORM registration — CLAUDE.md gotcha #1)
from evals.golden import GOLDEN  # noqa: E402


# ══════════════════════════════════════════════════════════════════════
# Evaluators — pure functions over (case, result). Add new metrics here.
# ══════════════════════════════════════════════════════════════════════

def routed_correctly(case: dict, result: dict) -> dict | None:
    """Did the router pick the tool we expected?"""
    if "tool" not in case:
        return None
    return {"key": "routing_accuracy", "score": int(result.get("tool") == case["tool"])}


def answered_correctly(case: dict, result: dict) -> dict | None:
    """Did it answer when it should, and refuse/fall back when it shouldn't?"""
    if "answered" not in case or "answered" not in result:
        return None
    return {"key": "answer_correctness", "score": int(result["answered"] == case["answered"])}


def found_expected_papers(case: dict, result: dict) -> dict | None:
    """Did the expected arxiv_id(s) show up in the cited sources? (recall@k, k=top_k)"""
    if "papers" not in case or "source_ids" not in result:
        return None
    got = set(result["source_ids"])
    want = set(case["papers"])
    return {"key": "retrieval_recall", "score": int(bool(want & got))}


EVALUATORS = [routed_correctly, answered_correctly, found_expected_papers]


# ══════════════════════════════════════════════════════════════════════
# Tier 1 — router only. One LLM call per case.
# ══════════════════════════════════════════════════════════════════════

async def run_router(case: dict) -> dict:
    from src.services.agents.config import GraphConfig
    from src.services.agents.nodes.router_node import select_tool
    from langchain_core.messages import HumanMessage

    runtime = SimpleNamespace(context=SimpleNamespace(graph_config=GraphConfig()))
    state = {"messages": [HumanMessage(content=case["query"])], "original_query": None}
    out = await select_tool(state, runtime)
    return {"tool": out.get("tool_selection"), "topic": out.get("target_topic")}


# ══════════════════════════════════════════════════════════════════════
# Tier 2 — the whole graph. Slow and real.
# ══════════════════════════════════════════════════════════════════════

# Phrases emitted by _extract_reasoning_steps when the graph did NOT produce a
# real answer. Kept here rather than inline so a wording change is a one-line fix.
NON_ANSWERS = ("Declined", "No relevant papers found")


async def run_full(case: dict, agent) -> dict:
    result = await agent.ask(case["query"], thread_id=f"eval-{abs(hash(case['query'])) % 10**8}")
    steps = result.get("reasoning_steps", [])

    fetched = any("Fetched" in s or "Searched arXiv" in s for s in steps)
    answered = not any(s.startswith(NON_ANSWERS) for s in steps)

    return {
        "tool": "fetch_live_papers" if fetched else "retrieve",
        "answered": answered,
        "source_ids": [s.get("arxiv_id") for s in result.get("sources", [])],
        "steps": steps,
        "answer": result.get("answer", ""),
    }


# ══════════════════════════════════════════════════════════════════════

async def main(full: bool, skip_fetch: bool) -> int:
    cases = GOLDEN
    if skip_fetch:
        cases = [c for c in cases if c.get("tool") != "fetch_live_papers"]

    agent = None
    if full:
        from src.services.agents.factory import make_agentic_rag
        agent = make_agentic_rag()

    scores: dict[str, list[int]] = {}
    rows = []

    for case in cases:
        t0 = time.time()
        try:
            result = await (run_full(case, agent) if full else run_router(case))
            error = None
        except Exception as e:                      # a crashing case is a FAILING case,
            result, error = {}, f"{type(e).__name__}: {e}"   # not a crashed harness
        elapsed = time.time() - t0

        marks = []
        for ev in EVALUATORS:
            out = ev(case, result)
            if out is None:
                continue
            scores.setdefault(out["key"], []).append(out["score"])
            marks.append(f"{out['key'].split('_')[0]}={'ok' if out['score'] else 'XX'}")

        rows.append((case, result, marks, elapsed, error))

    # ── report ────────────────────────────────────────────────────────
    mode = "FULL GRAPH" if full else "ROUTER ONLY"
    print(f"\n{'═' * 78}\n  {mode}  ·  {len(cases)} cases\n{'═' * 78}\n")

    for case, result, marks, elapsed, error in rows:
        ok = error is None and all("XX" not in m for m in marks)
        print(f"{'PASS' if ok else 'FAIL'}  {case['query'][:56]:<58} {elapsed:5.1f}s")
        if error:
            print(f"        ERROR {error}")
        else:
            if marks:
                print(f"        {' · '.join(marks)}")
            if "tool" in case and result.get("tool") != case.get("tool"):
                print(f"        wanted tool={case['tool']}, got {result.get('tool')}")
            if "answered" in case and "answered" in result and result["answered"] != case["answered"]:
                print(f"        wanted answered={case['answered']}, got {result['answered']}")
                for s in result.get("steps", []):
                    print(f"          - {s}")

    print(f"\n{'─' * 78}\n  SCORECARD\n{'─' * 78}")
    for key, vals in sorted(scores.items()):
        pct = 100 * sum(vals) / len(vals)
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(f"  {key:<20} {bar} {sum(vals)}/{len(vals)}  ({pct:.0f}%)")

    failed = sum(1 for _, _, m, _, e in rows if e or any("XX" in x for x in m))
    print(f"\n  {len(rows) - failed}/{len(rows)} cases fully passed\n")
    return 1 if failed else 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--full", action="store_true", help="run the whole graph (slow, costs money)")
    p.add_argument("--no-fetch", action="store_true", help="skip live-fetch cases")
    a = p.parse_args()
    raise SystemExit(asyncio.run(main(a.full, a.no_fetch)))
