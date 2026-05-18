"""C3 Action & Policy Execution — dispatches ActionRequests via C4 adapters."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone

from vigilance.components.c3_execution.policy_translator import PolicyTranslator
from vigilance.models.action_request import ActionRequest
from vigilance.models.execution_result import ActionResult, ExecutionResult


class ActionExecutor:
    """Execute ActionRequests by dispatching to the appropriate C4 adapter plugins.

    For each action in the request, the executor looks up the adapter that
    supports that action and calls it. If a policy_update NL description is
    present, it translates it to OPA/Rego via PolicyTranslator.
    """

    def __init__(self, policy_translator: PolicyTranslator | None = None) -> None:
        self._policy_translator = policy_translator

    def execute(
        self,
        request: ActionRequest,
        profile,
        adapters: dict,  # dict[str, ToolAdapter]
    ) -> ExecutionResult:
        """Execute an ActionRequest using the provided adapters.

        Args:
            request: The ActionRequest with actions to execute.
            profile: SectorProfile for context.
            adapters: Mapping of plugin_name → ToolAdapter instance.

        Returns:
            ExecutionResult with per-action results.
        """
        action_results: list[ActionResult] = []

        # Translate policy update if present (uses the LLM injected at construction)
        if request.policy_update and self._policy_translator:
            rego = self._policy_translator.translate(request.policy_update)
            print(f"[C3] Translated policy to Rego ({len(rego)} chars)")

        for action in request.actions:
            adapter = self._find_adapter(action, adapters)
            if adapter is None:
                action_results.append(
                    ActionResult(
                        action=action,
                        plugin="none",
                        success=False,
                        latency_ms=0,
                        response_code=404,
                        message=f"No adapter found for action '{action}'",
                    )
                )
                continue

            # Build params for the action
            params = self._build_params(action, request)
            result = adapter.execute(action, params)
            action_results.append(result)
            print(
                f"[C3] {action} → {adapter.plugin_name}: "
                f"{'OK' if result.success else 'FAIL'} ({result.latency_ms}ms)"
            )

        overall_success = all(r.success for r in action_results)

        return ExecutionResult(
            request_id=request.request_id,
            event_id=request.event_id,
            pilot=request.pilot,
            action_results=action_results,
            overall_success=overall_success,
            timestamp=datetime.now(timezone.utc),
        )

    def _find_adapter(self, action: str, adapters: dict):
        """Find the first adapter that supports the given action."""
        for adapter in adapters.values():
            if action in adapter.supported_actions:
                return adapter
        return None

    def _build_params(self, action: str, request: ActionRequest) -> dict:
        """Build action-specific parameters from the ActionRequest."""
        params: dict = {
            "event_id": request.event_id,
            "pilot": request.pilot,
        }
        # For isolate_plc, always pass safe-state mode
        if action == "isolate_plc":
            params["mode"] = "safe-state"
        return params
