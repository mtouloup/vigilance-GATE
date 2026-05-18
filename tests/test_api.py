"""Tests for the T5.3 REST API (T5.6 integration point)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from vigilance.api.app import app, _pipeline
import vigilance.api.app as api_module


@pytest.fixture(autouse=True)
def reset_pipeline():
    """Ensure each test starts with a fresh pipeline singleton."""
    api_module._pipeline = None
    yield
    api_module._pipeline = None


@pytest.fixture
def client():
    return TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "pilots" in data
        assert "TELECOM" in data["pilots"]
        assert "MARITIME" in data["pilots"]
        assert "FINANCE" in data["pilots"]
        assert "INDUSTRY_4" in data["pilots"]

    def test_health_includes_mode(self, client):
        resp = client.get("/api/v1/health")
        assert "mode" in resp.json()

    def test_health_includes_timestamp(self, client):
        resp = client.get("/api/v1/health")
        assert "timestamp" in resp.json()


class TestProfilesEndpoint:
    def test_profiles_returns_all_four_sectors(self, client):
        resp = client.get("/api/v1/profiles")
        assert resp.status_code == 200
        data = resp.json()
        assert set(data.keys()) == {"TELECOM", "MARITIME", "FINANCE", "INDUSTRY_4"}

    def test_profiles_include_expected_fields(self, client):
        resp = client.get("/api/v1/profiles")
        telecom = resp.json()["TELECOM"]
        assert "pilot" in telecom
        assert "sector" in telecom
        assert "tool_plugins" in telecom
        assert "confidence_threshold" in telecom
        assert "ot_safety_flag" in telecom

    def test_industry4_has_ot_safety_flag(self, client):
        resp = client.get("/api/v1/profiles")
        assert resp.json()["INDUSTRY_4"]["ot_safety_flag"] is True

    def test_telecom_ot_safety_flag_false(self, client):
        resp = client.get("/api/v1/profiles")
        assert resp.json()["TELECOM"]["ot_safety_flag"] is False


class TestEventsEndpoint:
    def test_submit_telecom_event(self, client):
        resp = client.post("/api/v1/events", json={
            "raw": "CEF:0|OTE-IDS|SOCv3|2.0|200|AUTH_BRUTE_FORCE|9|src=91.108.4.12 dst=nms-01 cnt=230 nodes=3 app=SSH"
        })
        assert resp.status_code in (200, 207)
        data = resp.json()
        assert "action_results" in data
        assert "overall_success" in data

    def test_submit_maritime_event(self, client):
        resp = client.post("/api/v1/events", json={
            "raw": {"vessel_id": "VESSEL-042", "ais_mmsi": "244820000",
                    "port_zone": "Berth-7", "anomaly": "ais_position_spoofing",
                    "severity": "HIGH"}
        })
        assert resp.status_code in (200, 207)
        data = resp.json()
        assert "action_results" in data

    def test_submit_finance_event(self, client):
        resp = client.post("/api/v1/events", json={
            "raw": {"account_id": "ACC-ES-001", "transaction_id": "TXN-001",
                    "anomaly": "account_takeover_attempt", "fraud_score": 0.94,
                    "severity": "HIGH"}
        })
        assert resp.status_code in (200, 207)
        data = resp.json()
        assert "action_results" in data

    def test_submit_industry4_event(self, client):
        resp = client.post("/api/v1/events", json={
            "raw": {"plc": "PLC-07", "line": "Line-3", "protocol": "OPC-UA",
                    "anomaly": "register_write_out_of_range", "severity": "CRITICAL"}
        })
        assert resp.status_code in (200, 207)
        data = resp.json()
        assert "action_results" in data

    def test_result_has_pilot(self, client):
        resp = client.post("/api/v1/events", json={
            "raw": "CEF:0|OTE-IDS|SOCv3|2.0|200|AUTH_BRUTE_FORCE|9|src=91.108.4.12 dst=nms-01 cnt=230"
        })
        data = resp.json()
        assert "pilot" in data


class TestActionRequestsEndpoint:
    def test_submit_action_request(self, client):
        resp = client.post("/api/v1/action-requests", json={
            "request_id": "req-api-001",
            "event_id": "evt-api-001",
            "pilot": "TELECOM",
            "actions": ["block_ip", "notify_soc"],
            "agent_confidence": 0.92,
        })
        assert resp.status_code in (200, 207)
        data = resp.json()
        assert "action_results" in data
        assert "overall_success" in data

    def test_submit_action_request_industry4(self, client):
        resp = client.post("/api/v1/action-requests", json={
            "request_id": "req-api-002",
            "event_id": "evt-api-002",
            "pilot": "INDUSTRY_4",
            "actions": ["isolate_plc", "notify_soc"],
            "agent_confidence": 0.91,
            "policy_update": "Deny all OPC-UA traffic from Zone-B for 2 hours",
        })
        assert resp.status_code in (200, 207)
        data = resp.json()
        assert "action_results" in data


class TestOpenAPISpec:
    def test_openapi_schema_accessible(self, client):
        resp = client.get("/api/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert schema["info"]["title"] == "T5.3 Agentic Wrapper Framework"

    def test_swagger_ui_accessible(self, client):
        resp = client.get("/api/docs")
        assert resp.status_code == 200

    def test_redoc_accessible(self, client):
        resp = client.get("/api/redoc")
        assert resp.status_code == 200
