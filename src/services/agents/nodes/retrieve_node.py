from typing import Any, Dict

from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime

from ..context import Context
from ..state   import AgentState
from .utils    import get_latest_query


async def initiate_retrieve(
    state: AgentState,
    runtime: Runtime[Context],
) -> Dict[str, Any]:
    """Emit a tool call to retrieve chunks, OR return fallback if attempts exceeded."""
    query            = get_latest_query(state["messages"])
    current_attempts = state.get("retrieval_attempts", 0)
    max_attempts     = runtime.context.graph_config.max_retrieval_attempts

    updates: Dict[str, Any] = {}

    # Store original query only on first attempt (never overwrite on retries)
    if state.get("original_query") is None:
        updates["original_query"] = query

    # Max attempts reached — fallback
    if current_attempts >= max_attempts:
        fallback_message = (
            f"I couldn't find relevant arXiv papers after {max_attempts} attempts.\n"
            "Try rephrasing your question with more specific technical terms."
        )
        updates["messages"] = [AIMessage(content=fallback_message)]
        return updates

    # New attempt — increment counter, emit tool call
    new_attempt = current_attempts + 1
    updates["retrieval_attempts"] = new_attempt
    updates["messages"] = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id":   f"retrieve_{new_attempt}",
                    "name": "retrieve_papers",
                    "args": {"query": query},
                }
            ],
        )
    ]
    return updates
