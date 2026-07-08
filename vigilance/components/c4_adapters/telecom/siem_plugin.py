"""OTE SIEM plugin — stub adapter for block_ip, query_logs, and create_incident actions."""
from __future__ import annotations

import uuid

from vigilance.components.c4_adapters.base import ToolAdapter
from vigilance.models.execution_result import ActionResult


class SIEMPlugin(ToolAdapter):
    """Stub SIEM adapter for OTE (Telecom) pilot.

    Simulates HTTP calls with realistic latencies (30-50ms).
    """

    @property
    def plugin_name(self) -> str:
        return "ote_siem"

    @property
    def supported_actions(self) -> list[str]:
        return ["block_ip", "query_logs", "create_incident"]

    def execute(self, action: str, params: dict) -> ActionResult:
        if action == "block_ip":
            return ActionResult(
                action=action,
                plugin=self.plugin_name,
                success=True,
                latency_ms=38,
                response_code=200,
                message=f"IP {params.get('event_id', 'unknown')} blocked in SIEM firewall rule",
            )
        elif action == "query_logs":
            return ActionResult(
                action=action,
                plugin=self.plugin_name,
                success=True,
                latency_ms=45,
                response_code=200,
                message="SIEM log query completed: 247 events retrieved",
            )
        elif action == "create_incident":
            return self._create_incident(params)
        else:
            return ActionResult(
                action=action,
                plugin=self.plugin_name,
                success=False,
                latency_ms=5,
                response_code=400,
                message=f"Unsupported action: {action}",
            )

    def _create_incident(self, params: dict) -> ActionResult:
        incident_id = f"INC-{uuid.uuid4().hex[:8]}"
        return ActionResult(
            action="create_incident",
            plugin=self.plugin_name,
            success=True,
            latency_ms=42,
            response_code=201,
            message=f"Incident {incident_id} created: {params.get('target', 'unspecified')}",
        )
