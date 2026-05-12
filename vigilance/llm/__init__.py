"""LLM provider factory for T5.3."""
from __future__ import annotations

import os

from vigilance.llm.base import LLMProvider, StubLLMProvider


def create_llm(ollama_url: str | None = None) -> LLMProvider:
    """Return an LLMProvider based on environment configuration.

    - If OLLAMA_BASE_URL is set (or ollama_url is passed), returns OllamaLLMProvider
      backed by mistral:7b (fast) and mistral-nemo (reasoning).
    - Otherwise returns StubLLMProvider (no external dependencies, safe for tests).
    """
    url = ollama_url or os.getenv("OLLAMA_BASE_URL")
    if url:
        from vigilance.llm.ollama_provider import OllamaLLMProvider
        return OllamaLLMProvider(base_url=url)
    return StubLLMProvider()


__all__ = ["LLMProvider", "StubLLMProvider", "create_llm"]
