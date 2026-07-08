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

Valid actions (TELECOM):    block_ip, revoke_session, notify_soc, update_acl
Valid actions (INDUSTRY_4): isolate_plc, revoke_ot_session, notify_soc, update_zt_policy
Valid actions (MARITIME):   block_vessel_access, quarantine_cargo_system, notify_port_authority, notify_soc, update_vessel_acl
Valid actions (FINANCE):    freeze_account, block_transaction, notify_fraud_team, escalate_to_compliance, notify_soc
"""

_EXTRACT_FIELDS_INSTRUCTION = """
Extract the requested fields from the provided security event text.
Respond with a single JSON object containing ONLY the requested field names as keys.
Use null for fields that cannot be determined from the text — do NOT guess or infer.

Field-specific rules:
- "pilot": must be one of TELECOM, MARITIME, FINANCE, INDUSTRY_4.
  Return null unless the text explicitly mentions telecom/network operators, maritime/vessel/port,
  banking/finance/fraud, or industrial control systems/OT/SCADA/PLC.
- "severity": must be one of LOW, MEDIUM, HIGH, CRITICAL. Return null if not inferable.
- "ot_protocol": only for industrial OT protocols (OPC-UA, Modbus, DNP3, IEC-104). Return null
  for telecom protocols (SS7, Diameter, SIP) or any non-OT protocol.
- "ot_safety_flag": true only if the text explicitly mentions a safety system or OT safety risk.
- All numeric fields (count, nodes_affected, fraud_score): return null if not present in text.
- Cross-pilot fields: return null for fields that belong to a different sector than the event.
  E.g. vessel_id/port_zone/ais_mmsi for non-maritime events; plc_id/scada_zone for non-OT events;
  account_id/fraud_score for non-finance events; subscriber_id/imsi for non-telecom events.

No prose, no markdown, no explanation — JSON object only.
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
        timeout: int = 300,
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

        Returns free-form text — no JSON constraint is applied, so callers
        (e.g. PolicyTranslator) can receive Rego, natural language, or any
        other non-JSON output format.
        """
        return self._chat(self.reasoning_model, system_prompt, messages, response_format=None)

    def semantic_check(self, system_prompt: str, messages: list[dict]) -> str:
        """Run a semantic guardrail review using the fast model (mistral:7b).

        Called by C5 SafetyGate for borderline/ESCALATE cases to obtain a
        second-opinion verdict before halting automated execution.
        """
        semantic_system = (
            system_prompt
            + "\n\nRESPONSE FORMAT: respond with valid JSON only.\n"
            '{"semantic_verdict": "APPROVE"|"REJECT", "reason": "<short explanation>"}'
        )
        return self._chat(self.fast_model, semantic_system, messages, response_format="json")

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
        raw_response = self._chat(self.fast_model, system, messages, response_format="json")

        try:
            result = json.loads(raw_response)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, ValueError):
            logger.warning("extract_fields: LLM returned non-JSON, using empty dict")

        return {field: None for field in fields}

    def _chat(
        self,
        model: str,
        system_prompt: str,
        messages: list[dict],
        response_format: str | None = None,
    ) -> str:
        """POST to /api/chat and return the assistant message content.

        Args:
            response_format: Pass ``"json"`` to engage Ollama's constrained JSON
                sampler (only for methods that truly need JSON output).
                Pass ``None`` (default) for free-form output such as Rego rules.
        """
        import requests

        payload: dict = {
            "model": model,
            "messages": [{"role": "system", "content": system_prompt}] + messages,
            "stream": False,
            "options": {"temperature": 0.1},
        }
        if response_format is not None:
            payload["format"] = response_format

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
