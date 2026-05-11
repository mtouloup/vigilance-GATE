"""SCADA OPC-UA plugin — stub adapter for Siemens Industry 4.0 pilot."""
from __future__ import annotations

from vigilance.components.c4_adapters.base import ToolAdapter
from vigilance.models.execution_result import ActionResult


class SCADAPlugin(ToolAdapter):
    """Stub SCADA/OPC-UA adapter for Siemens (Industry 4.0) pilot.

    The isolate_plc action ENFORCES safe-state mode — it raises ValueError
    if params do not include mode="safe-state".

    Stub response latencies:
    - isolate_plc: ~50ms
    - notify_soc: ~50ms
    - update_zt_policy: ~90ms
    """

    @property
    def plugin_name(self) -> str:
        return "scada_opcua"

    @property
    def supported_actions(self) -> list[str]:
        return ["isolate_plc", "notify_soc", "update_zt_policy"]

    def execute(self, action: str, params: dict) -> ActionResult:
        if action == "isolate_plc":
            return self._isolate_plc(params)
        elif action == "notify_soc":
            return self._notify_soc(params)
        elif action == "update_zt_policy":
            return self._update_zt_policy(params)
        else:
            return ActionResult(
                action=action,
                plugin=self.plugin_name,
                success=False,
                latency_ms=5,
                response_code=400,
                message=f"Unsupported action: {action}",
            )

    def _isolate_plc(self, params: dict) -> ActionResult:
        """Isolate a PLC — MUST use safe-state mode."""
        mode = params.get("mode")
        if mode != "safe-state":
            raise ValueError(
                f"isolate_plc requires mode='safe-state', got mode={mode!r}. "
                "OT safety enforcement: refusing to execute without safe-state."
            )
        plc_ref = params.get("plc_id", params.get("event_id", "unknown"))
        return ActionResult(
            action="isolate_plc",
            plugin=self.plugin_name,
            success=True,
            latency_ms=53,
            response_code=200,
            message=f"PLC {plc_ref} isolated via OPC-UA safe-state command (ACK received)",
        )

    def _notify_soc(self, params: dict) -> ActionResult:
        return ActionResult(
            action="notify_soc",
            plugin=self.plugin_name,
            success=True,
            latency_ms=48,
            response_code=200,
            message="OT SOC notification sent: ticket SOCT-2026-SIE-0074 created",
        )

    def _update_zt_policy(self, params: dict) -> ActionResult:
        return ActionResult(
            action="update_zt_policy",
            plugin=self.plugin_name,
            success=True,
            latency_ms=92,
            response_code=200,
            message="Zero-trust policy updated: IT/OT boundary rules applied for affected zone",
        )
