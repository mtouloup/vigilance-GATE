"""Tests for C5 — Safety, Audit & Simulation."""
from __future__ import annotations
import pytest
from datetime import datetime, timezone

from vigilance.components.c5_safety.guardrail import SafetyGate
from vigilance.components.c5_safety.audit import AuditLog
from vigilance.components.c5_safety.simulation import SimulationMode
from vigilance.components.c6_profiles.profile_manager import ProfileManager
from vigilance.llm.base import StubLLMProvider
from vigilance.models.action_request import ActionRequest
from vigilance.models.canonical_event import CanonicalEvent
from vigilance.models.execution_result import ExecutionResult, ActionResult
from vigilance.models.guardrail_check import GuardrailVerdict


def make_event(src_ip="91.108.4.12", ot_safety=False) -> CanonicalEvent:
    return CanonicalEvent(
        event_id="evt-guard-0001",
        type="AUTH_BRUTE_FORCE",
        pilot="TELECOM",
        severity="CRITICAL",
        src_ip=src_ip,
        target="nms-01",
        ot_safety_flag=ot_safety,
        timestamp=datetime.now(timezone.utc),
    )


def make_request(actions=None, confidence=0.96) -> ActionRequest:
    return ActionRequest(
        request_id="req-guard-0001",
        event_id="evt-guard-0001",
        pilot="OTE_GR",
        actions=actions or ["block_ip", "revoke_session", "notify_soc"],
        agent_confidence=confidence,
    )


class TestSafetyGate:
    def test_approved_normal_case(self):
        gate = SafetyGate()
        profile = ProfileManager(sector="TELECOM").load()
        event = make_event()
        request = make_request(confidence=0.96)
        check = gate.check(request, event, profile, StubLLMProvider())
        assert check.verdict == GuardrailVerdict.APPROVED

    def test_escalate_low_confidence(self):
        gate = SafetyGate()
        profile = ProfileManager(sector="TELECOM").load()
        event = make_event()
        request = make_request(confidence=0.50)
        check = gate.check(request, event, profile, StubLLMProvider())
        assert check.verdict == GuardrailVerdict.ESCALATE
        assert any("Confidence" in r for r in check.reasons)

    def test_escalate_protected_ip(self):
        gate = SafetyGate()
        profile = ProfileManager(sector="TELECOM").load()
        # 10.0.0.5 is in 10.0.0.0/8 (protected)
        event = make_event(src_ip="10.0.0.5")
        request = make_request(confidence=0.96)
        check = gate.check(request, event, profile, StubLLMProvider())
        assert check.verdict == GuardrailVerdict.ESCALATE
        assert any("protected" in r.lower() for r in check.reasons)

    def test_rejected_too_many_actions(self):
        gate = SafetyGate()
        profile = ProfileManager(sector="TELECOM").load()
        event = make_event()
        request = make_request(
            actions=["a1", "a2", "a3", "a4", "a5", "a6"],
            confidence=0.96,
        )
        check = gate.check(request, event, profile, StubLLMProvider())
        assert check.verdict == GuardrailVerdict.REJECTED

    def test_ot_safety_checked_for_industry4(self):
        gate = SafetyGate()
        profile = ProfileManager(sector="INDUSTRY_4").load()
        event = CanonicalEvent(
            event_id="evt-ot-0001",
            type="OT_ANOMALY",
            pilot="INDUSTRY_4",
            severity="CRITICAL",
            ot_safety_flag=True,
            timestamp=datetime.now(timezone.utc),
        )
        request = ActionRequest(
            request_id="req-ot-0001",
            event_id="evt-ot-0001",
            pilot="Siemens_RO",
            actions=["isolate_plc", "revoke_ot_session"],
            agent_confidence=0.91,
        )
        check = gate.check(request, event, profile, StubLLMProvider())
        assert check.ot_safety_checked is True


class TestAuditLog:
    def test_open_close_ote_record(self):
        log = AuditLog()
        audit_id = log.open_record("OTE_GR", "evt-001", "req-001")
        assert audit_id == "aud-OTE-0031"

        result = ExecutionResult(
            request_id="req-001",
            event_id="evt-001",
            pilot="OTE_GR",
            action_results=[
                ActionResult(
                    action="block_ip",
                    plugin="ote_siem",
                    success=True,
                    latency_ms=38,
                    response_code=200,
                )
            ],
            overall_success=True,
            timestamp=datetime.now(timezone.utc),
        )
        log.close_record(audit_id, result)
        record = log.get_by_id(audit_id)
        assert record.closed is True
        assert record.verdict == "SUCCESS"

    def test_open_close_siemens_record(self):
        log = AuditLog()
        audit_id = log.open_record("Siemens_RO", "evt-002", "req-002")
        assert audit_id == "aud-SIE-0074"

    def test_cannot_close_twice(self):
        log = AuditLog()
        audit_id = log.open_record("OTE_GR", "evt-003", "req-003")
        log.close_record(audit_id)
        with pytest.raises(RuntimeError):
            log.close_record(audit_id)

    def test_get_all_returns_records(self):
        log = AuditLog()
        log.open_record("OTE_GR", "evt-004", "req-004")
        log.open_record("OTE_GR", "evt-005", "req-005")
        records = log.get_all()
        assert len(records) == 2

    def test_sequential_counters(self):
        log = AuditLog()
        id1 = log.open_record("OTE_GR", "evt-010", "req-010")
        id2 = log.open_record("OTE_GR", "evt-011", "req-011")
        assert id1 == "aud-OTE-0031"
        assert id2 == "aud-OTE-0032"


class TestSimulationMode:
    def test_defaults(self):
        sim = SimulationMode()
        assert sim.dry_run is False
        assert sim.digital_twin is False
        assert sim.is_active() is False

    def test_dry_run_active(self):
        sim = SimulationMode(dry_run=True)
        assert sim.is_active() is True

    def test_digital_twin_active(self):
        sim = SimulationMode(digital_twin=True)
        assert sim.is_active() is True
