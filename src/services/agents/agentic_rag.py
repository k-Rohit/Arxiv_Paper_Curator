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
    score_user_query,
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
        """
        Builds the whole graph for the agentic RAG service. This includes nodes for retrieval, grading, guardrails, and answer generation.
        """
        logger.info("Building LangGraph workflow with context_schema")
        workflow = StateGraph(AgentState, name="AgenticRAGGraph")
        
        # Create tools (these need to be created upfront for ToolNode)
        retriever_tool = create_retriever_tool(
        opensearch_client=self.opensearch,
        embeddings_client=self.embeddings,
        top_k=self.graph_config.top_k,
        use_hybrid=self.graph_config.use_hybrid,
        )
        tools = [retriever_tool]
        
        # Add nodes
        logger.info("Adding nodes to workflow graph")
        workflow.add_node('guardrail_node',score_user_query)
        workflow.add_node('retrieve_node',initiate_retrieve)
        workflow.add_node('out_of_scope_node',ainvoke_out_of_scope_step)
        workflow.add_node("tool_retrieve", ToolNode(tools))
        workflow.add_node('grade_document_node',ainvoke_grade_retrieved_chunks)
        workflow.add_node('rewrite_query_node',rewrite_query)
        workflow.add_node('generate_answer_node',ainvoke_generate_answer)
        
        # Add edges
        logger.info("Configuring graph edges and routing logic")
        
        workflow.add_edge(START, "guardrail_node")
        workflow.add_conditional_edges(
            "guardrail_node",
            route,
            {
                "continue": "retrieve_node",
                "out_of_scope" : "out_of_scope_node"
            }
        )
        workflow.add_edge("out_of_scope_node", END)
        workflow.add_conditional_edges(
            "retrieve_node",
            tools_condition,
            {
                "tools": "tool_retrieve",
                END: END
            }
        )
        workflow.add_edge("tool_retrieve", "grade_documents")
        # After grading → route based on relevance
        workflow.add_conditional_edges(
            "grade_documents",
            lambda state: state.get("routing_decision", "generate_answer"),
            {
                "generate_answer": "generate_answer_node",
                "rewrite_query": "rewrite_query_node",
            },
        )
        # After rewriting → try retrieve again
        workflow.add_edge("rewrite_query_node","retrieve_node")
        
        # After answer generation → done
        workflow.add_edge("generate_answer", END)
        
        # Compile graph
        logger.info("Compiling LangGraph workflow")
        compiled_graph = workflow.compile()
        logger.info("✓ Graph compilation successful")

        return compiled_graph
        
        
        
        