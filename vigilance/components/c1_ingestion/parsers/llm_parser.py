"""LLM fallback parser for C1 ingestion."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone

from vigilance.llm.base import LLMProvider
from vigilance.models.canonical_event import CanonicalEvent


_VALID_PILOTS = {"TELECOM", "MARITIME", "FINANCE", "INDUSTRY_4"}

_CANONICAL_FIELDS = [
    "type", "pilot", "severity",
    "src_ip", "target", "count", "nodes_affected",
    "subscriber_id", "cell_id", "imsi",
    "plc_id", "line_id", "scada_zone", "ot_protocol", "ot_safety_flag",
    "vessel_id", "port_zone", "ais_mmsi", "cargo_system_id",
    "account_id", "transaction_id", "branch_id", "fraud_score",
    "timestamp",
]


class LLMParser:
    """Use an LLMProvider to extract fields from arbitrary raw events."""

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    def can_parse(self, raw: str | dict) -> bool:
        # LLM parser is the fallback — always claims it can parse
        return True

    @staticmethod
    def _to_int(val) -> int | None:
        """Coerce LLM output to int, discarding non-numeric values."""
        if val is None:
            return None
        if isinstance(val, int):
            return val
        try:
            return int(val)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_float(val) -> float | None:
        """Coerce LLM output to float, discarding non-numeric values."""
        if val is None:
            return None
        if isinstance(val, float):
            return val
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_str(val) -> str | None:
        """Coerce LLM output to str; joins lists, discards other non-string types."""
        if val is None:
            return None
        if isinstance(val, str):
            return val or None
        if isinstance(val, list):
            return ", ".join(str(v) for v in val) if val else None
        return str(val) or None

    def parse(self, raw: str | dict) -> CanonicalEvent:
        """Use LLM field extraction to build a CanonicalEvent."""
        raw_text = str(raw) if not isinstance(raw, str) else raw
        fields = self._llm.extract_fields(raw_text, _CANONICAL_FIELDS)

        # event_id is always a T5.3-generated UUID — never extracted from content
        event_id = str(uuid.uuid4())
        event_type = self._to_str(fields.get("type")) or "UNKNOWN_EVENT"
        pilot_raw = (self._to_str(fields.get("pilot")) or "").strip().upper()
        pilot = pilot_raw if pilot_raw in _VALID_PILOTS else "UNKNOWN"
        severity = self._to_str(fields.get("severity")) or "MEDIUM"

        # Parse timestamp
        ts_val = fields.get("timestamp")
        if isinstance(ts_val, datetime):
            timestamp = ts_val
        else:
            try:
                ts_str = str(ts_val) if ts_val else ""
                timestamp = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                timestamp = datetime.now(timezone.utc)

        return CanonicalEvent(
            event_id=event_id,
            type=event_type,
            pilot=pilot,
            severity=severity,
            src_ip=self._to_str(fields.get("src_ip")),
            target=self._to_str(fields.get("target")),
            count=self._to_int(fields.get("count")),
            nodes_affected=self._to_int(fields.get("nodes_affected")),
            # TELECOM
            subscriber_id=self._to_str(fields.get("subscriber_id")),
            cell_id=self._to_str(fields.get("cell_id")),
            imsi=self._to_str(fields.get("imsi")),
            # INDUSTRY_4
            plc_id=self._to_str(fields.get("plc_id")),
            line_id=self._to_str(fields.get("line_id")),
            scada_zone=self._to_str(fields.get("scada_zone")),
            ot_protocol=self._to_str(fields.get("ot_protocol")),
            ot_safety_flag=bool(fields.get("ot_safety_flag", False)),
            # MARITIME
            vessel_id=self._to_str(fields.get("vessel_id")),
            port_zone=self._to_str(fields.get("port_zone")),
            ais_mmsi=self._to_str(fields.get("ais_mmsi")),
            cargo_system_id=self._to_str(fields.get("cargo_system_id")),
            # FINANCE
            account_id=self._to_str(fields.get("account_id")),
            transaction_id=self._to_str(fields.get("transaction_id")),
            branch_id=self._to_str(fields.get("branch_id")),
            fraud_score=self._to_float(fields.get("fraud_score")),
            raw_payload={"llm_parsed": True, "raw": raw_text[:500]},
            timestamp=timestamp,
        )
