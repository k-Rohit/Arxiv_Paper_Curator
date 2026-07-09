import logging
from typing import Dict, List

from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime

from ..context import Context
from ..state   import AgentState
from .utils    import get_latest_query

logger = logging.getLogger(__name__)


async def ainvoke_out_of_scope_step(
    state: AgentState,
    runtime: Runtime[Context],
) -> Dict[str, List[AIMessage]]:
    """Polite refusal for off-topic queries. No LLM call — fixed template."""
    logger.info("NODE: out_of_scope")
    question = get_latest_query(state["messages"])

    response_text = (
        "I apologize, but I can only help with questions about academic research papers "
        "in Computer Science, Artificial Intelligence, and Machine Learning from arXiv.\n\n"
        f"Your question: '{question}'\n\n"
        "This appears to be outside my domain of expertise. Consider trying:\n"
        "- General-purpose AI assistants for broad knowledge questions\n"
        "- Domain-specific resources for topics outside CS/AI/ML\n"
        "- Technical documentation for specific software/tools\n\n"
        "If you have a question about AI/ML research papers, I'd be happy to help!"
    )

    return {"messages": [AIMessage(content=response_text)]}
