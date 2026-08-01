import logging
import time
from typing import Any, Dict

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.runtime import Runtime

from ..context import Context
from ..models  import GradeDocuments, GradingResult, SourceItem
from ..prompts import GRADE_DOCUMENTS_PROMPT
from ..state   import AgentState
from .utils    import get_latest_context, get_latest_query, get_latest_tool_artifact

logger = logging.getLogger(__name__)
load_dotenv()


async def ainvoke_grade_retrieved_chunks(
    state: AgentState,
    runtime: Runtime[Context],
) -> Dict[str, Any]:
    """Grade the retrieved chunks for relevance using an LLM."""
    logger.info("NODE: grade_chunks")
    start_time = time.time()

    graph_config = runtime.context.graph_config
    question     = get_latest_query(state["messages"])
    context      = get_latest_context(state["messages"])

    grading_prompt = GRADE_DOCUMENTS_PROMPT.format(context=context, question=question)

    llm_model  = ChatOpenAI(model=graph_config.model, temperature=graph_config.temperature)
    grader_llm = llm_model.with_structured_output(GradeDocuments)

    results: GradeDocuments = await grader_llm.ainvoke(grading_prompt)

    is_relevant = results.binary_score == "yes"
    route       = "generate_answer" if is_relevant else "rewrite_query"

    grading_result = GradingResult(
        document_id="retrieved_batch",
        is_relevant=is_relevant,
        reasoning=results.reasoning,
    )
    logger.info(f"grade={results.binary_score} route={route} took={time.time()-start_time:.2f}s")

    relevant_sources: list[SourceItem] = []
    if is_relevant:
        for doc in get_latest_tool_artifact(state["messages"]):
            authors = doc.metadata.get("authors", "")
            relevant_sources.append(
                SourceItem(
                    arxiv_id=doc.metadata.get("arxiv_id", ""),
                    title=doc.metadata.get("title", ""),
                    authors=authors.split(", ") if authors else [],
                    url=doc.metadata.get("source", ""),
                    relevance_score=doc.metadata.get("score", 0.0),
                )
            )

    return {
        "routing_decision": route,
        "grading_results":  [grading_result],
        "relevant_sources": relevant_sources,
    }
