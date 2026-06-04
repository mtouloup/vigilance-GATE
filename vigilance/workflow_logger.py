"""Workflow audit CSV logger — appends one row per completed pipeline execution.

Each row captures the full lifecycle of a security event through T5.3:
  raw event → C1 normalization (+ LLM if used) → ActionRequest from T5.4
  → C5 guardrail (+ LLM if ESCALATE) → C3 NL→Rego (+ LLM if policy_update)
  → C4 dispatch → ExecutionResult

File path is controlled by the WORKFLOW_CSV_PATH env var (default: workflow_audit.csv).
Thread-safe: multiple pipeline threads write to the same file without corruption.
"""
from __future__ import annotations

import csv
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_COLUMNS = [
    "timestamp",
    # C1 — ingestion
    "event_id",
    "pilot",
    "severity",
    "raw_event",
    "parser_used",
    "c1_llm_invoked",
    "c1_llm_fields",
    "canonical_event",
    # T5.4 → T5.3
    "request_id",
    "actions_requested",
    "agent_confidence",
    # C5 — guardrail
    "guardrail_verdict",
    "guardrail_reasons",
    "c5_llm_invoked",
    "c5_llm_response",
    # C3 — policy translation
    "policy_update_nl",
    "c3_llm_invoked",
    "c3_rego_rule",
    # C4 — dispatch result
    "actions_dispatched",
    "overall_success",
    "audit_id",
]


def _j(obj: Any) -> str:
    """Compact JSON serialisation for a cell value."""
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    try:
        return json.dumps(obj, default=str, ensure_ascii=False)
    except Exception:
        return str(obj)


class WorkflowCSVLogger:
    """Appends one row per completed T5.3 pipeline execution to a CSV file."""

    def __init__(self, path: str | None = None) -> None:
        self._path = Path(path or os.environ.get("WORKFLOW_CSV_PATH", "workflow_audit.csv"))
        self._lock = threading.Lock()
        self._ensure_header()

    def _ensure_header(self) -> None:
        if not self._path.exists() or self._path.stat().st_size == 0:
            with self._path.open("w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(_COLUMNS)

    def append(
        self,
        *,
        # C1
        event_id: str,
        pilot: str,
        severity: str,
        raw_event: Any,
        parser_used: str,
        c1_llm_invoked: bool,
        c1_llm_fields: dict | None,
        canonical_event: dict,
        # T5.4 → T5.3
        request_id: str,
        actions_requested: list[str],
        agent_confidence: float,
        # C5
        guardrail_verdict: str,
        guardrail_reasons: list[str],
        c5_llm_invoked: bool,
        c5_llm_response: str | None,
        # C3
        policy_update_nl: str | None,
        c3_llm_invoked: bool,
        c3_rego_rule: str | None,
        # C4
        actions_dispatched: list[str],
        overall_success: bool,
        audit_id: str,
    ) -> None:
        row = {
            "timestamp":        datetime.now(timezone.utc).isoformat(),
            "event_id":         event_id,
            "pilot":            pilot,
            "severity":         severity,
            "raw_event":        _j(raw_event),
            "parser_used":      parser_used,
            "c1_llm_invoked":   str(c1_llm_invoked),
            "c1_llm_fields":    _j(c1_llm_fields),
            "canonical_event":  _j(canonical_event),
            "request_id":       request_id,
            "actions_requested": "|".join(actions_requested),
            "agent_confidence": str(agent_confidence),
            "guardrail_verdict": guardrail_verdict,
            "guardrail_reasons": " | ".join(guardrail_reasons),
            "c5_llm_invoked":   str(c5_llm_invoked),
            "c5_llm_response":  c5_llm_response or "",
            "policy_update_nl": policy_update_nl or "",
            "c3_llm_invoked":   str(c3_llm_invoked),
            "c3_rego_rule":     c3_rego_rule or "",
            "actions_dispatched": "|".join(actions_dispatched),
            "overall_success":  str(overall_success),
            "audit_id":         audit_id,
        }
        with self._lock:
            with self._path.open("a", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=_COLUMNS).writerow(row)
