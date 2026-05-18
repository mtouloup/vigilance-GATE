"""C1 Event Ingestion & Normalization — orchestrates parsers with LLM fallback."""
from __future__ import annotations

from vigilance.components.c1_ingestion.parsers.cef_parser import CEFParser
from vigilance.components.c1_ingestion.parsers.ecs_parser import ECSParser
from vigilance.components.c1_ingestion.parsers.syslog_parser import SyslogParser
from vigilance.components.c1_ingestion.parsers.ot_json_parser import OTJsonParser
from vigilance.components.c1_ingestion.parsers.llm_parser import LLMParser
from vigilance.llm.base import LLMProvider
from vigilance.models.canonical_event import CanonicalEvent


class Normalizer:
    """Orchestrate parsers in priority order and fall back to LLM parser.

    Parser priority:
    1. CEF  — if raw is a string starting with "CEF:"
    2. ECS  — if raw is a dict with "event.kind"
    3. OT JSON — if raw is a dict with "plc" or "protocol"
    4. Syslog — if raw is a string matching syslog pattern
    5. LLM fallback — for anything else
    """

    def __init__(self, llm: LLMProvider) -> None:
        self._cef = CEFParser()
        self._ecs = ECSParser()
        self._syslog = SyslogParser()
        self._ot_json = OTJsonParser()
        self._llm_parser = LLMParser(llm)

    def normalize(self, raw: str | dict, sector_profile=None) -> CanonicalEvent:
        """Normalize raw event into a CanonicalEvent.

        Args:
            raw: Raw event as string or dict.
            sector_profile: Optional SectorProfile for sector-specific enrichment
                (e.g. OT safety flag). Pilot is determined from the event content
                by the parsers — this profile does NOT override the detected pilot.

        Returns:
            CanonicalEvent with normalized fields.
        """
        event = self._try_parse(raw)

        if sector_profile is not None:
            event = self._enrich_with_profile(event, sector_profile)

        return event

    def _try_parse(self, raw: str | dict) -> CanonicalEvent:
        # 1. CEF
        if self._cef.can_parse(raw):
            return self._cef.parse(raw)  # type: ignore[arg-type]
        # 2. ECS
        if self._ecs.can_parse(raw):
            return self._ecs.parse(raw)  # type: ignore[arg-type]
        # 3. OT JSON
        if self._ot_json.can_parse(raw):
            return self._ot_json.parse(raw)  # type: ignore[arg-type]
        # 4. Syslog
        if self._syslog.can_parse(raw):
            return self._syslog.parse(raw)  # type: ignore[arg-type]
        # 5. LLM fallback
        return self._llm_parser.parse(raw)

    def _enrich_with_profile(self, event: CanonicalEvent, profile) -> CanonicalEvent:
        """Apply sector-specific field enrichments from the profile.

        Does NOT override the pilot — that is determined by the parsers from
        event content. Only applies additive enrichments (e.g. OT safety flag).
        """
        if profile.sector == "INDUSTRY_4" and event.pilot == "INDUSTRY_4":
            if profile.ot_safety_flag and not event.ot_safety_flag:
                data = event.model_dump()
                data["ot_safety_flag"] = True
                return CanonicalEvent(**data)
        return event
