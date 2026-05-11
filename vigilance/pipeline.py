"""T53Pipeline — ties all components together into a unified processing pipeline."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone

from vigilance.broker import BaseBroker, create_broker
from vigilance.components.c1_ingestion.normalizer import Normalizer
from vigilance.components.c2_agentic.agent import AgentLoop
from vigilance.components.c3_execution.executor import ActionExecutor
from vigilance.components.c3_execution.policy_translator import PolicyTranslator
from vigilance.components.c4_adapters.base import ToolAdapter
from vigilance.components.c5_safety.audit import AuditLog
from vigilance.components.c5_safety.guardrail import SafetyGate
from vigilance.components.c5_safety.simulation import SimulationMode
from vigilance.components.c6_profiles.profile_manager import ProfileManager, SectorProfile
from vigilance.llm.base import StubLLMProvider
from vigilance.models.action_request import ActionRequest
from vigilance.models.execution_result import ActionResult, ExecutionResult
from vigilance.models.guardrail_check import GuardrailVerdict


def _build_telecom_adapters() -> dict[str, ToolAdapter]:
    from vigilance.components.c4_adapters.telecom.siem_plugin import SIEMPlugin
    from vigilance.components.c4_adapters.telecom.iam_plugin import IAMPlugin
    from vigilance.components.c4_adapters.telecom.ids_plugin import IDSPlugin

    plugins = [SIEMPlugin(), IAMPlugin(), IDSPlugin()]
    return {p.plugin_name: p for p in plugins}


def _build_industry4_adapters() -> dict[str, ToolAdapter]:
    from vigilance.components.c4_adapters.industry4.siem_plugin import SIEMPlugin as IndSIEM
    from vigilance.components.c4_adapters.industry4.iam_plugin import IAMPlugin as OTIAM
    from vigilance.components.c4_adapters.industry4.scada_plugin import SCADAPlugin

    plugins = [IndSIEM(), OTIAM(), SCADAPlugin()]
    return {p.plugin_name: p for p in plugins}


class T53Pipeline:
    """Main processing pipeline that orchestrates all T5.3 components.

    Flow:
    1. C6: Load sector profile
    2. C1: Normalize raw event → CanonicalEvent
    3. C2: Agentic reasoning → AgentDecision
    4. C5: Guardrail check → GuardrailCheck
    5. C3+C4: Execute actions → ExecutionResult (if APPROVED/ESCALATE w/ human approval)
    6. C5: Close audit record
    7. Broker: Publish result to t53.results
    """

    def __init__(
        self,
        sector: str | None = None,
        simulation_mode: bool = False,
        dry_run: bool = False,
    ) -> None:
        # C6 — load profile
        self._profile_manager = ProfileManager(sector=sector)
        self._profile: SectorProfile = self._profile_manager.load()

        # LLM
        self._llm = StubLLMProvider()

        # C1
        self._normalizer = Normalizer(self._llm)

        # C2
        self._agent = AgentLoop()

        # C3
        self._policy_translator = PolicyTranslator(self._llm)
        self._executor = ActionExecutor(self._policy_translator)

        # C4 — select adapters based on sector
        if self._profile.sector == "INDUSTRY_4":
            self._adapters = _build_industry4_adapters()
        else:
            self._adapters = _build_telecom_adapters()

        # C5
        self._guardrail = SafetyGate()
        self._audit = AuditLog()
        self._simulation = SimulationMode(
            dry_run=dry_run or simulation_mode,
            digital_twin=simulation_mode,
        )

        # Broker
        self._broker = create_broker()

        print(
            f"[T53Pipeline] Initialized: sector={self._profile.sector} "
            f"pilot={self._profile.pilot} "
            f"simulation={self._simulation}"
        )

    def process_event(self, raw_event: str | dict) -> ExecutionResult:
        """Process a raw event through the full T5.3 pipeline.

        Args:
            raw_event: Raw event string (CEF, syslog) or dict (ECS, OT JSON).

        Returns:
            ExecutionResult with all action outcomes.
        """
        profile = self._profile

        # Publish raw event to broker
        self._broker.publish("pilot.events.raw", {"raw": str(raw_event)[:500]})

        # --- C1: Normalize ---
        print("[T53Pipeline] C1: Normalizing event...")
        event = self._normalizer.normalize(raw_event, profile)
        print(
            f"[T53Pipeline] C1 → event_id={event.event_id} "
            f"type={event.type} severity={event.severity} pilot={event.pilot}"
        )

        # --- C2: Agentic reasoning ---
        print("[T53Pipeline] C2: Running agentic loop...")
        decision = self._agent.run(event, profile, self._llm)
        print(
            f"[T53Pipeline] C2 → threat={decision.threat_type} "
            f"confidence={decision.confidence:.2f} turns={decision.reasoning_turns} "
            f"actions={decision.recommended_actions}"
        )

        # Build ActionRequest
        request = ActionRequest(
            request_id=str(uuid.uuid4()),
            event_id=event.event_id,
            pilot=profile.pilot,
            actions=decision.recommended_actions,
            policy_update=(
                f"Block {event.src_ip} and apply zero-trust policy for {event.type}"
                if event.src_ip else None
            ),
            agent_confidence=decision.confidence,
        )

        # Open audit record
        audit_id = self._audit.open_record(
            pilot_id=profile.pilot,
            event_id=event.event_id,
            request_id=request.request_id,
        )
        print(f"[T53Pipeline] C5: Audit record opened: {audit_id}")

        # --- C5: Guardrail check ---
        print("[T53Pipeline] C5: Running guardrail checks...")
        guardrail = self._guardrail.check(request, event, profile, self._llm)
        print(
            f"[T53Pipeline] C5 → verdict={guardrail.verdict.value} "
            f"ot_safety_checked={guardrail.ot_safety_checked} "
            f"reasons={guardrail.reasons}"
        )

        # --- C3+C4: Execute ---
        if guardrail.verdict == GuardrailVerdict.REJECTED:
            print("[T53Pipeline] C5: REJECTED — skipping execution")
            # Return a no-op result
            result = ExecutionResult(
                request_id=request.request_id,
                event_id=event.event_id,
                pilot=profile.pilot,
                action_results=[
                    ActionResult(
                        action="REJECTED",
                        plugin="guardrail",
                        success=False,
                        latency_ms=0,
                        response_code=403,
                        message=f"Guardrail REJECTED: {'; '.join(guardrail.reasons)}",
                    )
                ],
                overall_success=False,
                timestamp=datetime.now(timezone.utc),
            )
        elif self._simulation.dry_run:
            print("[T53Pipeline] Dry-run mode: logging actions without executing")
            result = self._dry_run_result(request, event, profile)
        else:
            print(f"[T53Pipeline] C3+C4: Executing {len(request.actions)} actions...")
            result = self._executor.execute(request, profile, self._adapters)

        print(
            f"[T53Pipeline] C3+C4 → overall_success={result.overall_success} "
            f"actions={[r.action for r in result.action_results]}"
        )

        # --- C5: Close audit ---
        self._audit.close_record(audit_id, result, guardrail)
        print(f"[T53Pipeline] C5: Audit record closed: {audit_id}")

        # Publish result
        self._broker.publish("t53.results", result.model_dump(mode="json"))

        return result

    def _dry_run_result(
        self,
        request: ActionRequest,
        event,
        profile,
    ) -> ExecutionResult:
        """Produce a dry-run execution result (no real execution)."""
        action_results = [
            ActionResult(
                action=action,
                plugin="dry_run",
                success=True,
                latency_ms=0,
                response_code=200,
                message=f"[DRY-RUN] Would execute: {action}",
            )
            for action in request.actions
        ]
        return ExecutionResult(
            request_id=request.request_id,
            event_id=event.event_id,
            pilot=profile.pilot,
            action_results=action_results,
            overall_success=True,
            timestamp=datetime.now(timezone.utc),
        )

    @property
    def audit_log(self) -> AuditLog:
        """Access the audit log for inspection."""
        return self._audit

    @property
    def broker(self) -> BaseBroker:
        """Access the message broker for inspection."""
        return self._broker

    @property
    def profile(self) -> SectorProfile:
        """Access the loaded sector profile."""
        return self._profile
