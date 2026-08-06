import logging
import time
from typing import Any, Dict

from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime

from ..context import Context
from ..state   import AgentState
from .utils    import get_latest_tool_artifact

logger = logging.getLogger(__name__)


async def initiate_live_fetch(
    state: AgentState,
    runtime: Runtime[Context],
) -> Dict[str, Any]:
    """Emit the tool call that fetches new papers from arXiv.

    Deterministic — no LLM call. The router already decided we're fetching, and
    translate_query_node already produced the arXiv query, so this node only has to
    package those into the tool_calls payload that ToolNode executes.

    Mirrors `initiate_retrieve`'s hand-built tool call.
    """
    logger.info("NODE: initiate_live_fetch")

    graph_config       = runtime.context.graph_config
    arxiv_search_query = state.get("arxiv_search_query")
    topic_label        = state.get("live_fetch_topic_label") or state.get("target_topic") or ""

    # translate_query_node always sets this (it has its own fallback), so an empty value
    # means the graph reached here by an unexpected path. Bail out with a plain message
    # rather than emitting a tool call the tool can't act on.
    if not arxiv_search_query:
        logger.error("initiate_live_fetch reached without an arxiv_search_query — skipping fetch")
        return {
            "messages": [AIMessage(content="I wasn't able to work out what to search arXiv for.")],
        }

    logger.info(f"live fetch call | query={arxiv_search_query!r} max={graph_config.live_fetch_max_results}")

    return {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id":   "live_fetch_1",
                        "name": "fetch_live_papers",
                        "args": {
                            "arxiv_search_query": arxiv_search_query,
                            "topic_label":        topic_label,
                            "max_results":        graph_config.live_fetch_max_results,
                        },
                    }
                ],
            )
        ]
    }


async def finalize_live_fetch(
    state: AgentState,
    runtime: Runtime[Context],
) -> Dict[str, Any]:
    """Record what the live fetch actually did, for the user-facing reasoning steps.

    The tool already wrote a human-readable summary into the ToolMessage content
    (which generate_answer_node reads as its context). This node pulls the structured
    artifact so the numbers land in `live_fetch_log` -> `reasoning_steps` in the API
    response, instead of the user only seeing prose.
    """
    logger.info("NODE: finalize_live_fetch")
    start_time = time.time()

    artifact = get_latest_tool_artifact(state["messages"])

    # The retriever tool's artifact is a list of Documents; this tool's is a dict.
    # Anything else means we're looking at the wrong ToolMessage.
    if not isinstance(artifact, dict):
        logger.warning(f"finalize_live_fetch got unexpected artifact type: {type(artifact).__name__}")
        return {"live_fetch_log": ["Searched arXiv for new papers."]}

    topic_label = artifact.get("topic_label", "the topic")
    indexed     = artifact.get("papers_indexed", 0)
    skipped     = artifact.get("papers_skipped_existing", 0)
    chunks      = artifact.get("chunks_indexed", 0)

    if indexed:
        line = f"Fetched {indexed} new paper(s) on '{topic_label}' from arXiv ({chunks} chunks indexed)"
        if skipped:
            line += f"; {skipped} already in the corpus"
    elif skipped:
        line = f"Searched arXiv for '{topic_label}' — all {skipped} result(s) already in the corpus"
    else:
        line = f"Searched arXiv for '{topic_label}' — no usable new papers found"

    logger.info(f"{line} | took={time.time() - start_time:.2f}s")
    return {"live_fetch_log": [line]}
