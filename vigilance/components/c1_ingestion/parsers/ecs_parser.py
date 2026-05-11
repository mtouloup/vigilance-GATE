"""ECS (Elastic Common Schema) parser for C1 ingestion."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone

from vigilance.models.canonical_event import CanonicalEvent


class ECSParser:
    """Parse Elastic Common Schema dicts into CanonicalEvent objects."""

    def can_parse(self, raw: str | dict) -> bool:
        return isinstance(raw, dict) and "event.kind" in raw

    def parse(self, raw: dict) -> CanonicalEvent:
        """Parse an ECS dict and return a CanonicalEvent."""
        # Extract nested or flat fields
        event_kind = raw.get("event.kind", "event")
        event_category = raw.get("event.category", "")
        event_action = raw.get("event.action", "UNKNOWN")

        # Determine event type
        if "authentication" in str(event_category).lower():
            event_type = "AUTH_BRUTE_FORCE"
        elif "network" in str(event_category).lower():
            event_type = "NETWORK_ANOMALY"
        else:
            event_type = event_action.upper().replace("-", "_").replace(" ", "_")

        # Determine severity
        severity_raw = raw.get("event.severity", raw.get("log.level", "medium"))
        severity = self._map_severity(str(severity_raw))

        # Determine pilot
        pilot = raw.get("agent.type", raw.get("observer.type", "TELECOM")).upper()
        if pilot not in ("TELECOM", "INDUSTRY_4"):
            pilot = "TELECOM"

        src_ip = (
            raw.get("source.ip")
            or raw.get("client.ip")
            or raw.get("network.source.ip")
        )
        target = (
            raw.get("destination.address")
            or raw.get("server.address")
            or raw.get("host.hostname")
        )

        return CanonicalEvent(
            event_id=raw.get("event.id", str(uuid.uuid4())),
            type=event_type,
            pilot=pilot,
            severity=severity,
            src_ip=src_ip,
            target=target,
            raw_payload=raw,
            timestamp=datetime.now(timezone.utc),
        )

    def _map_severity(self, s: str) -> str:
        s_lower = s.lower()
        if s_lower in ("critical",):
            return "CRITICAL"
        elif s_lower in ("high", "error"):
            return "HIGH"
        elif s_lower in ("medium", "warning", "warn"):
            return "MEDIUM"
        else:
            return "LOW"
