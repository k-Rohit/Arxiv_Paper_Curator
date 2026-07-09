import logging

from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from src.services.embeddings.openai_client import OpenAIEmbeddingsClient
from src.services.openai_ import OpenAIClient
from src.services.opensearch.client import OpenSearchClient

from langchain_core.messages import HumanMessage, AIMessage

from .config import GraphConfig
from .context import Context
from .nodes import (
    ainvoke_generate_answer,
    ainvoke_grade_retrieved_chunks,
    ainvoke_out_of_scope_step,
    initiate_retrieve,
    rewrite_query,
    route,
    score_user_query,
)
from .state import AgentState
from .tools import create_retriever_tool

logger = logging.getLogger(__name__)


class AgenticRag:
    """Agentic RAG service.

    Wires the LangGraph workflow: guardrail → retrieve → grade → (rewrite or generate) → END.
    """

    def __init__(
        self,
        opensearch: OpenSearchClient,
        openaiembeddings: OpenAIEmbeddingsClient,
        openai_: OpenAIClient,
        graph_config: GraphConfig,
    ):
        """Initialize agentic RAG service.

        :param opensearch:       Client for document search
        :param openaiembeddings: Client for embeddings
        :param openai_:          OpenAI client for generation
        :param graph_config:     Configuration for graph execution
        """
        self.opensearch       = opensearch
        self.openaiembeddings = openaiembeddings
        self.openai_          = openai_
        self.graph_config     = graph_config

        logger.info("Initializing AgenticRAGService with configuration:")
        logger.info(f"  Model:                  {self.graph_config.model}")
        logger.info(f"  Top-k:                  {self.graph_config.top_k}")
        logger.info(f"  Hybrid search:          {self.graph_config.use_hybrid}")
        logger.info(f"  Max retrieval attempts: {self.graph_config.max_retrieval_attempts}")
        logger.info(f"  Guardrail threshold:    {self.graph_config.guardrail_threshold}")

        self.graph = self._build_graph()
        logger.info("✓ AgenticRAGService initialized successfully")

    def _build_graph(self) -> StateGraph:
        """Build and compile the LangGraph workflow."""
        logger.info("Building LangGraph workflow with context_schema=Context")
        workflow = StateGraph(AgentState, context_schema=Context)

        # Tool the LLM calls to retrieve chunks
        retriever_tool = create_retriever_tool(
            opensearch_client=self.opensearch,
            embeddings_client=self.openaiembeddings,
            top_k=self.graph_config.top_k,
            use_hybrid=self.graph_config.use_hybrid,
        )
        tools = [retriever_tool]

        # ─── Nodes ───────────────────────────────────────────────
        logger.info("Adding nodes to workflow graph")
        workflow.add_node("guardrail_node",       score_user_query)
        workflow.add_node("retrieve_node",        initiate_retrieve)
        workflow.add_node("out_of_scope_node",    ainvoke_out_of_scope_step)
        workflow.add_node("tool_retrieve",        ToolNode(tools))
        workflow.add_node("grade_document_node",  ainvoke_grade_retrieved_chunks)
        workflow.add_node("rewrite_query_node",   rewrite_query)
        workflow.add_node("generate_answer_node", ainvoke_generate_answer)

        # ─── Edges ───────────────────────────────────────────────
        logger.info("Configuring graph edges and routing logic")

        # START → guardrail
        workflow.add_edge(START, "guardrail_node")

        # guardrail → retrieve OR out_of_scope
        workflow.add_conditional_edges(
            "guardrail_node",
            route,
            {
                "continue":     "retrieve_node",
                "out_of_scope": "out_of_scope_node",
            },
        )

        # out_of_scope → END
        workflow.add_edge("out_of_scope_node", END)

        # retrieve → tool_retrieve (via tool_calls) OR END (max attempts hit)
        workflow.add_conditional_edges(
            "retrieve_node",
            tools_condition,
            {
                "tools": "tool_retrieve",
                END:     END,
            },
        )

        # tool_retrieve → grade
        workflow.add_edge("tool_retrieve", "grade_document_node")

        # grade → generate OR rewrite (based on state["routing_decision"])
        workflow.add_conditional_edges(
            "grade_document_node",
            lambda state: state.get("routing_decision", "generate_answer"),
            {
                "generate_answer": "generate_answer_node",
                "rewrite_query":   "rewrite_query_node",
            },
        )

        # rewrite → retrieve (loop back)
        workflow.add_edge("rewrite_query_node", "retrieve_node")

        # generate → END
        workflow.add_edge("generate_answer_node", END)

        logger.info("Compiling LangGraph workflow")
        compiled_graph = workflow.compile()
        logger.info("✓ Graph compilation successful")

        return compiled_graph

    async def ask(self, query: str, user_id: str = "api_user") -> dict:
        """Run the agentic graph end-to-end for one user query.

        :param query:   The user's question
        :param user_id: Optional user identifier (for tracing / logs)
        :returns:       Dict with query, answer, sources, retrieval_attempts
        """
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")

        # Initial state — every AgentState field explicitly set
        state_input: AgentState = {
            "messages":              [HumanMessage(content=query)],
            "retrieval_attempts":    0,
            "guardrail_result":      None,
            "routing_decision":      None,
            "grading_results":       [],
            "original_query":        None,
            "rewritten_query":       None,
            "sources":               None,
            "relevant_sources":      [],
            "relevant_tool_artefacts": None,
            "metadata":              {"user_id": user_id},
        }

        # Runtime dependencies bundled for every node
        runtime_context = Context(
            opensearch_client=self.opensearch,
            embeddings_client=self.openaiembeddings,
            openai_client=self.openai_,
            graph_config=self.graph_config,
        )

        logger.info(f"Invoking graph for user_id={user_id} query={query[:80]!r}")
        result = await self.graph.ainvoke(state_input, context=runtime_context)

        return {
            "query":              query,
            "answer":             self._extract_answer(result),
            "sources":            self._extract_sources(result),
            "reasoning_steps":    self._extract_reasoning_steps(result),
            "retrieval_attempts": result.get("retrieval_attempts", 0),
            "grading_results":    result.get("grading_results", []),
        }

    @staticmethod
    def _extract_answer(result: dict) -> str:
        """Walk messages backwards to find the final AIMessage from the agent."""
        for msg in reversed(result.get("messages", [])):
            if isinstance(msg, AIMessage) and msg.content:
                return msg.content
        return "No answer generated."

    @staticmethod
    def _extract_sources(result: dict) -> list:
        """
        This method is used for extracting the sources from the generated answer
        """
        sources = []
        relevant_sources = result.get("relevant_sources", [])
        
        for source in relevant_sources:
            if hasattr(source,"to_dict"):
                sources.append(source.to_dict())
            elif isinstance(source,dict):
                sources.append(source)
        
        return sources
    
    @staticmethod
    def _extract_reasoning_steps(result: dict) -> list[str]:
        """Extract reasoning steps from graph result."""
        steps = []
        retrieval_attempts = result.get("retrieval_attempts", 0)
        guardrail_result   = result.get("guardrail_result")
        grading_results    = result.get("grading_results", [])

        if guardrail_result:
            steps.append(f"Validated query scope (score: {guardrail_result.score}/100)")

        if retrieval_attempts > 0:
            steps.append(f"Retrieved documents ({retrieval_attempts} attempt(s))")

        if grading_results:
            relevant_count = sum(1 for g in grading_results if g.is_relevant)
            steps.append(f"Graded documents ({relevant_count} relevant)")

        if result.get("rewritten_query"):
            steps.append("Rewritten query for better results")

        steps.append("Generated answer from context")

        return steps

    def visualize(self, format: str = "mermaid", save_to: str | None = None) -> str | bytes:
        """Visualize the compiled graph in mermaid, png, or ascii form.

        :param format:  One of "mermaid", "png", "ascii"
        :param save_to: Optional path to save the output (e.g. "graph.png")
        :returns:       str for "mermaid"/"ascii", bytes for "png"
        :raises ValueError: for unknown formats
        """
        drawers = {
            "mermaid": lambda g: g.draw_mermaid(),
            "png":     lambda g: g.draw_mermaid_png(),
            "ascii":   lambda g: g.draw_ascii(),
        }
        if format not in drawers:
            raise ValueError(f"Unknown format {format!r}. Use one of: {list(drawers)}")

        logger.info(f"Generating graph visualization: format={format}")
        try:
            output = drawers[format](self.graph.get_graph())
            if save_to:
                mode = "wb" if isinstance(output, bytes) else "w"
                with open(save_to, mode) as f:
                    f.write(output)
                logger.info(f"✓ Saved {format} visualization to {save_to}")
            else:
                logger.info(f"✓ Generated {format} visualization")
            return output
        except Exception as e:
            logger.error(f"Failed to generate {format} visualization: {e}")
            raise
