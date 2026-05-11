"""OTE IDS plugin — stub adapter for notify_soc action."""
from __future__ import annotations

from vigilance.components.c4_adapters.base import ToolAdapter
from vigilance.models.execution_result import ActionResult


class IDSPlugin(ToolAdapter):
    """Stub IDS adapter for OTE (Telecom) pilot.

    Simulates SOC notification with realistic latencies (180-200ms).
    """

    @property
    def plugin_name(self) -> str:
        return "ote_ids"

    @property
    def supported_actions(self) -> list[str]:
        return ["notify_soc"]

    def execute(self, action: str, params: dict) -> ActionResult:
        if action == "notify_soc":
            return ActionResult(
                action=action,
                plugin=self.plugin_name,
                success=True,
                latency_ms=192,
                response_code=200,
                message="SOC notification sent: ticket SOCT-2026-0031 created",
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
