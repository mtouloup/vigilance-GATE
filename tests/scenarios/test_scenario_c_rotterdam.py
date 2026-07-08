"""Scenario C — Port of Rotterdam AIS Spoofing end-to-end pipeline test (INTEGRATED flow)."""
from __future__ import annotations
import uuid
import pytest

from vigilance.pipeline import T53Pipeline


RAW_AIS_EVENT = {
    "vessel_id": "VESSEL-042",
    "ais_mmsi": "244820000",
    "port_zone": "Berth-7",
    "anomaly": "ais_position_spoofing",
    "severity": "HIGH",
    "source": "port-radar-monitor",
}

T54_ACTIONS = ["block_vessel_access", "quarantine_cargo_system", "notify_port_authority", "notify_soc"]


@pytest.fixture
def pipeline():
    return T53Pipeline(dry_run=True)


def _ingest_and_execute(pipeline, raw, actions=T54_ACTIONS, confidence=0.88):
    event = pipeline.ingest_event(raw)
    result, _rego = pipeline.execute_action_request({
        "request_id":       str(uuid.uuid4()),
        "event_id":         event.event_id,
        "pilot":            event.pilot,
        "actions":          actions,
        "agent_confidence": confidence,
    })
    return result


def test_scenario_c_ingest_detects_maritime(pipeline):
    event = pipeline.ingest_event(RAW_AIS_EVENT)
    assert event.pilot == "MARITIME"
    assert event.severity == "HIGH"


def test_scenario_c_canonical_event_published(pipeline):
    pipeline.ingest_event(RAW_AIS_EVENT)
    messages = pipeline.broker.get_messages("t53.canonical_events")
    assert len(messages) == 1
    assert messages[0]["pilot"] == "MARITIME"


def test_scenario_c_execution_succeeds(pipeline):
    result = _ingest_and_execute(pipeline, RAW_AIS_EVENT)
    assert result.overall_success


def test_scenario_c_expected_actions_dispatched(pipeline):
    result = _ingest_and_execute(pipeline, RAW_AIS_EVENT)
    dispatched = [r.action for r in result.action_results]
    assert "block_vessel_access" in dispatched
    assert "notify_soc" in dispatched


def test_scenario_c_audit_record_created(pipeline):
    _ingest_and_execute(pipeline, RAW_AIS_EVENT)
    records = pipeline.audit_log.get_all()
    assert len(records) == 1
    assert records[0].audit_id.startswith("aud-ROT-")


def test_scenario_c_result_published_to_broker(pipeline):
    _ingest_and_execute(pipeline, RAW_AIS_EVENT)
    messages = pipeline.broker.get_messages("t53.results")
    assert len(messages) == 1
    assert messages[0]["overall_success"] is True


def test_scenario_c_correct_sector_profile(pipeline):
    assert pipeline.profiles["MARITIME"].sector == "MARITIME"
    assert pipeline.profiles["MARITIME"].pilot == "Rotterdam_NL"
    assert pipeline.profiles["MARITIME"].ot_safety_flag is False
