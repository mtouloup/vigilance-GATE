"""C2 tool definitions for the agentic loop."""
from __future__ import annotations
import json


def query_siem_logs(target: str, window_min: int = 60) -> dict:
    """Query stub SIEM logs for the given target over the specified time window.

    Returns plausible stub log data demonstrating repeated authentication failures.
    """
    return {
        "target": target,
        "window_min": window_min,
        "total_events": 247,
        "failed_auth_count": 230,
        "unique_src_ips": ["91.108.4.12", "91.108.4.13", "185.220.101.5"],
        "event_types": ["AUTH_FAILURE", "AUTH_FAILURE", "AUTH_SUCCESS"],
        "top_src_ip": "91.108.4.12",
        "top_src_ip_count": 189,
        "protocols": ["SSH", "HTTPS"],
        "summary": (
            f"SIEM shows {230} failed authentication attempts against {target} "
            f"in the last {window_min} minutes from 3 source IPs. "
            "Pattern consistent with credential stuffing attack."
        ),
    }


def query_iam_sessions(target: str) -> dict:
    """Query stub IAM sessions for the given target.

    Returns plausible stub session data.
    """
    return {
        "target": target,
        "active_sessions": 12,
        "suspicious_sessions": 3,
        "sessions": [
            {
                "session_id": "sess-0042",
                "user": "admin@ote.gr",
                "src_ip": "91.108.4.12",
                "created_at": "2026-01-01T00:15:00Z",
                "last_activity": "2026-01-01T00:58:00Z",
                "risk_score": 0.92,
                "flags": ["impossible_travel", "new_device"],
            },
            {
                "session_id": "sess-0043",
                "user": "svc_monitor@ote.gr",
                "src_ip": "91.108.4.12",
                "created_at": "2026-01-01T00:22:00Z",
                "last_activity": "2026-01-01T00:55:00Z",
                "risk_score": 0.88,
                "flags": ["new_device"],
            },
        ],
        "recommendation": "Revoke suspicious sessions sess-0042, sess-0043 immediately.",
    }


def query_threat_intel(ioc: str) -> dict:
    """Query stub threat intelligence for the given indicator of compromise."""
    return {
        "ioc": ioc,
        "reputation": "malicious",
        "threat_category": "credential_stuffing_botnet",
        "confidence": 0.95,
        "sources": ["VirusTotal", "Shodan", "AlienVault OTX"],
        "last_seen": "2026-01-01T00:45:00Z",
        "campaigns": ["STORM-0539", "TELECOM-CRED-2025"],
        "recommended_action": "block_ip",
    }


# Tool registry for the agent loop
AVAILABLE_TOOLS: dict[str, callable] = {
    "query_siem_logs": query_siem_logs,
    "query_iam_sessions": query_iam_sessions,
    "query_threat_intel": query_threat_intel,
}


def dispatch_tool(tool_name: str, params: dict) -> str:
    """Dispatch a tool call and return JSON-encoded result."""
    fn = AVAILABLE_TOOLS.get(tool_name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    result = fn(**params)
    return json.dumps(result)
