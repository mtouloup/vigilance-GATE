"""C5 Immutable Audit Log."""
from __future__ import annotations
from datetime import datetime, timezone

from vigilance.models.audit_record import AuditRecord
from vigilance.models.execution_result import ExecutionResult
from vigilance.models.guardrail_check import GuardrailCheck, GuardrailVerdict


# Starting counters per pilot (as per spec examples)
_PILOT_COUNTERS: dict[str, int] = {}
_PILOT_PREFIXES: dict[str, str] = {
    "OTE_GR": "OTE",
    "TELECOM": "OTE",
    "Siemens_RO": "SIE",
    "INDUSTRY_4": "SIE",
}
_PILOT_STARTS: dict[str, int] = {
    "OTE": 31,
    "SIE": 74,
}


class AuditLog:
    """Append-only in-memory audit log.

    Records are immutable once closed. Audit IDs follow the pattern:
    aud-{PREFIX}-{COUNTER:04d}
    - OTE pilot: starts at 0031 (aud-OTE-0031)
    - SIE pilot: starts at 0074 (aud-SIE-0074)
    """

    def __init__(self) -> None:
        self._records: list[AuditRecord] = []
        self._index: dict[str, int] = {}  # audit_id -> list index
        self._counters: dict[str, int] = {}

    def open_record(
        self,
        pilot_id: str,
        event_id: str,
        request_id: str,
    ) -> str:
        """Open a new audit record and return its audit_id.

        Args:
            pilot_id: Pilot identifier (e.g. OTE_GR, Siemens_RO).
            event_id: The event being processed.
            request_id: The ActionRequest identifier.

        Returns:
            audit_id string like "aud-OTE-0031".
        """
        prefix = _PILOT_PREFIXES.get(pilot_id, "GEN")
        if prefix not in self._counters:
            self._counters[prefix] = _PILOT_STARTS.get(prefix, 1)
        else:
            self._counters[prefix] += 1

        counter = self._counters[prefix]
        audit_id = f"aud-{prefix}-{counter:04d}"

        record = AuditRecord(
            audit_id=audit_id,
            pilot_id=pilot_id,
            event_id=event_id,
            request_id=request_id,
            timestamp_opened=datetime.now(timezone.utc),
            verdict="PENDING",
            closed=False,
        )
        self._index[audit_id] = len(self._records)
        self._records.append(record)
        return audit_id

    def close_record(
        self,
        audit_id: str,
        execution_result: ExecutionResult | None = None,
        guardrail_check: GuardrailCheck | None = None,
    ) -> None:
        """Close an audit record with execution results.

        Args:
            audit_id: The audit record identifier.
            execution_result: Optional ExecutionResult with action results.
            guardrail_check: Optional GuardrailCheck with verdict.

        Raises:
            KeyError: If audit_id does not exist.
            RuntimeError: If record is already closed.
        """
        idx = self._index.get(audit_id)
        if idx is None:
            raise KeyError(f"Audit record not found: {audit_id}")

        record = self._records[idx]
        if record.closed:
            raise RuntimeError(f"Audit record {audit_id} is already closed")

        # Determine verdict
        verdict = "UNKNOWN"
        if guardrail_check is not None:
            verdict = guardrail_check.verdict.value
        elif execution_result is not None:
            verdict = "SUCCESS" if execution_result.overall_success else "FAILURE"

        # Extract action results and latencies
        action_results: list[dict] = []
        latencies_ms: list[int] = []
        if execution_result is not None:
            for ar in execution_result.action_results:
                action_results.append(ar.model_dump())
                latencies_ms.append(ar.latency_ms)

        # Replace the record (simulate immutability by replacing in list)
        updated = AuditRecord(
            audit_id=record.audit_id,
            pilot_id=record.pilot_id,
            event_id=record.event_id,
            request_id=record.request_id,
            timestamp_opened=record.timestamp_opened,
            timestamp_closed=datetime.now(timezone.utc),
            verdict=verdict,
            action_results=action_results,
            latencies_ms=latencies_ms,
            closed=True,
        )
        self._records[idx] = updated

    def get_all(self) -> list[AuditRecord]:
        """Return a copy of all audit records."""
        return list(self._records)

    def get_by_id(self, audit_id: str) -> AuditRecord | None:
        """Return a specific audit record by ID."""
        idx = self._index.get(audit_id)
        if idx is None:
            return None
        return self._records[idx]
