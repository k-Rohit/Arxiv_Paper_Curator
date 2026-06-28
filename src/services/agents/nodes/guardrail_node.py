from ..state import AgentState
from ..prompts import GUARDRAIL_PROMPT
from typing import Literal
from ..models import GuardrailScoring, RoutingDecision

def guardrail(state: AgentState) -> dict:
    return {'guardrail_result' :GuardrailScoring(score=90, reason="Query is relevant to AI")}

def continue_after_guardrail(state: AgentState) -> Literal["continue", "out_of_scope"]:
    """STUB — always continue."""
    return "continue"
