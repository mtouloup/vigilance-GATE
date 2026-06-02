"""Scenario A — OTE Credential Stuffing end-to-end pipeline test (INTEGRATED flow)."""
from __future__ import annotations
import uuid
import pytest

from vigilance.pipeline import T53Pipeline


RAW_CEF = (
    "CEF:0|OTE-IDS|SOCv3|2.0|200|AUTH_BRUTE_FORCE|9|"
    "src=91.108.4.12 dst=nms-01 cnt=230 nodes=3 app=SSH"
)

# Simulates what T5.4 would dispatch after consuming the CanonicalEvent
T54_ACTIONS = ["block_ip", "revoke_session", "notify_soc"]


@pytest.fixture
def pipeline():
    return T53Pipeline(dry_run=True)


def _ingest_and_execute(pipeline, raw, actions=T54_ACTIONS, confidence=0.96):
    """Helper: C1 ingest → simulate T5.4 → C5+C3+C4 execute."""
    event = pipeline.ingest_event(raw)
    return pipeline.execute_action_request({
        "request_id":       str(uuid.uuid4()),
        "event_id":         event.event_id,
        "pilot":            event.pilot,
        "actions":          actions,
        "agent_confidence": confidence,
    })


def test_scenario_a_ingest_produces_canonical_event(pipeline):
    event = pipeline.ingest_event(RAW_CEF)
    assert event.event_id
    assert event.pilot == "TELECOM"
    assert event.severity in ("HIGH", "CRITICAL")


def test_scenario_a_canonical_event_published(pipeline):
    pipeline.ingest_event(RAW_CEF)
    messages = pipeline.broker.get_messages("t53.canonical_events")
    assert len(messages) == 1
    assert messages[0]["pilot"] == "TELECOM"


def test_scenario_a_execution_succeeds(pipeline):
    result = _ingest_and_execute(pipeline, RAW_CEF)
    assert result.overall_success


def test_scenario_a_expected_actions_dispatched(pipeline):
    result = _ingest_and_execute(pipeline, RAW_CEF)
    dispatched = [r.action for r in result.action_results]
    assert "block_ip" in dispatched
    assert "revoke_session" in dispatched
    assert "notify_soc" in dispatched


def test_scenario_a_audit_record_created(pipeline):
    result = _ingest_and_execute(pipeline, RAW_CEF)
    records = pipeline.audit_log.get_all()
    assert len(records) == 1
    record = records[0]
    assert record.closed is True
    assert record.audit_id.startswith("aud-OTE-")


def test_scenario_a_result_published_to_broker(pipeline):
    _ingest_and_execute(pipeline, RAW_CEF)
    messages = pipeline.broker.get_messages("t53.results")
    assert len(messages) == 1
    assert messages[0]["overall_success"] is True


def test_scenario_a_guardrail_rejects_too_many_actions(pipeline):
    """Guardrail always rejects when action count exceeds 5 (proportionality check)."""
    event = pipeline.ingest_event(RAW_CEF)
    result = pipeline.execute_action_request({
        "request_id":       str(uuid.uuid4()),
        "event_id":         event.event_id,
        "pilot":            event.pilot,
        "actions":          ["a1", "a2", "a3", "a4", "a5", "a6"],  # > 5
        "agent_confidence": 0.96,
    })
    assert not result.overall_success
    assert any(r.response_code == 403 for r in result.action_results)
