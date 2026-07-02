import logging
from typing import Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from ..models import ReasoningStep, SourceItem, ToolArtefact

logger = logging.getLogger(__name__)

def get_latest_query(messages: List):
    """Get the latest user query from messages.

    :param messages: List of messages
    :returns: Latest query text
    :raises ValueError: If no user query found
    """
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg.content

        raise ValueError("No user query found in messages")

def get_latest_context(messages: List):
    """ 
    Get the latest context message (mainly for ToolMessage)
    :param messages: List of messages
    :returns: Latest context which it contains
    """
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage):
            return msg.content if hasattr(msg,"content") else ""
    return ""