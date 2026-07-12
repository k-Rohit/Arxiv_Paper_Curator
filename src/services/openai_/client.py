"""OpenAI chat-completion LLM client for RAG."""

import json
import logging
from typing import Any, Dict, List

from langsmith import traceable
from openai import AsyncOpenAI

from src.config import OpenAIClientSettings
from src.services.openai_.prompts import RAGPromptBuilder, ResponseParser

logger = logging.getLogger(__name__)


class OpenAIClient:
    """Client for OpenAI chat completions, RAG-focused."""

    def __init__(self, settings: OpenAIClientSettings):
        self.settings = settings
        self._client = AsyncOpenAI(
            api_key=settings.api_key or None,
            max_retries=settings.max_retries,
            timeout=settings.timeout_seconds,
        )
        self.prompt_builder = RAGPromptBuilder()
        self.response_parser = ResponseParser()
        logger.info(f"OpenAI client initialized: model={settings.model}")

    async def chat(self, system_prompt: str, user_prompt: str) -> str:
        """Generic chat call — returns raw text from the LLM."""
        response = await self._client.chat.completions.create(
            model=self.settings.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=self.settings.max_tokens,
            temperature=self.settings.temperature,
            top_p=self.settings.top_p,
        )
        return response.choices[0].message.content.strip()

    @traceable(name="generate_rag_response", run_type="llm")
    async def generate_rag_response(self, query: str, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """End-to-end RAG generation: build prompt → call LLM → parse response.

        :param query: User's question
        :param chunks: Retrieved chunks (from OpenSearch)
        :returns: Dict matching RAGResponse shape (answer, sources, citations, confidence)
        """
        system_prompt = self.prompt_builder.system_prompt
        user_prompt = self.prompt_builder.create_rag_prompt(query=query, chunks=chunks)

        raw_text = await self.chat(system_prompt=system_prompt, user_prompt=user_prompt)
        logger.info(f"LLM returned {len(raw_text)} chars for query: '{query[:50]}'")

        return self.response_parser.parse_structured_response(raw_text)

    async def generate_structured_rag_response(self, query: str, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """RAG generation with OpenAI's JSON-mode for structured output.

        Uses `response_format={"type": "json_object"}` so the LLM is forced to
        return valid JSON matching the RAGResponse shape.

        :param query: User's question
        :param chunks: Retrieved chunks
        :returns: Dict matching RAGResponse shape
        """
        system_prompt = (
            self.prompt_builder.system_prompt
            + "\n\nReturn the response as JSON matching this schema: "
            + json.dumps(self.prompt_builder.create_structured_prompt(query, chunks)["format"])
        )
        user_prompt = self.prompt_builder.create_rag_prompt(query=query, chunks=chunks)

        response = await self._client.chat.completions.create(
            model=self.settings.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=self.settings.max_tokens,
            temperature=self.settings.temperature,
            top_p=self.settings.top_p,
            response_format={"type": "json_object"},
        )
        raw_text = response.choices[0].message.content.strip()
        return self.response_parser.parse_structured_response(raw_text)
