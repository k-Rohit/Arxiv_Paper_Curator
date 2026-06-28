from langchain_core.messages import AIMessage
from ..state import AgentState

async def ainvoke_retrieve_step(state: AgentState) -> dict:
    return {
        "retrieval_attempts" : 1,
        "original_query": "stub-query",
        "messages" : [AIMessage(content="stub")]
    }