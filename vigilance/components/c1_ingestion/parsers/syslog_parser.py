"""Syslog parser for C1 ingestion."""
from __future__ import annotations
import re
import uuid
from datetime import datetime, timezone

from vigilance.models.canonical_event import CanonicalEvent


class SyslogParser:
    """Parse syslog format strings into CanonicalEvent objects.

    Supports RFC 3164 and RFC 5424 formats.
    """

    # RFC 3164: <priority>timestamp hostname process[pid]: message
    _RFC3164 = re.compile(
        r'^<(?P<priority>\d+)>(?P<timestamp>\w{3}\s+\d+\s+\d+:\d+:\d+)\s+'
        r'(?P<hostname>\S+)\s+(?P<process>\S+):\s*(?P<message>.+)$'
    )
    # RFC 5424: <priority>version timestamp hostname appname procid msgid structured-data msg
    _RFC5424 = re.compile(
        r'^<(?P<priority>\d+)>(?P<version>\d+)\s+(?P<timestamp>\S+)\s+'
        r'(?P<hostname>\S+)\s+(?P<appname>\S+)\s+(?P<procid>\S+)\s+(?P<msgid>\S+)'
        r'(?:\s+(?P<structured_data>\[.*?\]|-))?\s*(?P<message>.*)$'
    )

    def can_parse(self, raw: str | dict) -> bool:
        if not isinstance(raw, str):
            return False
        return bool(self._RFC3164.match(raw)) or bool(self._RFC5424.match(raw))

    def parse(self, raw: str) -> CanonicalEvent:
        """Parse a syslog string and return a CanonicalEvent."""
        m = self._RFC5424.match(raw) or self._RFC3164.match(raw)
        if not m:
            raise ValueError(f"Not a valid syslog string: {raw[:80]}")

        data = m.groupdict()
        message = data.get("message", "")
        hostname = data.get("hostname", "unknown")

        # Heuristic event type detection
        msg_lower = message.lower()
        if "auth" in msg_lower or "login" in msg_lower or "password" in msg_lower:
            event_type = "AUTH_BRUTE_FORCE"
        elif "fail" in msg_lower:
            event_type = "AUTH_FAILURE"
        else:
            event_type = "SYSLOG_EVENT"

        # Priority parsing for severity
        priority = int(data.get("priority", 13))
        facility = priority >> 3
        level = priority & 0x7
        severity = self._syslog_level_to_severity(level)

        return CanonicalEvent(
            event_id=str(uuid.uuid4()),
            type=event_type,
            pilot="TELECOM",
            severity=severity,
            target=hostname,
            raw_payload={"syslog_raw": raw, "parsed": data},
            timestamp=datetime.now(timezone.utc),
        )

    def _syslog_level_to_severity(self, level: int) -> str:
        # syslog levels: 0=emerg, 1=alert, 2=crit, 3=err, 4=warn, 5=notice, 6=info, 7=debug
        if level <= 1:
            return "CRITICAL"
        elif level <= 3:
            return "HIGH"
        elif level <= 4:
            return "MEDIUM"
        else:
            return "LOW"
