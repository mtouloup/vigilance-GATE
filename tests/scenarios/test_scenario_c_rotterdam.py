"""Scenario C — Port of Rotterdam AIS Spoofing end-to-end pipeline test."""
from __future__ import annotations
import pytest

from vigilance.pipeline import T53Pipeline


_RAW_AIS_EVENT = {
    "vessel_id": "VESSEL-042",
    "ais_mmsi": "244820000",
    "port_zone": "Berth-7",
    "anomaly": "ais_position_spoofing",
    "severity": "HIGH",
    "source": "port-radar-monitor",
}


def test_scenario_c_rotterdam_ais_spoofing():
    """Full pipeline: AIS spoofing alert → block_vessel_access + quarantine + notify."""
    pipeline = T53Pipeline(sector="MARITIME")
    result = pipeline.process_event(_RAW_AIS_EVENT)

    assert result.overall_success
    assert any(r.action == "block_vessel_access" for r in result.action_results)
    assert any(r.action == "notify_soc" for r in result.action_results)


def test_scenario_c_audit_record_created():
    """Verify audit record is opened and closed with ROT prefix."""
    pipeline = T53Pipeline(sector="MARITIME")
    pipeline.process_event(_RAW_AIS_EVENT)

    records = pipeline.audit_log.get_all()
    assert len(records) == 1
    record = records[0]
    assert record.closed is True
    assert record.audit_id.startswith("aud-ROT-")
    assert record.verdict in ("APPROVED", "SUCCESS", "ESCALATE")


def test_scenario_c_broker_publishes_result():
    """Verify result is published to t53.results broker topic."""
    pipeline = T53Pipeline(sector="MARITIME")
    pipeline.process_event(_RAW_AIS_EVENT)

    messages = pipeline.broker.get_messages("t53.results")
    assert len(messages) == 1
    assert messages[0]["overall_success"] is True


def test_scenario_c_all_actions_succeed():
    """All individual actions must succeed for the Rotterdam AIS spoofing scenario."""
    pipeline = T53Pipeline(sector="MARITIME")
    result = pipeline.process_event(_RAW_AIS_EVENT)

    for action_result in result.action_results:
        assert action_result.success, (
            f"Action '{action_result.action}' failed: {action_result.message}"
        )
        assert action_result.latency_ms >= 0


def test_scenario_c_correct_sector_profile():
    """Verify the MARITIME profile is loaded with Rotterdam_NL pilot."""
    pipeline = T53Pipeline(sector="MARITIME")
    assert pipeline.profile.sector == "MARITIME"
    assert pipeline.profile.pilot == "Rotterdam_NL"
    assert pipeline.profile.ot_safety_flag is False
    assert "port_siem" in pipeline.profile.tool_plugins
    assert "port_iam" in pipeline.profile.tool_plugins
    assert "port_ops" in pipeline.profile.tool_plugins
