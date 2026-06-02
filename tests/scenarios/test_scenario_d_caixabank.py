"""Scenario D — CaixaBank Account Takeover end-to-end pipeline test (INTEGRATED flow)."""
from __future__ import annotations
import uuid
import pytest

from vigilance.pipeline import T53Pipeline


RAW_FRAUD_EVENT = {
    "account_id": "ACC-ES-0099182",
    "transaction_id": "TXN-2026-887341",
    "branch_id": "BCN-CENTRAL",
    "anomaly": "account_takeover_attempt",
    "fraud_score": 0.94,
    "severity": "HIGH",
    "source": "caixabank-fraud-monitor",
}

T54_ACTIONS = ["freeze_account", "block_transaction", "notify_fraud_team", "notify_soc"]


@pytest.fixture
def pipeline():
    return T53Pipeline(dry_run=True)


def _ingest_and_execute(pipeline, raw, actions=T54_ACTIONS, confidence=0.93):
    event = pipeline.ingest_event(raw)
    return pipeline.execute_action_request({
        "request_id":       str(uuid.uuid4()),
        "event_id":         event.event_id,
        "pilot":            event.pilot,
        "actions":          actions,
        "agent_confidence": confidence,
    })


def test_scenario_d_ingest_detects_finance(pipeline):
    event = pipeline.ingest_event(RAW_FRAUD_EVENT)
    assert event.pilot == "FINANCE"
    assert event.severity == "HIGH"


def test_scenario_d_canonical_event_published(pipeline):
    pipeline.ingest_event(RAW_FRAUD_EVENT)
    messages = pipeline.broker.get_messages("t53.canonical_events")
    assert len(messages) == 1
    assert messages[0]["pilot"] == "FINANCE"


def test_scenario_d_execution_succeeds(pipeline):
    result = _ingest_and_execute(pipeline, RAW_FRAUD_EVENT)
    assert result.overall_success


def test_scenario_d_expected_actions_dispatched(pipeline):
    result = _ingest_and_execute(pipeline, RAW_FRAUD_EVENT)
    dispatched = [r.action for r in result.action_results]
    assert "freeze_account" in dispatched
    assert "notify_soc" in dispatched


def test_scenario_d_audit_record_created(pipeline):
    _ingest_and_execute(pipeline, RAW_FRAUD_EVENT)
    records = pipeline.audit_log.get_all()
    assert len(records) == 1
    assert records[0].audit_id.startswith("aud-CAI-")


def test_scenario_d_result_published_to_broker(pipeline):
    _ingest_and_execute(pipeline, RAW_FRAUD_EVENT)
    messages = pipeline.broker.get_messages("t53.results")
    assert len(messages) == 1
    assert messages[0]["overall_success"] is True


def test_scenario_d_higher_confidence_threshold(pipeline):
    """Finance requires confidence >= 0.85 (stricter than the 0.80 default)."""
    assert pipeline.profiles["FINANCE"].confidence_threshold == 0.85


def test_scenario_d_guardrail_rejects_too_many_actions(pipeline):
    """Guardrail always rejects when action count exceeds 5 (proportionality check)."""
    event = pipeline.ingest_event(RAW_FRAUD_EVENT)
    result = pipeline.execute_action_request({
        "request_id":       str(uuid.uuid4()),
        "event_id":         event.event_id,
        "pilot":            event.pilot,
        "actions":          ["a1", "a2", "a3", "a4", "a5", "a6"],  # > 5
        "agent_confidence": 0.93,
    })
    assert not result.overall_success
    assert any(r.response_code == 403 for r in result.action_results)


def test_scenario_d_correct_sector_profile(pipeline):
    assert pipeline.profiles["FINANCE"].sector == "FINANCE"
    assert pipeline.profiles["FINANCE"].pilot == "CaixaBank_ES"
    assert pipeline.profiles["FINANCE"].ot_safety_flag is False
