from typing import Dict, Literal

from dotenv import load_dotenv
from typing import cast
from langchain_openai import ChatOpenAI

from ..config  import GraphConfig
from ..models  import GuardrailScoring
from ..prompts import GUARDRAIL_PROMPT
from ..state   import AgentState
from .utils    import get_latest_query

load_dotenv()

config = GraphConfig()


async def score_user_query(state: AgentState) -> Dict[str, GuardrailScoring]:
    query  = get_latest_query(state["messages"])
    prompt = GUARDRAIL_PROMPT.format(question=query)

    model      = ChatOpenAI(model=config.model, temperature=0.0)
    scorer_llm = model.with_structured_output(GuardrailScoring)

    response = await scorer_llm.ainvoke(prompt)
    return {"guardrail_result": response}


def route(state: AgentState) -> Literal["continue", "out_of_scope"]:
    """Route based on the guardrail score."""
    score = state["guardrail_result"].score
    return "continue" if score >= config.guardrail_threshold else "out_of_scope"
