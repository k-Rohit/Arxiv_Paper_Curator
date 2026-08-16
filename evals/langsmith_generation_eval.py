"""Stage 3 — generation eval, tracked in LangSmith.

Same reasoning as langsmith_retrieval_eval.py: run this to save a baseline before
changing anything upstream (retrieval strategy, GENERATE_ANSWER_PROMPT, chunk size —
any of it). A retrieval change can move generation quality too — faithfulness/
correctness are only as good as the context they're fed — so tracking this
separately from retrieval_eval's own metrics is what lets you see that side effect
instead of missing it.

Requires: uv run python evals/langsmith_setup.py   (once, or whenever golden.py changes)

Usage:
    uv run python evals/langsmith_generation_eval.py --tag generation-baseline
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

from langchain_openai import ChatOpenAI  # noqa: E402
from langsmith import aevaluate  # noqa: E402
from langsmith.evaluation import EvaluationResult, EvaluationResults  # noqa: E402
from langsmith.utils import tracing_is_enabled  # noqa: E402

from src.services.opensearch.factory import make_opensearch_client  # noqa: E402
from src.services.embeddings.factory import make_openai_embeddings_client  # noqa: E402
from evals.generation_eval import (  # noqa: E402  — reuse the verified judges, don't reimplement
    MODEL, TEMPERATURE,
    retrieve_context, generate,
    judge_faithfulness, judge_relevance, judge_correctness, judge_abstention,
)
from evals.langsmith_setup import DATASET_NAME  # noqa: E402


def make_target(osc, emb, gen_llm):
    async def target(inputs: dict) -> dict:
        query = inputs["query"]

        t0 = time.perf_counter()
        context = await retrieve_context(osc, emb, query)
        retrieval_ms = (time.perf_counter() - t0) * 1000

        t1 = time.perf_counter()
        answer = await generate(gen_llm, context, query)
        generation_ms = (time.perf_counter() - t1) * 1000

        return {
            "context": context,
            "answer": answer,
            "retrieval_ms": retrieval_ms,
            "generation_ms": generation_ms,
            "total_ms": retrieval_ms + generation_ms,
        }

    return target


def make_evaluator(judge_llm):
    async def generation_metrics(run, example) -> EvaluationResults:
        outputs = run.outputs or {}
        expected = example.outputs or {}
        query = example.inputs.get("query", "")
        context = outputs.get("context", "")
        answer = outputs.get("answer", "")

        results = [
            EvaluationResult(key="latency_retrieval_ms", score=outputs.get("retrieval_ms", 0.0)),
            EvaluationResult(key="latency_generation_ms", score=outputs.get("generation_ms", 0.0)),
            EvaluationResult(key="latency_total_ms", score=outputs.get("total_ms", 0.0)),
        ]

        has_reference = bool(expected.get("expected_paper_id"))

        if has_reference:
            faith = await judge_faithfulness(judge_llm, context, answer)
            if faith is not None:
                results.append(EvaluationResult(key="faithfulness", score=faith))
            rel = await judge_relevance(judge_llm, query, answer)
            results.append(EvaluationResult(key="relevance", score=rel))
            corr = await judge_correctness(judge_llm, expected.get("expected_answer", ""), answer)
            results.append(EvaluationResult(key="correctness", score=corr))
        else:
            absten = await judge_abstention(judge_llm, query, context, answer)
            results.append(EvaluationResult(key="abstention", score=absten))

        return EvaluationResults(results=results)

    return generation_metrics


async def main(tag: str) -> None:
    if not tracing_is_enabled():
        print("LANGCHAIN_TRACING_V2 is not enabled — set it in .env first.")
        return

    osc = make_opensearch_client()
    emb = make_openai_embeddings_client()
    gen_llm = ChatOpenAI(model=MODEL, temperature=TEMPERATURE)     # matches production
    judge_llm = ChatOpenAI(model=MODEL, temperature=0.0)

    print(f"running experiment {tag!r} over {DATASET_NAME}...")
    results = await aevaluate(
        make_target(osc, emb, gen_llm),
        data=DATASET_NAME,
        evaluators=[make_evaluator(judge_llm)],
        experiment_prefix=tag,
        max_concurrency=2,   # generation calls are the expensive part — keep this modest
    )
    print(f"done -> {getattr(results, 'experiment_name', tag)}")
    print("compare experiments in smith.langchain.com -> Datasets & Experiments")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--tag", required=True, help="experiment name, e.g. 'generation-baseline'")
    a = p.parse_args()
    asyncio.run(main(a.tag))
