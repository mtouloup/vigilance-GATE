"""Tests for C4 — Tool Adapter Layer."""
from __future__ import annotations
import pytest

from vigilance.components.c4_adapters.telecom.siem_plugin import SIEMPlugin as TeleSIEM
from vigilance.components.c4_adapters.telecom.iam_plugin import IAMPlugin as TeleIAM
from vigilance.components.c4_adapters.telecom.ids_plugin import IDSPlugin as TeleIDS
from vigilance.components.c4_adapters.industry4.siem_plugin import SIEMPlugin as IndSIEM
from vigilance.components.c4_adapters.industry4.iam_plugin import IAMPlugin as OTIAM
from vigilance.components.c4_adapters.industry4.scada_plugin import SCADAPlugin


class TestTelecomAdapters:
    def test_siem_block_ip(self):
        plugin = TeleSIEM()
        result = plugin.execute("block_ip", {"event_id": "evt-001"})
        assert result.success
        assert result.response_code == 200
        assert result.plugin == "ote_siem"
        assert result.latency_ms > 0

    def test_siem_query_logs(self):
        plugin = TeleSIEM()
        result = plugin.execute("query_logs", {})
        assert result.success
        assert result.response_code == 200

    def test_iam_revoke_session(self):
        plugin = TeleIAM()
        result = plugin.execute("revoke_session", {})
        assert result.success
        assert result.plugin == "ote_iam"
        assert result.latency_ms >= 60

    def test_ids_notify_soc(self):
        plugin = TeleIDS()
        result = plugin.execute("notify_soc", {})
        assert result.success
        assert result.plugin == "ote_ids"
        assert result.latency_ms >= 180

    def test_siem_create_incident(self):
        plugin = TeleSIEM()
        result = plugin.execute("create_incident", {"target": "brute-force-auth-server-01"})
        assert result.success
        assert result.response_code == 201
        assert result.plugin == "ote_siem"
        assert "INC-" in result.message
        assert "brute-force-auth-server-01" in result.message

    def test_siem_create_incident_no_target(self):
        plugin = TeleSIEM()
        result = plugin.execute("create_incident", {})
        assert result.success
        assert "unspecified" in result.message

    def test_siem_supported_actions(self):
        plugin = TeleSIEM()
        assert set(plugin.supported_actions) == {"block_ip", "query_logs", "create_incident"}

    def test_unsupported_action(self):
        plugin = TeleSIEM()
        result = plugin.execute("nonexistent", {})
        assert not result.success
        assert result.response_code == 400


class TestIndustry4Adapters:
    def test_industrial_siem_query_logs(self):
        plugin = IndSIEM()
        result = plugin.execute("query_logs", {})
        assert result.success
        assert result.plugin == "industrial_siem"

    def test_ot_iam_revoke_session(self):
        plugin = OTIAM()
        result = plugin.execute("revoke_ot_session", {})
        assert result.success
        assert result.plugin == "ot_iam"

    def test_scada_isolate_plc_safe_state(self):
        plugin = SCADAPlugin()
        result = plugin.execute("isolate_plc", {"mode": "safe-state", "plc_id": "PLC-07"})
        assert result.success
        assert result.plugin == "scada_opcua"
        assert "safe-state" in result.message.lower() or "PLC" in result.message

    def test_scada_isolate_plc_requires_safe_state(self):
        plugin = SCADAPlugin()
        with pytest.raises(ValueError, match="safe-state"):
            plugin.execute("isolate_plc", {"mode": "hard-shutdown"})

    def test_scada_isolate_plc_no_mode_raises(self):
        plugin = SCADAPlugin()
        with pytest.raises(ValueError):
            plugin.execute("isolate_plc", {})

    def test_scada_notify_soc(self):
        plugin = SCADAPlugin()
        result = plugin.execute("notify_soc", {})
        assert result.success

    def test_scada_update_zt_policy(self):
        plugin = SCADAPlugin()
        result = plugin.execute("update_zt_policy", {})
        assert result.success
        assert result.latency_ms >= 90

    def test_industrial_siem_create_incident(self):
        plugin = IndSIEM()
        result = plugin.execute("create_incident", {"target": "plc-anomaly-line-7"})
        assert result.success
        assert result.response_code == 201
        assert result.plugin == "industrial_siem"
        assert "INC-" in result.message
        assert "plc-anomaly-line-7" in result.message

    def test_industrial_siem_create_incident_no_target(self):
        plugin = IndSIEM()
        result = plugin.execute("create_incident", {})
        assert result.success
        assert "unspecified" in result.message

    def test_industrial_siem_supported_actions(self):
        plugin = IndSIEM()
        assert set(plugin.supported_actions) == {"query_logs", "block_ip", "create_incident"}

    def test_supported_actions_listed(self):
        plugin = SCADAPlugin()
        assert "isolate_plc" in plugin.supported_actions
        assert "notify_soc" in plugin.supported_actions
        assert "update_zt_policy" in plugin.supported_actions
