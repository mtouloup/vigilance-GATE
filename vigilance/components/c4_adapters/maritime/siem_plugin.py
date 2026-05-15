"""Port SIEM plugin — stub adapter for Port of Rotterdam (Maritime) pilot."""
from __future__ import annotations

from vigilance.components.c4_adapters.base import ToolAdapter
from vigilance.models.execution_result import ActionResult


class PortSIEMPlugin(ToolAdapter):
    """Stub SIEM adapter for Port of Rotterdam (Maritime) pilot.

    Covers port IT/OT SIEM: AIS anomaly alerts, vessel access events,
    cargo system intrusion detections.
    """

    @property
    def plugin_name(self) -> str:
        return "port_siem"

    @property
    def supported_actions(self) -> list[str]:
        return ["block_vessel_access", "query_logs", "update_vessel_acl"]

    def execute(self, action: str, params: dict) -> ActionResult:
        if action == "block_vessel_access":
            vessel = params.get("vessel_id", params.get("event_id", "unknown"))
            return ActionResult(
                action=action,
                plugin=self.plugin_name,
                success=True,
                latency_ms=42,
                response_code=200,
                message=f"Vessel access blocked in port SIEM: {vessel}",
            )
        elif action == "query_logs":
            return ActionResult(
                action=action,
                plugin=self.plugin_name,
                success=True,
                latency_ms=51,
                response_code=200,
                message="Port SIEM log query completed: 183 events retrieved",
            )
        elif action == "update_vessel_acl":
            return ActionResult(
                action=action,
                plugin=self.plugin_name,
                success=True,
                latency_ms=38,
                response_code=200,
                message="Vessel ACL updated: access restrictions applied",
            )
        else:
            return ActionResult(
                action=action,
                plugin=self.plugin_name,
                success=False,
                latency_ms=5,
                response_code=400,
                message=f"Unsupported action: {action}",
            )
