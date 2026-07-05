import logging
import time
from typing import Dict, List, Optional

from langchain_core.messages import HumanMessage
from langfuse.langchain import CallbackHandler
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from src.services.embeddings.openai_client import OpenAIEmbeddingsClient
from src.services.openai_ import OpenAIClient
from src.services.opensearch.client import OpenSearchClient

from .config import GraphConfig
from .nodes import (
    ainvoke_generate_answer,
    ainvoke_grade_retrieved_chunks,
    ainvoke_out_of_scope_step,
    route,
    ainvoke_out_of_scope_step,
    initiate_retrieve,
    rewrite_query
)
from .state import AgentState
from .tools import create_retriever_tool

logger = logging.getLogger(__name__)

