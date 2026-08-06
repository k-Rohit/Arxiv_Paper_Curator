import logging
import time
from typing import Dict, Literal

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.runtime import Runtime

from ..context import Context
from ..models  import ToolSelection
from ..prompts import TOOL_ROUTING_PROMPT
from ..state   import AgentState
from .utils    import get_latest_query

logger = logging.getLogger(__name__)
load_dotenv()

async def select_tool(
    state: AgentState,
    runtime: Runtime[Context], 
) -> Dict:
    """ Select the relevant tool for the user query """
    logger.info("NODE: select_tool")
    start_time = time.time()
    
    graph_config     = runtime.context.graph_config
    original_query   = state.get("original_query") or get_latest_query(state["messages"])
    
    selected_tool = "retrieve"  # default tool
    topic         = None
    reasoning = ""
    
    try:
        model = ChatOpenAI(
            model_name=graph_config.model,
            temperature=graph_config.temperature)
        
        tool_selection_model = model.with_structured_output(ToolSelection)
        tool_selection_prompt = TOOL_ROUTING_PROMPT.format(question = original_query)
        response = await tool_selection_model.ainvoke(tool_selection_prompt)
        
        selected_tool = response.tool
        topic = response.topic
        reasoning = response.reason
        
        logger.info(f"selected_tool={selected_tool}, topic={topic}, reasoning={reasoning}, took={time.time() - start_time:.2f}s")
        
    except Exception as e:
        logger.error(f"Error during tool selection: {e}")
    
    return {
        "tool_selection" : selected_tool,
        "target_topic"   : topic
    }

def route_after_tool_selection(state: AgentState) -> Literal["retrieve_node", "translate_query_node"]:
    """ Read the router's choice and pick the next move' """
    if state.get("tool_selection") == "fetch_live_papers":
        return "translate_query_node"
    else:
        return "retrieve_node"
    