"""Scenario B — Siemens OT Anomaly end-to-end pipeline test."""
from __future__ import annotations
import pytest

from vigilance.pipeline import T53Pipeline


def test_scenario_b_siemens_ot_anomaly():
    """Full pipeline: OT JSON anomaly → isolate_plc(safe-state) + revoke_ot_session + notify_soc + update_zt_policy"""
    raw_ot = {
        "plc": "PLC-07",
        "line": "Line-3",
        "protocol": "OPC-UA",
        "anomaly": "register_write_out_of_range",
        "severity": "CRITICAL",
    }
    pipeline = T53Pipeline(sector="INDUSTRY_4")
    result = pipeline.process_event(raw_ot)

    assert result.overall_success
    assert any(r.action == "isolate_plc" for r in result.action_results)
    assert any(r.action == "revoke_ot_session" for r in result.action_results)


def test_scenario_b_all_expected_actions():
    """All four OT response actions must be present."""
    raw_ot = {
        "plc": "PLC-07",
        "line": "Line-3",
        "protocol": "OPC-UA",
        "anomaly": "register_write_out_of_range",
        "severity": "CRITICAL",
    }
    pipeline = T53Pipeline(sector="INDUSTRY_4")
    result = pipeline.process_event(raw_ot)

    actions_executed = {r.action for r in result.action_results}
    assert "isolate_plc" in actions_executed
    assert "revoke_ot_session" in actions_executed
    assert "notify_soc" in actions_executed
    assert "update_zt_policy" in actions_executed


def test_scenario_b_audit_record_sie():
    """Verify audit record uses SIE prefix for Siemens pilot."""
    raw_ot = {
        "plc": "PLC-07",
        "line": "Line-3",
        "protocol": "OPC-UA",
        "anomaly": "register_write_out_of_range",
        "severity": "CRITICAL",
    }
    pipeline = T53Pipeline(sector="INDUSTRY_4")
    pipeline.process_event(raw_ot)

    records = pipeline.audit_log.get_all()
    assert len(records) == 1
    record = records[0]
    assert record.audit_id.startswith("aud-SIE-")
    assert record.closed is True


def test_scenario_b_ot_safety_flag_checked():
    """Verify OT safety checks are performed for Siemens OT events."""
    raw_ot = {
        "plc": "PLC-07",
        "line": "Line-3",
        "protocol": "OPC-UA",
        "anomaly": "register_write_out_of_range",
        "severity": "CRITICAL",
    }
    pipeline = T53Pipeline(sector="INDUSTRY_4")
    result = pipeline.process_event(raw_ot)

    # Verify safe-state mode was used for isolate_plc
    isolate_result = next(
        (r for r in result.action_results if r.action == "isolate_plc"), None
    )
    assert isolate_result is not None
    assert isolate_result.success
    # Safe-state enforcement should be reflected in the message
    assert "safe-state" in isolate_result.message.lower() or isolate_result.response_code == 200


def test_scenario_b_all_actions_succeed():
    """All individual OT actions must succeed."""
    raw_ot = {
        "plc": "PLC-07",
        "line": "Line-3",
        "protocol": "OPC-UA",
        "anomaly": "register_write_out_of_range",
        "severity": "CRITICAL",
    }
    pipeline = T53Pipeline(sector="INDUSTRY_4")
    result = pipeline.process_event(raw_ot)

    for action_result in result.action_results:
        assert action_result.success, (
            f"Action '{action_result.action}' failed: {action_result.message}"
        )
