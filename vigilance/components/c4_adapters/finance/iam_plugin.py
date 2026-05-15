"""Bank IAM plugin — stub adapter for CaixaBank (Finance) pilot."""
from __future__ import annotations

from vigilance.components.c4_adapters.base import ToolAdapter
from vigilance.models.execution_result import ActionResult


class BankIAMPlugin(ToolAdapter):
    """Stub IAM adapter for CaixaBank (Finance) pilot.

    Manages customer and employee accounts: session revocation, account
    freezing, multi-factor enforcement.
    """

    @property
    def plugin_name(self) -> str:
        return "bank_iam"

    @property
    def supported_actions(self) -> list[str]:
        return ["freeze_account", "revoke_session", "query_sessions"]

    def execute(self, action: str, params: dict) -> ActionResult:
        if action == "freeze_account":
            account = params.get("account_id", params.get("event_id", "unknown"))
            return ActionResult(
                action=action,
                plugin=self.plugin_name,
                success=True,
                latency_ms=56,
                response_code=200,
                message=f"Account frozen via Bank IAM: {account} — all activity suspended",
            )
        elif action == "revoke_session":
            return ActionResult(
                action=action,
                plugin=self.plugin_name,
                success=True,
                latency_ms=63,
                response_code=200,
                message="Bank IAM sessions revoked: all active tokens invalidated",
            )
        elif action == "query_sessions":
            return ActionResult(
                action=action,
                plugin=self.plugin_name,
                success=True,
                latency_ms=48,
                response_code=200,
                message="Bank IAM session query completed: 5 active sessions found",
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
