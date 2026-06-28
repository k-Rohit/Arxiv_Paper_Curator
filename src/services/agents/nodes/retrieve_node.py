from typing import Dict, Any

from langchain_core.messages import AIMessage

from ..config import GraphConfig
from ..state  import AgentState
from .utils   import get_latest_query

config = GraphConfig()

async def initiate_retrieve(state: AgentState) -> dict:
    # get the latest message
    query = get_latest_query(state['messages'])
    """Emit a tool call to retrieve chunks, OR return fallback if attempts exceeded."""
    current_attempts = state.get('retrieval_attempts',0)
    max_attempts = config.max_retrieval_attempts    
    
    updates = {}
    # original_query is None on attempt 1 because no node has set it yet. The is None check means "only set on the first call, never overwrite."
    if state.get("original_query") is None:
        updates["original_query"] = query
    
    # max attempts reached
    if current_attempts >= max_attempts:
        fallback_message = (
            f"I couldn't find relevant arXiv papers after {max_attempts} attempts.\n"
            "Try rephrasing your question with more specific technical terms."
        )
        updates["messages"] = [AIMessage(content=fallback_message)]
        return updates

    # new attempt (if max attempts haven't been reached) - 
    new_attempt = current_attempts + 1
    updates["retrieval_attempts"] = new_attempt
    updates["messages"] = [
        AIMessage(
            content="",
            tool_calls = [
                {
                    "id": f"retrieve_{new_attempt}",
                    "name" : "retrieve_papers",
                    "args" : {"query": query}
                }
            ],
        )
    ]
    return updates
    
    