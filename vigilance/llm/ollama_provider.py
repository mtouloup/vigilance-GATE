"""OllamaLLMProvider — real LLM backend via Ollama (mistral:7b + mistral-nemo)."""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

# Models match the T5.3 spec exactly
FAST_MODEL = "mistral:7b"        # C1 fallback parser, C5 semantic guardrail
REASONING_MODEL = "mistral-nemo" # C2 agentic loop, C3 NL→Rego policy translation

# Injected into every agentic-loop system prompt so the model returns parseable JSON
_AGENTIC_JSON_INSTRUCTION = """
RESPONSE FORMAT (strictly enforced):
- You MUST respond with valid JSON only. No prose, no markdown, no code fences.

When you need to call a tool:
  {"tool_call": "<tool_name>", "params": {"<key>": "<value>"}}

Available tools:
  query_siem_logs(target: str, window_min: int)
  query_iam_sessions(target: str)
  query_threat_intel(ioc: str)

When you have enough information to decide:
  {"decision": "<THREAT_TYPE>", "actions": ["<action1>", ...], "confidence": <0.0-1.0>}

Valid actions (TELECOM):  block_ip, revoke_session, notify_soc, update_acl
Valid actions (INDUSTRY_4): isolate_plc, revoke_ot_session, notify_soc, update_zt_policy
"""

_EXTRACT_FIELDS_INSTRUCTION = """
Extract the requested fields from the provided security event text.
Respond with a single JSON object containing ONLY the requested field names as keys.
Use null for fields that cannot be determined. No prose, no markdown.
"""


class OllamaLLMProvider:
    """LLM provider backed by a local Ollama instance.

    Uses mistral:7b for fast extraction tasks and mistral-nemo for multi-turn
    agentic reasoning, matching the T5.3 spec.

    Args:
        base_url: Ollama API base URL (default: http://localhost:11434).
        fast_model: Model for C1/C5 extraction tasks.
        reasoning_model: Model for C2/C3 reasoning tasks.
        timeout: HTTP request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        fast_model: str = FAST_MODEL,
        reasoning_model: str = REASONING_MODEL,
        timeout: int = 120,
    ) -> None:
        try:
            import requests as _req  # noqa: F401
        except ImportError:
            raise RuntimeError(
                "requests is required for OllamaLLMProvider. "
                "Install with: pip install requests>=2.31"
            )
        self._base_url = base_url.rstrip("/")
        self.fast_model = fast_model
        self.reasoning_model = reasoning_model
        self._timeout = timeout

    def complete(self, system_prompt: str, messages: list[dict]) -> str:
        """Run a chat completion using the reasoning model (mistral-nemo).

        Augments the system prompt with JSON format instructions so the
        agentic loop always receives parseable output.
        """
        augmented_system = system_prompt + _AGENTIC_JSON_INSTRUCTION
        return self._chat(self.reasoning_model, augmented_system, messages)

    def extract_fields(self, raw_text: str, fields: list[str]) -> dict:
        """Extract structured fields from raw text using the fast model (mistral:7b).

        Returns a dict mapping each requested field name to its extracted value
        (or None if not found).
        """
        system = _EXTRACT_FIELDS_INSTRUCTION
        user_content = (
            f"Extract these fields: {fields}\n\n"
            f"From this security event:\n{raw_text[:2000]}"
        )
        messages = [{"role": "user", "content": user_content}]
        raw_response = self._chat(self.fast_model, system, messages)

        try:
            result = json.loads(raw_response)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, ValueError):
            logger.warning("extract_fields: LLM returned non-JSON, using empty dict")

        return {field: None for field in fields}

    def _chat(self, model: str, system_prompt: str, messages: list[dict]) -> str:
        """POST to /api/chat and return the assistant message content."""
        import requests

        payload = {
            "model": model,
            "messages": [{"role": "system", "content": system_prompt}] + messages,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1},  # Low temperature for deterministic JSON
        }

        url = f"{self._base_url}/api/chat"
        try:
            resp = requests.post(url, json=payload, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()
            return data["message"]["content"].strip()
        except requests.exceptions.ConnectionError as exc:
            raise RuntimeError(
                f"Cannot reach Ollama at {self._base_url}. "
                "Is the Ollama container running? Check OLLAMA_BASE_URL."
            ) from exc
        except requests.exceptions.Timeout:
            raise RuntimeError(
                f"Ollama request timed out after {self._timeout}s "
                f"(model={model}). Consider increasing OLLAMA_TIMEOUT."
            )
        except Exception as exc:
            logger.error(f"Ollama chat error (model={model}): {exc}")
            raise
