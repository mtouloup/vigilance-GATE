"""Scenario A — OTE Credential Stuffing end-to-end pipeline test."""
from __future__ import annotations
import pytest

from vigilance.pipeline import T53Pipeline


def test_scenario_a_ote_credential_stuffing():
    """Full pipeline: CEF brute-force alert → block_ip + revoke_session + notify_soc"""
    raw_cef = (
        "CEF:0|OTE-IDS|SOCv3|2.0|200|AUTH_BRUTE_FORCE|9|"
        "src=91.108.4.12 dst=nms-01 cnt=230 nodes=3 app=SSH"
    )
    pipeline = T53Pipeline(sector="TELECOM")
    result = pipeline.process_event(raw_cef)

    assert result.overall_success
    assert any(r.action == "block_ip" for r in result.action_results)
    assert any(r.action == "revoke_session" for r in result.action_results)
    assert any(r.action == "notify_soc" for r in result.action_results)


def test_scenario_a_audit_record_created():
    """Verify audit record is opened and closed during OTE pipeline run."""
    raw_cef = (
        "CEF:0|OTE-IDS|SOCv3|2.0|200|AUTH_BRUTE_FORCE|9|"
        "src=91.108.4.12 dst=nms-01 cnt=230 nodes=3 app=SSH"
    )
    pipeline = T53Pipeline(sector="TELECOM")
    result = pipeline.process_event(raw_cef)

    records = pipeline.audit_log.get_all()
    assert len(records) == 1
    record = records[0]
    assert record.closed is True
    assert record.audit_id.startswith("aud-OTE-")
    assert record.verdict in ("APPROVED", "SUCCESS")


def test_scenario_a_broker_publishes_result():
    """Verify result is published to t53.results broker topic."""
    raw_cef = (
        "CEF:0|OTE-IDS|SOCv3|2.0|200|AUTH_BRUTE_FORCE|9|"
        "src=91.108.4.12 dst=nms-01 cnt=230 nodes=3 app=SSH"
    )
    pipeline = T53Pipeline(sector="TELECOM")
    pipeline.process_event(raw_cef)

    messages = pipeline.broker.get_messages("t53.results")
    assert len(messages) == 1
    assert messages[0]["overall_success"] is True


def test_scenario_a_all_actions_succeed():
    """All individual actions must succeed for OTE credential stuffing."""
    raw_cef = (
        "CEF:0|OTE-IDS|SOCv3|2.0|200|AUTH_BRUTE_FORCE|9|"
        "src=91.108.4.12 dst=nms-01 cnt=230 nodes=3 app=SSH"
    )
    pipeline = T53Pipeline(sector="TELECOM")
    result = pipeline.process_event(raw_cef)

    for action_result in result.action_results:
        assert action_result.success, (
            f"Action '{action_result.action}' failed: {action_result.message}"
        )
        assert action_result.latency_ms >= 0
