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
from vigilance.llm import create_llm
from vigilance.models.action_request import ActionRequest
from vigilance.models.canonical_event import CanonicalEvent
from vigilance.models.execution_result import ActionResult, ExecutionResult
from vigilance.models.guardrail_check import GuardrailVerdict

TOPIC_CANONICAL_EVENTS = "t53.canonical_events"
TOPIC_ACTION_REQUESTS  = "t53.action_requests"
TOPIC_RESULTS          = "t53.results"


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


def _build_maritime_adapters() -> dict[str, ToolAdapter]:
    from vigilance.components.c4_adapters.maritime.siem_plugin import PortSIEMPlugin
    from vigilance.components.c4_adapters.maritime.iam_plugin import PortIAMPlugin
    from vigilance.components.c4_adapters.maritime.port_ops_plugin import PortOpsPlugin

    plugins = [PortSIEMPlugin(), PortIAMPlugin(), PortOpsPlugin()]
    return {p.plugin_name: p for p in plugins}


def _build_finance_adapters() -> dict[str, ToolAdapter]:
    from vigilance.components.c4_adapters.finance.siem_plugin import BankSIEMPlugin
    from vigilance.components.c4_adapters.finance.iam_plugin import BankIAMPlugin
    from vigilance.components.c4_adapters.finance.fraud_engine_plugin import FraudEnginePlugin

    plugins = [BankSIEMPlugin(), BankIAMPlugin(), FraudEnginePlugin()]
    return {p.plugin_name: p for p in plugins}


