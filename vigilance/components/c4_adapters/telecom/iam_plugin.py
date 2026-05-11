"""OTE IAM plugin — stub adapter for revoke_session and query_sessions actions."""
from __future__ import annotations

from vigilance.components.c4_adapters.base import ToolAdapter
from vigilance.models.execution_result import ActionResult


class IAMPlugin(ToolAdapter):
    """Stub IAM adapter for OTE (Telecom) pilot.

    Simulates HTTP calls with realistic latencies (60-80ms).
    """

    @property
    def plugin_name(self) -> str:
        return "ote_iam"

    @property
    def supported_actions(self) -> list[str]:
        return ["revoke_session", "query_sessions"]

    def execute(self, action: str, params: dict) -> ActionResult:
        if action == "revoke_session":
            return ActionResult(
                action=action,
                plugin=self.plugin_name,
                success=True,
                latency_ms=67,
                response_code=200,
                message="Active sessions revoked: sess-0042, sess-0043",
            )
        elif action == "query_sessions":
            return ActionResult(
                action=action,
                plugin=self.plugin_name,
                success=True,
                latency_ms=72,
                response_code=200,
                message="IAM session query completed: 12 active sessions found",
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
