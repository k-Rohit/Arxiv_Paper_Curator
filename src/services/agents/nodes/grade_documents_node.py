import asyncio
import logging
import time
from typing import Any, Dict

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI

from ..config  import GraphConfig
from ..models  import GradeDocuments, GradingResult
from ..prompts import GRADE_DOCUMENTS_PROMPT
from ..state   import AgentState
from .utils    import get_latest_context, get_latest_query

logger = logging.getLogger(__name__)
config = GraphConfig()


async def ainvoke_grade_retrieved_chunks(state: AgentState) -> Dict[str, Any]:
    """Grade the retrieved chunks for relevance using an LLM."""
    logger.info("NODE: grade_chunks")
    start_time = time.time()

    question = get_latest_query(state["messages"])
    context  = get_latest_context(state["messages"])

    grading_prompt = GRADE_DOCUMENTS_PROMPT.format(context=context, question=question)

    llm_model  = ChatOpenAI(model=config.model, temperature=config.temperature)
    grader_llm = llm_model.with_structured_output(GradeDocuments)

    results: GradeDocuments = await grader_llm.ainvoke(grading_prompt)   # ← added await

    is_relevant = results.binary_score == "yes"
    route       = "generate_answer" if is_relevant else "rewrite_query"

    logger.info(f"grade={results.binary_score} route={route} took={time.time()-start_time:.2f}s")

    return {
"routing_decision": route,
"grading_results":  [results],
}


# ─── quick manual test ──────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # ── Case 1: RELEVANT chunks
    good_state: AgentState = {
        "messages": [
            HumanMessage(content="What is multi-head attention in transformers?"),
            # (skipping the AIMessage tool_call for brevity — we only need the ToolMessage)
            ToolMessage(
                content=(
                    "[1706.03762] Multi-head attention allows the model to jointly attend "
                    "to information from different representation subspaces at different "
                    "positions. Instead of performing a single attention function, we linearly "
                    "project queries, keys, and values h times with different learned projections."
                    "\n\n---\n\n"
                    "[1706.03762] The Transformer follows this overall architecture using "
                    "stacked self-attention and point-wise, fully connected layers for both the "
                    "encoder and decoder."
                ),
                tool_call_id="retrieve_1",
                name="retrieve_papers",
            ),
        ],
    }

    # ── Case 2: IRRELEVANT chunks
    bad_state: AgentState = {
        "messages": [
            HumanMessage(content="What is multi-head attention in transformers?"),
            ToolMessage(
                content=(
                    "[9999.99999] The cheesecake recipe requires 250g of cream cheese, "
                    "150g of sugar, and 3 eggs. Bake at 160C for 45 minutes."
                    "\n\n---\n\n"
                    "[8888.88888] Best bouldering routes in Fontainebleau include Cul de Chien "
                    "and Rocher Canon. Bring good shoes."
                ),
                tool_call_id="retrieve_1",
                name="retrieve_papers",
            ),
        ],
    }

async def _run():
    print("\n=== Case 1: RELEVANT chunks ===")
    result_good = await ainvoke_grade_retrieved_chunks(good_state)
    print(result_good)

    print("\n=== Case 2: IRRELEVANT chunks ===")
    result_bad = await ainvoke_grade_retrieved_chunks(bad_state)
    print(result_bad)

    asyncio.run(_run())
