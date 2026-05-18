"""Tests for C1 — Event Ingestion & Normalization."""
from __future__ import annotations
import pytest
from datetime import datetime, timezone

from vigilance.components.c1_ingestion.normalizer import Normalizer
from vigilance.components.c1_ingestion.parsers.cef_parser import CEFParser
from vigilance.components.c1_ingestion.parsers.ecs_parser import ECSParser
from vigilance.components.c1_ingestion.parsers.ot_json_parser import OTJsonParser
from vigilance.components.c1_ingestion.parsers.syslog_parser import SyslogParser
from vigilance.llm.base import StubLLMProvider
from vigilance.models.canonical_event import CanonicalEvent


CEF_SAMPLE = (
    "CEF:0|OTE-IDS|SOCv3|2.0|200|AUTH_BRUTE_FORCE|9|"
    "src=91.108.4.12 dst=nms-01 cnt=230 nodes=3 app=SSH"
)

ECS_SAMPLE = {
    "event.kind": "alert",
    "event.category": "authentication",
    "event.action": "brute-force",
    "event.severity": "high",
    "source.ip": "10.0.0.5",
    "host.hostname": "login-server-01",
}

OT_JSON_SAMPLE = {
    "plc": "PLC-07",
    "line": "Line-3",
    "protocol": "OPC-UA",
    "anomaly": "register_write_out_of_range",
    "severity": "CRITICAL",
}

SYSLOG_SAMPLE = (
    "<134>Jan  1 00:01:00 firewall01 sshd: "
    "Failed password for admin from 91.108.4.12 port 22 ssh2"
)


class TestCEFParser:
    def test_can_parse_cef_string(self):
        parser = CEFParser()
        assert parser.can_parse(CEF_SAMPLE)
        assert not parser.can_parse({"not": "cef"})

    def test_parse_cef_event(self):
        parser = CEFParser()
        event = parser.parse(CEF_SAMPLE)
        assert isinstance(event, CanonicalEvent)
        assert event.type == "AUTH_BRUTE_FORCE"
        assert event.severity == "CRITICAL"
        assert event.src_ip == "91.108.4.12"
        assert event.target == "nms-01"
        assert event.count == 230
        assert event.nodes_affected == 3

    def test_parse_cef_low_severity(self):
        low_cef = "CEF:0|Vendor|Product|1.0|100|TEST_EVENT|2|src=1.2.3.4"
        event = CEFParser().parse(low_cef)
        assert event.severity == "LOW"


class TestECSParser:
    def test_can_parse_ecs_dict(self):
        parser = ECSParser()
        assert parser.can_parse(ECS_SAMPLE)
        assert not parser.can_parse("not a dict")

    def test_parse_ecs_event(self):
        parser = ECSParser()
        event = parser.parse(ECS_SAMPLE)
        assert isinstance(event, CanonicalEvent)
        assert event.severity == "HIGH"
        assert event.src_ip == "10.0.0.5"
        assert event.target == "login-server-01"


class TestOTJsonParser:
    def test_can_parse_ot_json(self):
        parser = OTJsonParser()
        assert parser.can_parse(OT_JSON_SAMPLE)
        assert not parser.can_parse("not a plc dict")

    def test_parse_ot_json_event(self):
        parser = OTJsonParser()
        event = parser.parse(OT_JSON_SAMPLE)
        assert isinstance(event, CanonicalEvent)
        assert event.pilot == "INDUSTRY_4"
        assert event.severity == "CRITICAL"
        assert event.plc_id == "PLC-07"
        assert event.line_id == "Line-3"
        assert event.ot_protocol == "OPC-UA"
        assert event.ot_safety_flag is True


class TestSyslogParser:
    def test_can_parse_syslog(self):
        parser = SyslogParser()
        assert parser.can_parse(SYSLOG_SAMPLE)
        assert not parser.can_parse({"not": "syslog"})

    def test_parse_syslog_event(self):
        parser = SyslogParser()
        event = parser.parse(SYSLOG_SAMPLE)
        assert isinstance(event, CanonicalEvent)
        assert event.target == "firewall01"


class TestNormalizer:
    def setup_method(self):
        self.normalizer = Normalizer(StubLLMProvider())

    def test_normalize_cef(self):
        event = self.normalizer.normalize(CEF_SAMPLE)
        assert event.type == "AUTH_BRUTE_FORCE"
        assert event.src_ip == "91.108.4.12"

    def test_normalize_ot_json(self):
        event = self.normalizer.normalize(OT_JSON_SAMPLE)
        assert event.pilot == "INDUSTRY_4"
        assert event.ot_safety_flag is True

    def test_normalize_ecs(self):
        event = self.normalizer.normalize(ECS_SAMPLE)
        assert event.severity == "HIGH"

    def test_normalize_llm_fallback(self):
        # A raw string that no structured parser can handle
        event = self.normalizer.normalize("some unknown event format xyz123")
        assert isinstance(event, CanonicalEvent)
        # LLM fallback should produce a valid event
        assert event.type is not None

    def test_normalize_ot_safety_enriched_from_profile(self):
        # OT JSON parser always sets pilot=INDUSTRY_4 from the payload structure.
        # When the INDUSTRY_4 profile has ot_safety_flag=True, the normalizer
        # should ensure ot_safety_flag is set on the event.
        from vigilance.components.c6_profiles.profile_manager import ProfileManager
        profile = ProfileManager(sector="INDUSTRY_4").load()
        event = self.normalizer.normalize(OT_JSON_SAMPLE, sector_profile=profile)
        assert event.pilot == "INDUSTRY_4"
        assert event.ot_safety_flag is True
