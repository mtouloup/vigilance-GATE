"""OT JSON parser for Siemens Industry 4.0 events."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone

from vigilance.models.canonical_event import CanonicalEvent


class OTJsonParser:
    """Parse Siemens OT JSON dicts into CanonicalEvent objects.

    Recognizes dicts with keys: plc, line, protocol, anomaly, severity
    """

    def can_parse(self, raw: str | dict) -> bool:
        return isinstance(raw, dict) and ("plc" in raw or "protocol" in raw)

    def parse(self, raw: dict) -> CanonicalEvent:
        """Parse an OT JSON dict and return a CanonicalEvent."""
        plc_id = raw.get("plc")
        line_id = raw.get("line")
        protocol = raw.get("protocol")  # OPC-UA | Modbus
        anomaly = raw.get("anomaly", "UNKNOWN_ANOMALY")
        severity_raw = raw.get("severity", "HIGH")
        severity = severity_raw.upper() if isinstance(severity_raw, str) else "HIGH"

        # Normalise severity to known values
        if severity not in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
            severity = "HIGH"

        # Derive event type from anomaly description
        anomaly_lower = str(anomaly).lower()
        if "register_write" in anomaly_lower or "write_out_of_range" in anomaly_lower:
            event_type = "OT_ANOMALY"
        elif "lateral" in anomaly_lower:
            event_type = "OT_LATERAL_MOVE"
        elif "anomaly" in anomaly_lower:
            event_type = "OT_ANOMALY"
        else:
            event_type = "OT_ANOMALY"

        return CanonicalEvent(
            event_id=str(uuid.uuid4()),
            type=event_type,
            pilot="INDUSTRY_4",
            severity=severity,
            plc_id=plc_id,
            line_id=line_id,
            ot_protocol=protocol,
            ot_safety_flag=True,
            raw_payload=raw,
            timestamp=datetime.now(timezone.utc),
        )
