"""OTE SIEM plugin — stub adapter for block_ip and query_logs actions."""
from __future__ import annotations

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
        return ["block_ip", "query_logs"]

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
        else:
            return ActionResult(
                action=action,
                plugin=self.plugin_name,
                success=False,
                latency_ms=5,
                response_code=400,
                message=f"Unsupported action: {action}",
            )
