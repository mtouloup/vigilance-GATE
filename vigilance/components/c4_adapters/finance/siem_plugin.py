"""Bank SIEM plugin — stub adapter for CaixaBank (Finance) pilot."""
from __future__ import annotations

from vigilance.components.c4_adapters.base import ToolAdapter
from vigilance.models.execution_result import ActionResult


class BankSIEMPlugin(ToolAdapter):
    """Stub SIEM adapter for CaixaBank (Finance) pilot.

    Covers banking security events: authentication anomalies, fraud
    signal correlation, insider threat indicators.
    """

    @property
    def plugin_name(self) -> str:
        return "bank_siem"

    @property
    def supported_actions(self) -> list[str]:
        return ["query_logs", "block_transaction", "notify_soc"]

    def execute(self, action: str, params: dict) -> ActionResult:
        if action == "query_logs":
            return ActionResult(
                action=action,
                plugin=self.plugin_name,
                success=True,
                latency_ms=44,
                response_code=200,
                message="Bank SIEM log query completed: 312 events retrieved",
            )
        elif action == "block_transaction":
            txn = params.get("transaction_id", params.get("event_id", "unknown"))
            return ActionResult(
                action=action,
                plugin=self.plugin_name,
                success=True,
                latency_ms=29,
                response_code=200,
                message=f"Transaction blocked in bank SIEM: {txn}",
            )
        elif action == "notify_soc":
            return ActionResult(
                action=action,
                plugin=self.plugin_name,
                success=True,
                latency_ms=178,
                response_code=200,
                message="Bank SOC notification sent: ticket BSOC-2026-0001 created",
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
