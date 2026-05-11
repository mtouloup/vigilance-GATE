"""Tests for C2 — Agentic Interaction Layer."""
from __future__ import annotations
import pytest
from datetime import datetime, timezone

from vigilance.components.c2_agentic.agent import AgentLoop
from vigilance.components.c2_agentic.tools import (
    query_siem_logs,
    query_iam_sessions,
    query_threat_intel,
    dispatch_tool,
)
from vigilance.components.c6_profiles.profile_manager import ProfileManager
from vigilance.llm.base import StubLLMProvider
from vigilance.models.agent_decision import AgentDecision
from vigilance.models.canonical_event import CanonicalEvent


def make_telecom_event() -> CanonicalEvent:
    return CanonicalEvent(
        event_id="evt-test-0001",
        type="AUTH_BRUTE_FORCE",
        pilot="TELECOM",
        severity="CRITICAL",
        src_ip="91.108.4.12",
        target="nms-01",
        count=230,
        timestamp=datetime.now(timezone.utc),
    )


def make_industry4_event() -> CanonicalEvent:
    return CanonicalEvent(
        event_id="evt-test-0002",
        type="OT_ANOMALY",
        pilot="INDUSTRY_4",
        severity="CRITICAL",
        plc_id="PLC-07",
        ot_safety_flag=True,
        timestamp=datetime.now(timezone.utc),
    )


class TestAgentLoop:
    def test_telecom_decision(self):
        loop = AgentLoop()
        profile = ProfileManager(sector="TELECOM").load()
        event = make_telecom_event()
        decision = loop.run(event, profile, StubLLMProvider())

        assert isinstance(decision, AgentDecision)
        assert decision.event_id == event.event_id
        assert decision.threat_type == "CREDENTIAL_STUFFING"
        assert "block_ip" in decision.recommended_actions
        assert "revoke_session" in decision.recommended_actions
        assert "notify_soc" in decision.recommended_actions
        assert decision.confidence == pytest.approx(0.96)
        assert decision.reasoning_turns >= 3

    def test_industry4_decision(self):
        loop = AgentLoop()
        profile = ProfileManager(sector="INDUSTRY_4").load()
        event = make_industry4_event()
        decision = loop.run(event, profile, StubLLMProvider())

        assert isinstance(decision, AgentDecision)
        assert decision.threat_type == "OT_LATERAL_MOVE"
        assert "isolate_plc" in decision.recommended_actions
        assert "revoke_ot_session" in decision.recommended_actions
        assert decision.confidence == pytest.approx(0.91)

    def test_decision_has_correct_pilot(self):
        loop = AgentLoop()
        profile = ProfileManager(sector="TELECOM").load()
        event = make_telecom_event()
        decision = loop.run(event, profile, StubLLMProvider())
        assert decision.pilot == "TELECOM"

    def test_reasoning_uses_tools(self):
        loop = AgentLoop()
        profile = ProfileManager(sector="TELECOM").load()
        event = make_telecom_event()
        decision = loop.run(event, profile, StubLLMProvider())
        # Stub LLM does 2 tool calls then final decision = 3 turns
        assert decision.reasoning_turns == 3


class TestTools:
    def test_query_siem_logs(self):
        result = query_siem_logs("nms-01", window_min=60)
        assert result["target"] == "nms-01"
        assert result["failed_auth_count"] > 0
        assert "unique_src_ips" in result

    def test_query_iam_sessions(self):
        result = query_iam_sessions("nms-01")
        assert result["active_sessions"] > 0
        assert len(result["sessions"]) > 0

    def test_query_threat_intel(self):
        result = query_threat_intel("91.108.4.12")
        assert result["reputation"] == "malicious"

    def test_dispatch_tool_unknown(self):
        import json
        result = json.loads(dispatch_tool("unknown_tool", {}))
        assert "error" in result
