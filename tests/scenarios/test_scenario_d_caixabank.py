"""Scenario D — CaixaBank Account Takeover end-to-end pipeline test."""
from __future__ import annotations
import pytest

from vigilance.pipeline import T53Pipeline


_RAW_FRAUD_EVENT = {
    "account_id": "ACC-ES-0099182",
    "transaction_id": "TXN-2026-887341",
    "branch_id": "BCN-CENTRAL",
    "anomaly": "account_takeover_attempt",
    "fraud_score": 0.94,
    "severity": "HIGH",
    "source": "caixabank-fraud-monitor",
}


def test_scenario_d_caixabank_account_takeover():
    """Full pipeline: account takeover alert → freeze_account + block_transaction + notify."""
    pipeline = T53Pipeline(sector="FINANCE")
    result = pipeline.process_event(_RAW_FRAUD_EVENT)

    assert result.overall_success
    assert any(r.action == "freeze_account" for r in result.action_results)
    assert any(r.action == "notify_soc" for r in result.action_results)


def test_scenario_d_audit_record_created():
    """Verify audit record is opened and closed with CAI prefix."""
    pipeline = T53Pipeline(sector="FINANCE")
    pipeline.process_event(_RAW_FRAUD_EVENT)

    records = pipeline.audit_log.get_all()
    assert len(records) == 1
    record = records[0]
    assert record.closed is True
    assert record.audit_id.startswith("aud-CAI-")
    assert record.verdict in ("APPROVED", "SUCCESS", "ESCALATE")


def test_scenario_d_broker_publishes_result():
    """Verify result is published to t53.results broker topic."""
    pipeline = T53Pipeline(sector="FINANCE")
    pipeline.process_event(_RAW_FRAUD_EVENT)

    messages = pipeline.broker.get_messages("t53.results")
    assert len(messages) == 1
    assert messages[0]["overall_success"] is True


def test_scenario_d_all_actions_succeed():
    """All individual actions must succeed for the CaixaBank account takeover scenario."""
    pipeline = T53Pipeline(sector="FINANCE")
    result = pipeline.process_event(_RAW_FRAUD_EVENT)

    for action_result in result.action_results:
        assert action_result.success, (
            f"Action '{action_result.action}' failed: {action_result.message}"
        )
        assert action_result.latency_ms >= 0


def test_scenario_d_correct_sector_profile():
    """Verify the FINANCE profile is loaded with CaixaBank_ES pilot."""
    pipeline = T53Pipeline(sector="FINANCE")
    assert pipeline.profiles["FINANCE"].sector == "FINANCE"
    assert pipeline.profiles["FINANCE"].pilot == "CaixaBank_ES"
    assert pipeline.profiles["FINANCE"].ot_safety_flag is False
    assert pipeline.profiles["FINANCE"].confidence_threshold == 0.85
    assert "bank_siem" in pipeline.profiles["FINANCE"].tool_plugins
    assert "bank_iam" in pipeline.profiles["FINANCE"].tool_plugins
    assert "fraud_engine" in pipeline.profiles["FINANCE"].tool_plugins


def test_scenario_d_higher_confidence_threshold():
    """Finance sector requires confidence >= 0.85 (higher than default 0.80)."""
    pipeline = T53Pipeline(sector="FINANCE")
    assert pipeline.profiles["FINANCE"].confidence_threshold == 0.85
