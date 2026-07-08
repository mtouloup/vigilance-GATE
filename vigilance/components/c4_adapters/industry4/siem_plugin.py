"""Industrial SIEM plugin — stub adapter for Siemens Industry 4.0 pilot."""
from __future__ import annotations

import uuid

from vigilance.components.c4_adapters.base import ToolAdapter
from vigilance.models.execution_result import ActionResult


class SIEMPlugin(ToolAdapter):
    """Stub industrial SIEM adapter for Siemens (Industry 4.0) pilot.

    Simulates HTTP calls with realistic latencies (40-60ms).
    """

    @property
    def plugin_name(self) -> str:
        return "industrial_siem"

    @property
    def supported_actions(self) -> list[str]:
        return ["query_logs", "block_ip", "create_incident"]

    def execute(self, action: str, params: dict) -> ActionResult:
        if action == "query_logs":
            return ActionResult(
                action=action,
                plugin=self.plugin_name,
                success=True,
                latency_ms=52,
                response_code=200,
                message="Industrial SIEM log query completed: OT anomaly events retrieved",
            )
        elif action == "block_ip":
            return ActionResult(
                action=action,
                plugin=self.plugin_name,
                success=True,
                latency_ms=44,
                response_code=200,
                message="IT/OT boundary firewall rule applied — IP blocked",
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
            latency_ms=47,
            response_code=201,
            message=f"Incident {incident_id} created: {params.get('target', 'unspecified')}",
        )
