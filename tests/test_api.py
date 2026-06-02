"""Tests for the T5.3 REST API (T5.6 integration point)."""
from __future__ import annotations
import uuid
import pytest
from fastapi.testclient import TestClient

from vigilance.api.app import app
import vigilance.api.app as api_module


@pytest.fixture(autouse=True)
def reset_pipeline():
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
        assert set(data["pilots"]) == {"TELECOM", "MARITIME", "FINANCE", "INDUSTRY_4"}

    def test_health_includes_timestamp(self, client):
        assert "timestamp" in client.get("/api/v1/health").json()


class TestProfilesEndpoint:
    def test_profiles_returns_all_four_sectors(self, client):
        data = client.get("/api/v1/profiles").json()
        assert set(data.keys()) == {"TELECOM", "MARITIME", "FINANCE", "INDUSTRY_4"}

    def test_profiles_include_expected_fields(self, client):
        telecom = client.get("/api/v1/profiles").json()["TELECOM"]
        for field in ("pilot", "sector", "tool_plugins", "confidence_threshold", "ot_safety_flag"):
            assert field in telecom

    def test_industry4_has_ot_safety_flag(self, client):
        assert client.get("/api/v1/profiles").json()["INDUSTRY_4"]["ot_safety_flag"] is True

    def test_telecom_no_ot_safety_flag(self, client):
        assert client.get("/api/v1/profiles").json()["TELECOM"]["ot_safety_flag"] is False


class TestEventsEndpoint:
    """POST /api/v1/events — C1 normalize only, returns 202 Accepted."""

    def test_submit_telecom_event_returns_202(self, client):
        resp = client.post("/api/v1/events", json={
            "raw": "CEF:0|OTE-IDS|SOCv3|2.0|200|AUTH_BRUTE_FORCE|9|src=91.108.4.12 dst=nms-01 cnt=230 nodes=3 app=SSH"
        })
        assert resp.status_code == 202
        data = resp.json()
        assert "event_id" in data
        assert data["pilot"] == "TELECOM"

    def test_submit_maritime_event(self, client):
        resp = client.post("/api/v1/events", json={
            "raw": {"vessel_id": "VESSEL-042", "ais_mmsi": "244820000",
                    "port_zone": "Berth-7", "anomaly": "ais_position_spoofing",
                    "severity": "HIGH"}
        })
        assert resp.status_code == 202
        assert resp.json()["pilot"] == "MARITIME"

    def test_submit_finance_event(self, client):
        resp = client.post("/api/v1/events", json={
            "raw": {"account_id": "ACC-ES-001", "transaction_id": "TXN-001",
                    "anomaly": "account_takeover_attempt", "fraud_score": 0.94,
                    "severity": "HIGH"}
        })
        assert resp.status_code == 202
        assert resp.json()["pilot"] == "FINANCE"

    def test_submit_industry4_event(self, client):
        resp = client.post("/api/v1/events", json={
            "raw": {"plc": "PLC-07", "line": "Line-3", "protocol": "OPC-UA",
                    "anomaly": "register_write_out_of_range", "severity": "CRITICAL"}
        })
        assert resp.status_code == 202
        assert resp.json()["pilot"] == "INDUSTRY_4"

    def test_response_includes_event_id(self, client):
        resp = client.post("/api/v1/events", json={
            "raw": "CEF:0|OTE-IDS|SOCv3|2.0|200|AUTH_BRUTE_FORCE|9|src=91.108.4.12 dst=nms-01 cnt=230"
        })
        assert "event_id" in resp.json()


class TestActionRequestsEndpoint:
    """POST /api/v1/action-requests — C5+C3+C4 execute, returns ExecutionResult."""

    def test_submit_action_request_telecom(self, client):
        resp = client.post("/api/v1/action-requests", json={
            "request_id": str(uuid.uuid4()),
            "event_id": str(uuid.uuid4()),
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
            "request_id": str(uuid.uuid4()),
            "event_id": str(uuid.uuid4()),
            "pilot": "INDUSTRY_4",
            "actions": ["isolate_plc", "notify_soc"],
            "agent_confidence": 0.91,
            "policy_update": "Deny all OPC-UA traffic from Zone-B for 2 hours",
        })
        assert resp.status_code in (200, 207)
        assert "action_results" in resp.json()

    def test_too_many_actions_rejected(self, client):
        """Guardrail rejects when action count exceeds 5 (proportionality check)."""
        resp = client.post("/api/v1/action-requests", json={
            "request_id": str(uuid.uuid4()),
            "event_id": str(uuid.uuid4()),
            "pilot": "TELECOM",
            "actions": ["a1", "a2", "a3", "a4", "a5", "a6"],  # > 5
            "agent_confidence": 0.95,
        })
        data = resp.json()
        assert not data["overall_success"]
        assert any(r["response_code"] == 403 for r in data["action_results"])


class TestOpenAPISpec:
    def test_openapi_schema_accessible(self, client):
        schema = client.get("/api/openapi.json").json()
        assert schema["info"]["title"] == "T5.3 Agentic Wrapper Framework"

    def test_swagger_ui_accessible(self, client):
        assert client.get("/api/docs").status_code == 200

    def test_redoc_accessible(self, client):
        assert client.get("/api/redoc").status_code == 200
