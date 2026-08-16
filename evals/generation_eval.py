"""Stage 3 — generation eval.

For each golden case: run the SAME retrieval + SAME GENERATE_ANSWER_PROMPT the real
agent uses (top_k=3, matching production), get a real answer, then judge it three ways.

Two families of case, judged differently:

  cases WITH an expected paper (16 of 20)
      faithfulness   is every claim in the answer supported by the retrieved context?
                     (hallucination detector — independent of whether retrieval was
                     "correct" by our labels; it judges against whatever context the
                     system actually used)
      relevance      does the answer actually address the question asked?
                     (an answer can be 100% faithful and still not relevant — see notes)
      correctness    does it align with our verified reference answer?
                     (the one metric that uses ground truth, not just the context)

  cases with NO expected paper (4 of 20 — out_of_scope + the corpus-gap case)
      abstention     retrieval always returns *something* even when nothing is
                     relevant. The question here isn't "was the answer faithful to
                     bad context" — it's whether the generator correctly recognized
                     the context doesn't answer the question and said so, instead of
                     confidently hallucinating from irrelevant chunks. This is exactly
                     the check stage 1 (retrieval_eval.py) cannot do — retrieval-level
                     metrics are trivially 0 there regardless of what the generator
                     does with what it got.

Usage:
    uv run python evals/generation_eval.py
    uv run python evals/generation_eval.py --difficulty hard
"""

import argparse
import asyncio
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

from langchain_openai import ChatOpenAI  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from src.services.opensearch.factory import make_opensearch_client  # noqa: E402
from src.services.embeddings.factory import make_openai_embeddings_client  # noqa: E402
from src.services.agents.prompts import GENERATE_ANSWER_PROMPT  # noqa: E402
from evals.retrieval_dataset import GOLDEN_RETRIEVAL  # noqa: E402

MODEL = "gpt-4o-mini"
TEMPERATURE = 0.0
TOP_K = 3   # matches GraphConfig.top_k — the real production setting


# ══════════════════════════════════════════════════════════════════════
# Judges — same structured-output idiom as the rest of this codebase
# (GuardrailScoring, GradeDocuments, ...): force a Pydantic shape, never
# parse free text.
# ══════════════════════════════════════════════════════════════════════

class ClaimCheck(BaseModel):
    claim: str = Field(description="One factual claim extracted from the answer")
    supported: bool = Field(description="Is this claim directly supported by the context?")

class FaithfulnessJudgement(BaseModel):
    claims: list[ClaimCheck]

class RelevanceJudgement(BaseModel):
    relevant: bool = Field(description="Does the answer actually address the question asked?")
    reasoning: str = ""

class CorrectnessJudgement(BaseModel):
    correct: bool = Field(description="Does the answer align with the reference on the key facts?")
    reasoning: str = ""

class AbstentionCheck(BaseModel):
    hallucinated: bool = Field(
        description="True if the answer confidently answered using irrelevant/insufficient "
                    "context instead of acknowledging it couldn't find relevant information."
    )
    reasoning: str = ""


FAITHFULNESS_PROMPT = """Break the ANSWER below into individual factual claims. For each claim,
state whether it is DIRECTLY supported by the CONTEXT — not whether it's true in general,
only whether the context actually says it.

CONTEXT:
{context}

ANSWER:
{answer}

List every distinct factual claim in the answer and mark each supported or not."""

RELEVANCE_PROMPT = """Does the ANSWER actually address the QUESTION asked — regardless of
whether the answer is correct or grounded? An answer can be fully accurate and still fail
to address what was asked.

QUESTION: {question}

ANSWER: {answer}"""

CORRECTNESS_PROMPT = """Compare the GENERATED ANSWER to the REFERENCE ANSWER. Do they agree
on the key facts? Wording can differ completely — judge factual alignment only.

REFERENCE ANSWER: {reference}

GENERATED ANSWER: {generated}"""

ABSTENTION_PROMPT = """The system was asked a question that this corpus cannot actually
answer (either off-topic, or genuinely absent from the corpus). It retrieved some context
anyway, because search always returns its nearest matches even when none are truly relevant.

Did the ANSWER correctly recognize the context doesn't answer the question and say so —
or did it confidently answer as if the context were relevant?

QUESTION: {question}

RETRIEVED CONTEXT (may be irrelevant — that's expected here):
{context}

ANSWER:
{answer}"""


# ══════════════════════════════════════════════════════════════════════

async def retrieve_context(osc, emb, query: str) -> str:
    """Same shape as retrieve_papers tool's `content` — real production retrieval."""
    qv = await emb.embed_text(query)
    hits = osc.search_unified(query=query, query_embedding=qv, size=TOP_K, use_hybrid=True)["hits"]
    if not hits:
        return "No relevant documents found."
    return "\n\n".join(
        f"[{h.get('title', '')} (arXiv:{h.get('arxiv_id', '')})]\n{h['chunk_text']}"
        for h in hits
    )