class T53Pipeline:
    """Main processing pipeline that orchestrates all T5.3 components.

    STANDALONE mode (default):
      pilot.events.raw → C1 → C2 → C5 → C3+C4 → t53.results
      Also publishes CanonicalEvent to t53.canonical_events for observability.

    INTEGRATED mode (VIGILANCE_MODE=INTEGRATED):
      pilot.events.raw → C1 → t53.canonical_events  (T5.4 takes over)
      t53.action_requests  → C5 → C3+C4 → t53.results  (T5.4 dispatches back)
    """

    def __init__(
        self,
        sector: str | None = None,
        simulation_mode: bool = False,
        dry_run: bool = False,
        mode: str = "STANDALONE",
    ) -> None:
        self._mode = mode.upper()

        # C6 — load profile
        self._profile_manager = ProfileManager(sector=sector)
        self._profile: SectorProfile = self._profile_manager.load()

        # LLM
        self._llm = create_llm()

        # C1
        self._normalizer = Normalizer(self._llm)

        # C2 (used in STANDALONE only)
        self._agent = AgentLoop()

        # C3
        self._policy_translator = PolicyTranslator(self._llm)
        self._executor = ActionExecutor(self._policy_translator)

        # C4 — select adapters based on sector
        _adapter_builders = {
            "INDUSTRY_4": _build_industry4_adapters,
            "MARITIME": _build_maritime_adapters,
            "FINANCE": _build_finance_adapters,
        }
        builder = _adapter_builders.get(self._profile.sector, _build_telecom_adapters)
        self._adapters = builder()

        # Event cache for INTEGRATED mode: event_id → CanonicalEvent
        self._event_cache: dict[str, CanonicalEvent] = {}

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
            f"mode={self._mode} "
            f"simulation={self._simulation}"
        )

    def process_event(self, raw_event: str | dict) -> ExecutionResult:
        """Process a raw event — routes to standalone or integrated mode.

        In STANDALONE mode runs the full C1→C2→C5→C3→C4 pipeline.
        In INTEGRATED mode runs C1 only and publishes CanonicalEvent for T5.4.
        """
        if self._mode == "INTEGRATED":
            self.ingest_event(raw_event)
            return None  # T5.4 will dispatch the ActionRequest separately
        return self._run_standalone(raw_event)

    # ── STANDALONE: full internal pipeline ────────────────────────────────────

    def _run_standalone(self, raw_event: str | dict) -> ExecutionResult:
        """STANDALONE full pipeline: C1 → C2 → C5 → C3+C4 → publish result."""
        profile = self._profile

        # --- C1: Normalize ---
        print("[T53Pipeline] C1: Normalizing event...")
        event = self._normalizer.normalize(raw_event, profile)
        print(
            f"[T53Pipeline] C1 → event_id={event.event_id} "
            f"type={event.type} severity={event.severity} pilot={event.pilot}"
        )

        # Publish CanonicalEvent for observability (T5.4 can subscribe even in STANDALONE)
        self._broker.publish(TOPIC_CANONICAL_EVENTS, event.model_dump(mode="json"))

        # --- C2: Agentic reasoning ---
        print("[T53Pipeline] C2: Running agentic loop...")
        decision = self._agent.run(event, profile, self._llm)
        print(
            f"[T53Pipeline] C2 → threat={decision.threat_type} "
            f"confidence={decision.confidence:.2f} turns={decision.reasoning_turns} "
            f"actions={decision.recommended_actions}"
        )

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

        return self._guardrail_and_execute(request, event)

    # ── INTEGRATED: C1 ingestion half ─────────────────────────────────────────

    def ingest_event(self, raw_event: str | dict) -> CanonicalEvent:
        """INTEGRATED mode — C1 only.

        Normalises the raw event, caches it by event_id, and publishes the
        CanonicalEvent to t53.canonical_events for T5.4 to consume.
        T5.4 will call T5.1 (RAG) and T5.2 (agent catalogue), then dispatch
        an ActionRequest back to t53.action_requests.
        """
        profile = self._profile
        print("[T53Pipeline][INTEGRATED] C1: Normalizing event...")
        event = self._normalizer.normalize(raw_event, profile)
        print(
            f"[T53Pipeline][INTEGRATED] C1 → event_id={event.event_id} "
            f"type={event.type} severity={event.severity} pilot={event.pilot}"
        )

        self._event_cache[event.event_id] = event
        self._broker.publish(TOPIC_CANONICAL_EVENTS, event.model_dump(mode="json"))
        print(
            f"[T53Pipeline][INTEGRATED] CanonicalEvent published → "
            f"{TOPIC_CANONICAL_EVENTS} (awaiting ActionRequest from T5.4)"
        )
        return event

    # ── INTEGRATED: C5+C3+C4 execution half ───────────────────────────────────

    def execute_action_request(self, action_request_dict: dict) -> ExecutionResult:
        """INTEGRATED mode — receives ActionRequest dispatched by T5.4.

        Looks up the original CanonicalEvent from the cache (by event_id),
        runs the C5 guardrail, executes via C3+C4, and publishes the
        ExecutionResult to t53.results.
        """
        request = ActionRequest(**action_request_dict)
        print(
            f"[T53Pipeline][INTEGRATED] ActionRequest received from T5.4: "
            f"event_id={request.event_id} actions={request.actions} "
            f"confidence={request.agent_confidence:.2f}"
        )

        # Retrieve the CanonicalEvent stored during ingest_event()
        event = self._event_cache.get(request.event_id)
        if event is None:
            # Fallback: reconstruct a minimal CanonicalEvent from the request
            from datetime import timezone
            event = CanonicalEvent(
                event_id=request.event_id,
                type="UNKNOWN",
                pilot=request.pilot,
                severity="HIGH",
                timestamp=datetime.now(timezone.utc),
            )
            print(
                f"[T53Pipeline][INTEGRATED] WARNING: event_id={request.event_id} "
                "not in cache — using minimal CanonicalEvent"
            )

        return self._guardrail_and_execute(request, event)

    # ── Shared: guardrail + execution (used by both modes) ────────────────────

    def _guardrail_and_execute(
        self,
        request: ActionRequest,
        event: CanonicalEvent,
    ) -> ExecutionResult:
        profile = self._profile

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

        self._audit.close_record(audit_id, result, guardrail)
        print(f"[T53Pipeline] C5: Audit record closed: {audit_id}")

        self._broker.publish(TOPIC_RESULTS, result.model_dump(mode="json"))
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
