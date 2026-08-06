"""Throwaway test: can the LLM pick the right tool? No graph, no code changes.

Run:  uv run python <this file>
If the accuracy looks good, copy ToolSelection -> models.py and the prompt -> prompts.py
"""

import asyncio
from typing import Literal, Optional

from dotenv import load_dotenv

load_dotenv()

from langchain_openai import ChatOpenAI  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402


class ToolSelection(BaseModel):
    tool: Literal["retrieve", "summarize_paper", "fetch_live_papers"]
    paper_references: list[str] = Field(default_factory=list)
    topic: Optional[str] = None
    reason: str = ""


TOOL_ROUTING_PROMPT = """You route requests for an arXiv research assistant. Pick the ONE tool that best handles the user's request.

    Tools:
        - retrieve: answer a question using research papers we already have locally. This is the DEFAULT for ordinary questions about concepts, methods, or findings.
        - summarize_paper: the user names a specific paper and wants that paper summarized.
        - fetch_live_papers: the user wants us to go find NEW papers from arXiv that we may not have yet. Signals: "find", "get me", "search for", "any recent/latest papers on...".

        Rules:
            - When in doubt, choose retrieve. It is the safe default.
            - summarize_paper: copy whatever the user called the paper into paper_references (e.g. ["BERT"]). Never invent or recall an arXiv ID from memory.
            - fetch_live_papers: put the subject matter into topic.
            - A question ABOUT a topic is retrieve. A request to GO GET papers on a topic is fetch_live_papers.

            Examples:
                "how does attention work?" -> retrieve
                "summarize the BERT paper" -> summarize_paper, paper_references=["BERT"]
                "find new papers on diffusion models" -> fetch_live_papers, topic="diffusion models"

                User request: {question}"""


CASES = [
                    # (query, expected tool)
                    ("how does multi-head attention work?",                    "retrieve"),
                    ("what safety mechanism does PAC-MAN use for robots?",     "retrieve"),
                    ("explain knowledge distillation",                         "retrieve"),
                    ("what did the PAIChecker paper find?",                    "retrieve"),
                    ("summarize the BERT paper",                               "summarize_paper"),
                    ("give me a summary of PAIChecker",                        "summarize_paper"),
                    ("can you summarize the mixture of experts paper?",        "summarize_paper"),
                    ("find new papers on diffusion models",                    "fetch_live_papers"),
                    ("get me recent work on humanoid locomotion",              "fetch_live_papers"),
                    ("search arxiv for papers about quantum machine learning", "fetch_live_papers"),
                    ("any latest papers on retrieval augmented generation?",   "fetch_live_papers"),
                ]


async def main():
    model = ChatOpenAI(model="gpt-4o-mini", temperature=0.0)
    router = model.with_structured_output(ToolSelection)

    results = await asyncio.gather(
        *(router.ainvoke(TOOL_ROUTING_PROMPT.format(question=q)) for q, _ in CASES)
    )

    hits = 0
    print(f"{'':2} {'QUERY':<52} {'EXPECTED':<18} {'GOT':<18} EXTRACTED")
    print("-" * 130)
    for (query, expected), got in zip(CASES, results):
        ok = got.tool == expected
        hits += ok
        extracted = got.paper_references or got.topic or ""
        print(f"{'OK' if ok else 'XX':2} {query:<52} {expected:<18} {got.tool:<18} {extracted}")

        print("-" * 130)
        print(f"accuracy: {hits}/{len(CASES)}")
        for (query, expected), got in zip(CASES, results):
            if got.tool != expected:
                print(f"\nMISS: {query!r}\n  wanted {expected}, got {got.tool}\n  reason: {got.reason}")


asyncio.run(main())
