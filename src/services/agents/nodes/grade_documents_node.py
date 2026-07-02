import logging
import time
from typing import Any, Dict

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

from ..config  import GraphConfig
from ..models  import GradeDocuments, GradingResult
from ..prompts import GRADE_DOCUMENTS_PROMPT
from ..state   import AgentState
from .utils    import get_latest_context, get_latest_query

logger = logging.getLogger(__name__)
config = GraphConfig()
load_dotenv()


async def ainvoke_grade_retrieved_chunks(state: AgentState) -> Dict[str, Any]:
    """Grade the retrieved chunks for relevance using an LLM."""
    logger.info("NODE: grade_chunks")
    start_time = time.time()

    question = get_latest_query(state["messages"])
    context  = get_latest_context(state["messages"])

    grading_prompt = GRADE_DOCUMENTS_PROMPT.format(context=context, question=question)

    llm_model  = ChatOpenAI(model=config.model, temperature=config.temperature)
    grader_llm = llm_model.with_structured_output(GradeDocuments)

    results: GradeDocuments = await grader_llm.ainvoke(grading_prompt)

    is_relevant = results.binary_score == "yes"
    route       = "generate_answer" if is_relevant else "rewrite_query"
    
    grading_result = GradingResult(
        document_id="retrieved_batch",
        is_relevant=is_relevant,
        reasoning=results.reasoning
    )
    logger.info(f"grade={results.binary_score} route={route} took={time.time()-start_time:.2f}s")

    return {
        "routing_decision": route,
        "grading_results":  [grading_result],
    }
    