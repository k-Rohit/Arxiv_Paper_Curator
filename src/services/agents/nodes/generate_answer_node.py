import asyncio
import logging
import time
from typing import Dict, List

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI

from ..config  import GraphConfig
from ..prompts import GENERATE_ANSWER_PROMPT
from ..state   import AgentState
from .utils    import get_latest_context, get_latest_query

logger = logging.getLogger(__name__)
config = GraphConfig()
load_dotenv()


async def ainvoke_generate_answer(state: AgentState) -> Dict[str, List[AIMessage]]:
    """Generate the final answer from the retrieved chunks."""
    logger.info("NODE: generate_answer")
    start_time = time.time()

    question = get_latest_query(state["messages"])
    context  = get_latest_context(state["messages"])

    if not context:
        context = "No relevant documents found."

        prompt = GENERATE_ANSWER_PROMPT.format(context=context, question=question)

        llm = ChatOpenAI(model=config.model, temperature=config.temperature)
        response = await llm.ainvoke(prompt)

        answer = response.content if hasattr(response, "content") else str(response)

        logger.info(f"answer_len={len(answer)} took={time.time()-start_time:.2f}s")

        return {"messages": [AIMessage(content=answer)]}


    # ─── quick manual test ──────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    test_state: AgentState = {
        "messages": [
            HumanMessage(content="What is multi-head attention in transformers?"),
            ToolMessage(
                content=(
                    "[1706.03762] Multi-head attention allows the model to jointly attend "
                    "to information from different representation subspaces at different "
                    "positions. Instead of performing a single attention function, we linearly "
                    "project queries, keys, and values h times with different learned projections."
                    "\n\n---\n\n"
                    "[1706.03762] The Transformer follows this overall architecture using "
                    "stacked self-attention and point-wise, fully connected layers for both the "
                    "encoder and decoder."
                ),
                tool_call_id="retrieve_1",
                name="retrieve_papers",
            ),
        ],
    }

async def _run():
    result = await ainvoke_generate_answer(test_state)
    print("\n=== Generated answer ===")
    print(result["messages"][0].content)

    asyncio.run(_run())
