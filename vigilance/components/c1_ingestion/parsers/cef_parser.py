"""CEF (Common Event Format) parser for C1 ingestion."""
from __future__ import annotations
import re
import uuid
from datetime import datetime, timezone

from vigilance.models.canonical_event import CanonicalEvent


class CEFParser:
    """Parse CEF format strings into CanonicalEvent objects.

    CEF format:
      CEF:version|device_vendor|device_product|device_version|signature_id|name|severity|extensions
    """

    # Map CEF severity (0-10) to our severity labels
    _SEVERITY_MAP = {
        range(0, 4): "LOW",
        range(4, 7): "MEDIUM",
        range(7, 9): "HIGH",
        range(9, 11): "CRITICAL",
    }

    def can_parse(self, raw: str | dict) -> bool:
        return isinstance(raw, str) and raw.strip().startswith("CEF:")

    def parse(self, raw: str) -> CanonicalEvent:
        """Parse a CEF string and return a CanonicalEvent."""
        raw = raw.strip()
        # Split header (first 7 pipes) from extensions
        parts = raw.split("|", 7)
        if len(parts) < 7:
            raise ValueError(f"Invalid CEF format — expected 8 pipe-delimited fields, got {len(parts)}")

        # parts[0] = "CEF:0", parts[5] = name/type, parts[6] = severity
        event_name = parts[5].strip()
        cef_severity_str = parts[6].strip()
        try:
            cef_severity_int = int(cef_severity_str)
        except ValueError:
            cef_severity_int = 5

        severity = self._map_severity(cef_severity_int)

        # Determine pilot from device product
        device_product = parts[2].strip().upper()
        if any(kw in device_product for kw in ("OTE", "TELECOM", "SOC")):
            pilot = "TELECOM"
        else:
            pilot = "TELECOM"  # Default to TELECOM for CEF events

        # Parse extensions
        ext_str = parts[7] if len(parts) > 7 else ""
        extensions = self._parse_extensions(ext_str)

        src_ip = extensions.get("src")
        target = extensions.get("dst")
        count_str = extensions.get("cnt")
        count = int(count_str) if count_str else None
        nodes_str = extensions.get("nodes")
        nodes_affected = int(nodes_str) if nodes_str else None

        return CanonicalEvent(
            event_id=str(uuid.uuid4()),
            type=event_name,
            pilot=pilot,
            severity=severity,
            src_ip=src_ip,
            target=target,
            count=count,
            nodes_affected=nodes_affected,
            raw_payload={"cef_raw": raw, "extensions": extensions},
            timestamp=datetime.now(timezone.utc),
        )

    def _parse_extensions(self, ext_str: str) -> dict:
        """Parse CEF extension key=value pairs."""
        result: dict = {}
        # Match key=value, value may contain spaces until next key=
        pattern = re.compile(r'(\w+)=([^\s=]+(?:\s+(?!\w+=)[^\s=]+)*)')
        for match in pattern.finditer(ext_str):
            result[match.group(1)] = match.group(2).strip()
        return result

    def _map_severity(self, n: int) -> str:
        if n <= 3:
            return "LOW"
        elif n <= 6:
            return "MEDIUM"
        elif n <= 8:
            return "HIGH"
        else:
            return "CRITICAL"
