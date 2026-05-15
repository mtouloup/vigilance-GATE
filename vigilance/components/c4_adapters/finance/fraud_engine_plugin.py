"""Fraud Engine plugin — stub adapter for CaixaBank (Finance) pilot."""
from __future__ import annotations

from vigilance.components.c4_adapters.base import ToolAdapter
from vigilance.models.execution_result import ActionResult


class FraudEnginePlugin(ToolAdapter):
    """Stub Fraud Engine adapter for CaixaBank (Finance) pilot.

    Covers fraud response actions: transaction blocking, fraud team
    notification, compliance escalation, payment channel restrictions.
    """

    @property
    def plugin_name(self) -> str:
        return "fraud_engine"

    @property
    def supported_actions(self) -> list[str]:
        return [
            "block_transaction",
            "notify_fraud_team",
            "escalate_to_compliance",
            "notify_soc",
        ]

    def execute(self, action: str, params: dict) -> ActionResult:
        if action == "block_transaction":
            txn = params.get("transaction_id", params.get("event_id", "unknown"))
            return ActionResult(
                action=action,
                plugin=self.plugin_name,
                success=True,
                latency_ms=22,
                response_code=200,
                message=f"Transaction {txn} blocked by fraud engine (real-time intercept)",
            )
        elif action == "notify_fraud_team":
            return ActionResult(
                action=action,
                plugin=self.plugin_name,
                success=True,
                latency_ms=165,
                response_code=200,
                message="Fraud team notified: case FRAUD-2026-0001 opened for investigation",
            )
        elif action == "escalate_to_compliance":
            return ActionResult(
                action=action,
                plugin=self.plugin_name,
                success=True,
                latency_ms=201,
                response_code=200,
                message="Escalated to compliance: DORA/PSD2 incident report COMP-2026-0001 filed",
            )
        elif action == "notify_soc":
            return ActionResult(
                action=action,
                plugin=self.plugin_name,
                success=True,
                latency_ms=183,
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
