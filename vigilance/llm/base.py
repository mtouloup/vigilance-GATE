from __future__ import annotations
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Abstract LLM provider interface."""

    @abstractmethod
    def complete(self, system_prompt: str, messages: list[dict]) -> str:
        """Send a chat completion request and return the response text."""
        ...

    @abstractmethod
    def extract_fields(self, raw_text: str, fields: list[str]) -> dict:
        """Extract structured fields from raw text."""
        ...


class StubLLMProvider(LLMProvider):
    """Returns plausible stub responses without real API calls.

    All responses are deterministic so tests always pass.
    """

    # Stub tool-call sequence for the agentic loop
    _TOOL_TURN_1 = (
        '{"tool_call": "query_siem_logs", "params": {"target": "nms-01", "window_min": 60}}'
    )
    _TOOL_TURN_2 = (
        '{"tool_call": "query_iam_sessions", "params": {"target": "nms-01"}}'
    )

    # Final decisions keyed by pilot keyword in system prompt
    _DECISION_TELECOM = (
        '{"decision": "CREDENTIAL_STUFFING", '
        '"actions": ["block_ip", "revoke_session", "notify_soc"], '
        '"confidence": 0.96}'
    )
    _DECISION_INDUSTRY4 = (
        '{"decision": "OT_LATERAL_MOVE", '
        '"actions": ["isolate_plc", "revoke_ot_session", "notify_soc", "update_zt_policy"], '
        '"confidence": 0.91}'
    )
    _DECISION_MARITIME = (
        '{"decision": "AIS_SPOOFING", '
        '"actions": ["block_vessel_access", "quarantine_cargo_system", "notify_port_authority", "notify_soc"], '
        '"confidence": 0.88}'
    )
    _DECISION_FINANCE = (
        '{"decision": "ACCOUNT_TAKEOVER", '
        '"actions": ["freeze_account", "block_transaction", "notify_fraud_team", "notify_soc"], '
        '"confidence": 0.93}'
    )

    # Stub OPA/Rego policy
    _REGO_STUB = (
        'package vigilance.policy\n\ndefault allow = false\n\n'
        'allow {\n    input.action == "block_ip"\n    input.src_ip != ""\n}\n'
    )

    def complete(self, system_prompt: str, messages: list[dict]) -> str:
        """Return a deterministic stub response based on context keywords."""
        # Check the last user/tool message to determine turn
        last_content = ""
        for msg in reversed(messages):
            if msg.get("role") in ("user", "tool"):
                last_content = str(msg.get("content", ""))
                break

        # If tool results are in the conversation (turn 2+), advance the sequence
        tool_result_count = sum(
            1 for m in messages if m.get("role") == "tool"
        )

        if tool_result_count == 0:
            # Turn 1: call first tool
            return self._TOOL_TURN_1
        elif tool_result_count == 1:
            # Turn 2: call second tool
            return self._TOOL_TURN_2
        else:
            # Turn 3+: return final decision based on pilot sector keyword
            system_lower = system_prompt.lower()
            if "industrial" in system_lower or "rame" in system_lower or "plc" in system_lower:
                return self._DECISION_INDUSTRY4
            elif "maritime" in system_lower or "vessel" in system_lower or "rotterdam" in system_lower:
                return self._DECISION_MARITIME
            elif "financial" in system_lower or "fraud" in system_lower or "caixabank" in system_lower:
                return self._DECISION_FINANCE
            else:
                return self._DECISION_TELECOM

    def extract_fields(self, raw_text: str, fields: list[str]) -> dict:
        """Return stub field extractions based on requested fields."""
        result: dict = {}
        raw_lower = raw_text.lower()

        field_defaults = {
            "event_id": "evt-stub-0001",
            "type": "AUTH_BRUTE_FORCE",
            "pilot": "TELECOM",
            "severity": "HIGH",
            "src_ip": "10.0.0.1",
            "target": "stub-target",
            "count": 100,
            "nodes_affected": 1,
            "timestamp": "2026-01-01T00:00:00Z",
            # TELECOM
            "subscriber_id": None,
            "cell_id": None,
            "imsi": None,
            # INDUSTRY_4
            "plc_id": None,
            "line_id": None,
            "scada_zone": None,
            "ot_protocol": None,
            "ot_safety_flag": False,
            # MARITIME
            "vessel_id": None,
            "port_zone": None,
            "ais_mmsi": None,
            "cargo_system_id": None,
            # FINANCE
            "account_id": None,
            "transaction_id": None,
            "branch_id": None,
            "fraud_score": None,
        }

        # Heuristic overrides based on raw text content
        if "plc" in raw_lower or "scada" in raw_lower or "opc" in raw_lower:
            field_defaults["type"] = "OT_ANOMALY"
            field_defaults["pilot"] = "INDUSTRY_4"
        elif "vessel" in raw_lower or "ais" in raw_lower or "port" in raw_lower or "cargo" in raw_lower:
            field_defaults["type"] = "AIS_ANOMALY"
            field_defaults["pilot"] = "MARITIME"
        elif "account" in raw_lower or "transaction" in raw_lower or "fraud" in raw_lower:
            field_defaults["type"] = "FRAUD_ATTEMPT"
            field_defaults["pilot"] = "FINANCE"

        if "critical" in raw_lower:
            field_defaults["severity"] = "CRITICAL"
        elif "high" in raw_lower:
            field_defaults["severity"] = "HIGH"

        for field in fields:
            result[field] = field_defaults.get(field)

        return result