async def generate(llm, context: str, question: str) -> str:
    """The exact prompt + call generate_answer_node uses."""
    prompt = GENERATE_ANSWER_PROMPT.format(context=context, question=question)
    response = await llm.ainvoke(prompt)
    return response.content if hasattr(response, "content") else str(response)


async def judge_faithfulness(llm, context: str, answer: str) -> Optional[float]:
    judge = llm.with_structured_output(FaithfulnessJudgement)
    result: FaithfulnessJudgement = await judge.ainvoke(
        FAITHFULNESS_PROMPT.format(context=context, answer=answer))
    if not result.claims:
        return None
    return sum(c.supported for c in result.claims) / len(result.claims)


async def judge_relevance(llm, question: str, answer: str) -> int:
    judge = llm.with_structured_output(RelevanceJudgement)
    result: RelevanceJudgement = await judge.ainvoke(
        RELEVANCE_PROMPT.format(question=question, answer=answer))
    return int(result.relevant)


async def judge_correctness(llm, reference: str, generated: str) -> int:
    judge = llm.with_structured_output(CorrectnessJudgement)
    result: CorrectnessJudgement = await judge.ainvoke(
        CORRECTNESS_PROMPT.format(reference=reference, generated=generated))
    return int(result.correct)


async def judge_abstention(llm, question: str, context: str, answer: str) -> int:
    """1 = good (correctly abstained), 0 = bad (hallucinated a confident answer)."""
    judge = llm.with_structured_output(AbstentionCheck)
    result: AbstentionCheck = await judge.ainvoke(
        ABSTENTION_PROMPT.format(question=question, context=context, answer=answer))
    return int(not result.hallucinated)


# ══════════════════════════════════════════════════════════════════════

async def main(difficulty: str | None) -> int:
    cases = GOLDEN_RETRIEVAL
    if difficulty:
        cases = [c for c in cases if c["difficulty"] == difficulty]

    osc = make_opensearch_client()
    emb = make_openai_embeddings_client()
    gen_llm = ChatOpenAI(model=MODEL, temperature=TEMPERATURE)     # matches production
    judge_llm = ChatOpenAI(model=MODEL, temperature=0.0)           # judges always deterministic

    scores = defaultdict(list)
    by_difficulty = defaultdict(lambda: defaultdict(list))
    rows = []

    print(f"Running {len(cases)} case(s)...\n")
    for case in cases:
        context = await retrieve_context(osc, emb, case["query"])
        answer = await generate(gen_llm, context, case["query"])

        has_reference = bool(case["expected_paper_id"])

        if has_reference:
            faith = await judge_faithfulness(judge_llm, context, answer)
            rel = await judge_relevance(judge_llm, case["query"], answer)
            corr = await judge_correctness(judge_llm, case["expected_answer"], answer)
            if faith is not None:
                scores["faithfulness"].append(faith)
                by_difficulty[case["difficulty"]]["faithfulness"].append(faith)
            scores["relevance"].append(rel)
            scores["correctness"].append(corr)
            by_difficulty[case["difficulty"]]["relevance"].append(rel)
            by_difficulty[case["difficulty"]]["correctness"].append(corr)
            tag = (f"faith={'—' if faith is None else f'{faith:.2f}'} "
                   f"rel={'ok' if rel else 'XX'} corr={'ok' if corr else 'XX'}")
        else:
            absten = await judge_abstention(judge_llm, case["query"], context, answer)
            scores["abstention"].append(absten)
            by_difficulty[case["difficulty"]]["abstention"].append(absten)
            tag = f"abstained_correctly={'ok' if absten else 'XX — HALLUCINATED'}"

        print(f"{case['query'][:52]:<54} [{case['difficulty']:<6} {case['query_type']:<28}] {tag}")
        rows.append((case, answer, tag))

    print(f"\n{'═' * 78}\n  OVERALL — {len(cases)} case(s)\n{'═' * 78}")
    for key in ("faithfulness", "relevance", "correctness", "abstention"):
        vals = scores.get(key)
        if not vals:
            continue
        avg = sum(vals) / len(vals)
        bar = "█" * int(avg * 20) + "░" * (20 - int(avg * 20))
        print(f"  {key:<14} {bar} {avg:.2f}  (n={len(vals)})")

    print(f"\n{'─' * 78}\n  BY DIFFICULTY\n{'─' * 78}")
    for diff in ("easy", "medium", "hard"):
        vals = by_difficulty.get(diff)
        if not vals:
            continue
        parts = [f"{k}={sum(v)/len(v):.2f}" for k, v in vals.items() if v]
        print(f"  {diff:<8} {'  '.join(parts)}")

    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--difficulty", choices=["easy", "medium", "hard"])
    a = p.parse_args()
    raise SystemExit(asyncio.run(main(a.difficulty)))
