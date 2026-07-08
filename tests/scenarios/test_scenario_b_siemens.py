"""Scenario B — Siemens OT Anomaly end-to-end pipeline test (INTEGRATED flow)."""
from __future__ import annotations
import uuid
import pytest

from vigilance.pipeline import T53Pipeline


RAW_OT_JSON = {
    "plc": "PLC-07", "line": "Line-3", "protocol": "OPC-UA",
    "anomaly": "register_write_out_of_range", "severity": "CRITICAL",
}

T54_ACTIONS = ["isolate_plc", "revoke_ot_session", "notify_soc", "update_zt_policy"]


@pytest.fixture
def pipeline():
    return T53Pipeline(dry_run=True)


def _ingest_and_execute(pipeline, raw, actions=T54_ACTIONS, confidence=0.91, policy=None):
    event = pipeline.ingest_event(raw)
    result, _rego = pipeline.execute_action_request({
        "request_id":       str(uuid.uuid4()),
        "event_id":         event.event_id,
        "pilot":            event.pilot,
        "actions":          actions,
        "agent_confidence": confidence,
        "policy_update":    policy,
    })
    return result


def test_scenario_b_ingest_detects_industry4(pipeline):
    event = pipeline.ingest_event(RAW_OT_JSON)
    assert event.pilot == "INDUSTRY_4"
    assert event.severity == "CRITICAL"


def test_scenario_b_ot_safety_flag_set(pipeline):
    event = pipeline.ingest_event(RAW_OT_JSON)
    assert event.ot_safety_flag is True


def test_scenario_b_canonical_event_published(pipeline):
    pipeline.ingest_event(RAW_OT_JSON)
    messages = pipeline.broker.get_messages("t53.canonical_events")
    assert len(messages) == 1
    assert messages[0]["pilot"] == "INDUSTRY_4"


def test_scenario_b_execution_succeeds(pipeline):
    result = _ingest_and_execute(pipeline, RAW_OT_JSON)
    assert result.overall_success


def test_scenario_b_ot_actions_dispatched(pipeline):
    result = _ingest_and_execute(pipeline, RAW_OT_JSON)
    dispatched = [r.action for r in result.action_results]
    assert "isolate_plc" in dispatched
    assert "notify_soc" in dispatched


def test_scenario_b_audit_record_created(pipeline):
    _ingest_and_execute(pipeline, RAW_OT_JSON)
    records = pipeline.audit_log.get_all()
    assert len(records) == 1
    assert records[0].audit_id.startswith("aud-SIE-")


def test_scenario_b_guardrail_uses_industry4_profile(pipeline):
    event = pipeline.ingest_event(RAW_OT_JSON)
    from unittest.mock import patch
    from vigilance.models.guardrail_check import GuardrailCheck, GuardrailVerdict
    approved = GuardrailCheck(
        check_id="chk-test", request_id="req-test",
        verdict=GuardrailVerdict.APPROVED, reasons=[], ot_safety_checked=True,
    )
    with patch.object(pipeline._guardrail, "check", return_value=approved) as mock_check:
        pipeline.execute_action_request({
            "request_id": str(uuid.uuid4()), "event_id": event.event_id,
            "pilot": event.pilot, "actions": T54_ACTIONS, "agent_confidence": 0.91,
        })
        profile_arg = mock_check.call_args[0][2]
        assert profile_arg.sector == "INDUSTRY_4"
