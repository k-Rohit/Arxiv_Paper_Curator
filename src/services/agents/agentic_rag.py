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

class AgenticRag:
    """Agentic RAG service

    This implementation uses:
    - context_schema for dependency injection
    - Runtime[Context] for type-safe access in nodes
    - Direct client invocation (no pre-built runnables)
    - Lightweight nodes as pure functions
    """
    def init(
        self,
        opensearch: OpenSearchClient,
        openaiembeddings: OpenAIEmbeddingsClient,
        openai_ : OpenAIClient,
        graph_config: GraphConfig
    ):
        """Initialize agentic RAG service.

        :param opensearch: Client for document search
        :param openai_: OpenAI Client for Generation
        :param openaiembeddings: Client for embeddings
        :param graph_config: Configuration for graph execution
        """
        
        self.opensearch = opensearch
        self.openaiembeddings = openaiembeddings
        self.openai_ = openai_
        self.graph_config = graph_config
        
        logger.info("Initializing AgenticRAGService with configuration:")
        logger.info(f"  Model: {self.graph_config.model}")
        logger.info(f"  Top-k: {self.graph_config.top_k}")
        logger.info(f"  Hybrid search: {self.graph_config.use_hybrid}")
        logger.info(f"  Max retrieval attempts: {self.graph_config.max_retrieval_attempts}")
        logger.info(f"  Guardrail threshold: {self.graph_config.guardrail_threshold}")
        
        # Build graph once (no runnables needed!)
        self.graph = self._build_graph()
        logger.info("✓ AgenticRAGService initialized successfully")
    
    def _build_graph(self) -> StateGraph:
        pass