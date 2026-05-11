"""OT IAM plugin — stub adapter for Siemens Industry 4.0 pilot."""
from __future__ import annotations

from vigilance.components.c4_adapters.base import ToolAdapter
from vigilance.models.execution_result import ActionResult


class IAMPlugin(ToolAdapter):
    """Stub OT IAM adapter for Siemens (Industry 4.0) pilot.

    Simulates HTTP calls with realistic latencies (60-80ms).
    """

    @property
    def plugin_name(self) -> str:
        return "ot_iam"

    @property
    def supported_actions(self) -> list[str]:
        return ["revoke_ot_session", "query_sessions"]

    def execute(self, action: str, params: dict) -> ActionResult:
        if action == "revoke_ot_session":
            return ActionResult(
                action=action,
                plugin=self.plugin_name,
                success=True,
                latency_ms=71,
                response_code=200,
                message="OT session credentials revoked for PLC zone access",
            )
        elif action == "query_sessions":
            return ActionResult(
                action=action,
                plugin=self.plugin_name,
                success=True,
                latency_ms=65,
                response_code=200,
                message="OT IAM session query completed",
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
