import asyncio
import logging
import time
from typing import Dict, List

from dotenv import load_dotenv
from langchain_core.messages import  HumanMessage, ToolMessage, AIMessage
from langchain_openai import ChatOpenAI

from src.services.agents.config  import GraphConfig
from src.services.agents.prompts import REWRITE_PROMPT
from src.services.agents.state   import AgentState
from src.services.agents.nodes.utils    import get_latest_query
from src.services.agents.models import QueryRewriteOutput


logger = logging.getLogger(__name__)
config = GraphConfig()
load_dotenv()

async def rewrite_query(state: AgentState) -> Dict[str, str | List]:
    """Rewrite the original query for better document retrieval using LLM.

    This node uses an LLM to intelligently rewrite the user's query
    to improve the chances of finding relevant documents.

    :param state: Current agent state
    :returns: Dictionary with rewritten_query and updated messages
    """
    logger.info("NODE: rewrite_query")
    start_time = time.time()
    
    # Get the original question - 
    original_query = state.get("original_query") or get_latest_query(state["messages"])
    current_attemps = state.get("retrieval_attempts",0)
    rewritten_query = ""
    reasoning = ""
    
    if current_attemps < config.max_retrieval_attempts:
        try:
            model = ChatOpenAI(model=config.model, temperature=0.4)
            query_rewriter = model.with_structured_output(QueryRewriteOutput)
            query_rewriter_prompt = REWRITE_PROMPT.format(question=original_query)
            response: QueryRewriteOutput = await query_rewriter.ainvoke(query_rewriter_prompt)
            if not response or not response.rewritten_query:
                raise ValueError("LLM failed to return valid structured output for query rewriting")
            
            rewritten_query = response.rewritten_query.strip()
            reasoning = response.reasoning
            logger.info(
            f"'{original_query[:50]}...' -> '{rewritten_query[:50]}...'"
            )
            logger.debug(f"Rewriting reasoning: {reasoning}")
            return {
                "messages" : [HumanMessage(content=rewrite_query)],
                "rewritten_query" : rewritten_query
            }
        except Exception as e:
            logger.error(f"Failed to rewrite query using LLM: {e}")
            logger.warning("Falling back to simple keyword expansion")
            # Fallback to simple expansion if LLM fails
            rewritten_query = f"{original_query} research paper arxiv machine learning"
            reasoning = "Fallback: Simple keyword expansion due to LLM error"
    else:
        return {
                "messages" : [HumanMessage(content=rewrite_query)],
                "rewritten_query" : rewritten_query
                }  
