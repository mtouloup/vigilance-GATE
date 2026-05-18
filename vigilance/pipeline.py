"""T53Pipeline — ties all components together into a unified processing pipeline.

T5.3 is a single multi-pilot agentic wrapper that serves all four VIGILANCE
GA pilots simultaneously (TELECOM, MARITIME, FINANCE, INDUSTRY_4). At startup
all sector profiles and all C4 adapter sets are loaded. Each event is routed
to the correct profile and adapters based on the pilot detected by C1 parsers.
"""
from __future__ import annotations
import logging
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

logger = logging.getLogger(__name__)

TOPIC_CANONICAL_EVENTS = "t53.canonical_events"
TOPIC_ACTION_REQUESTS  = "t53.action_requests"
TOPIC_RESULTS          = "t53.results"

# Pilot value used when no sector can be detected from the event content
_UNKNOWN_PILOT = "UNKNOWN"
# Sector used as last-resort fallback when pilot remains UNKNOWN after C1
_FALLBACK_SECTOR = "TELECOM"


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


_ADAPTER_BUILDERS = {
    "TELECOM":    _build_telecom_adapters,
    "INDUSTRY_4": _build_industry4_adapters,
    "MARITIME":   _build_maritime_adapters,
    "FINANCE":    _build_finance_adapters,
}


class T53Pipeline:
    """Main processing pipeline that orchestrates all T5.3 components.

    Supports all four GA pilots in a single instance. Pilot detection happens
    in C1 (parsers + LLM fallback). C2, C5, C3+C4 are then executed with the
    profile and adapters that correspond to the detected pilot.

    STANDALONE mode (default):
      pilot.events.raw → C1 → C2 → C5 → C3+C4 → t53.results

    INTEGRATED mode (VIGILANCE_MODE=INTEGRATED):
      pilot.events.raw → C1 → t53.canonical_events  (T5.4 takes over)
      t53.action_requests  → C5 → C3+C4 → t53.results
    """

    def __init__(
        self,
        sector: str | None = None,
        simulation_mode: bool = False,
        dry_run: bool = False,
        mode: str = "STANDALONE",
    ) -> None:
        self._mode = mode.upper()

        # C6 — load ALL sector profiles at startup
        self._profiles: dict[str, SectorProfile] = ProfileManager.load_all_profiles()

        # LLM
        self._llm = create_llm()

        # C1
        self._normalizer = Normalizer(self._llm)

        # C2
        self._agent = AgentLoop()

        # C3
        self._policy_translator = PolicyTranslator(self._llm)
        self._executor = ActionExecutor(self._policy_translator)

        # C4 — build adapter sets for ALL sectors at startup
        self._all_adapters: dict[str, dict[str, ToolAdapter]] = {
            sector_key: builder()
            for sector_key, builder in _ADAPTER_BUILDERS.items()
        }

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

        sectors_loaded = list(self._profiles.keys())
        print(
            f"[T53Pipeline] Initialized: pilots={sectors_loaded} "
            f"mode={self._mode} simulation={self._simulation}"
        )

    # ── Profile + adapter lookup per event ────────────────────────────────────

    def _profile_for(self, pilot: str) -> SectorProfile:
        """Return the SectorProfile for the given pilot/sector.

        Falls back to TELECOM with a warning if pilot is UNKNOWN or unrecognised.
        """
        profile = self._profiles.get(pilot)
        if profile is None:
            logger.warning(
                f"Pilot '{pilot}' has no registered profile — "
                f"falling back to {_FALLBACK_SECTOR}. "
                "Improve C1 extraction or add a profile for this sector."
            )
            profile = self._profiles[_FALLBACK_SECTOR]
        return profile

    def _adapters_for(self, sector: str) -> dict[str, ToolAdapter]:
        return self._all_adapters.get(sector, self._all_adapters[_FALLBACK_SECTOR])

    # ── Entry point ───────────────────────────────────────────────────────────

    def process_event(self, raw_event: str | dict) -> ExecutionResult:
        """Process a raw event — routes to standalone or integrated mode."""
        if self._mode == "INTEGRATED":
            self.ingest_event(raw_event)
            return None
        return self._run_standalone(raw_event)

    # ── STANDALONE: full internal pipeline ────────────────────────────────────

    def _run_standalone(self, raw_event: str | dict) -> ExecutionResult:
        """STANDALONE full pipeline: C1 → C2 → C5 → C3+C4 → publish result."""
        print("[T53Pipeline] C1: Normalizing event...")
        event = self._normalizer.normalize(raw_event)
        profile = self._profile_for(event.pilot)

        # Apply sector-specific enrichments (e.g. INDUSTRY_4 OT safety flag)
        event = self._normalizer.normalize(raw_event, sector_profile=profile) \
            if event.pilot != _UNKNOWN_PILOT else event

        print(
            f"[T53Pipeline] C1 → event_id={event.event_id} "
            f"type={event.type} severity={event.severity} pilot={event.pilot}"
        )

        self._broker.publish(TOPIC_CANONICAL_EVENTS, event.model_dump(mode="json"))

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

        return self._guardrail_and_execute(request, event, profile)

    # ── INTEGRATED: C1 ingestion half ─────────────────────────────────────────

    def ingest_event(self, raw_event: str | dict) -> CanonicalEvent:
        """INTEGRATED mode — C1 only: normalize, cache, and publish CanonicalEvent."""
        print("[T53Pipeline][INTEGRATED] C1: Normalizing event...")
        event = self._normalizer.normalize(raw_event)

        # Apply sector-specific profile enrichments once pilot is known
        profile = self._profile_for(event.pilot)
        event = self._normalizer._enrich_with_profile(event, profile)

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
        """INTEGRATED mode — receives ActionRequest dispatched by T5.4."""
        request = ActionRequest(**action_request_dict)
        print(
            f"[T53Pipeline][INTEGRATED] ActionRequest received from T5.4: "
            f"event_id={request.event_id} actions={request.actions} "
            f"confidence={request.agent_confidence:.2f}"
        )

        event = self._event_cache.get(request.event_id)
        if event is None:
            event = CanonicalEvent(
                event_id=request.event_id,
                type="UNKNOWN",
                pilot=request.pilot,
                severity="HIGH",
                timestamp=datetime.now(timezone.utc),
            )
            logger.warning(
                f"event_id={request.event_id} not in cache — using minimal CanonicalEvent"
            )

        # Select profile based on the event's detected pilot
        profile = self._profile_for(event.pilot)
        return self._guardrail_and_execute(request, event, profile)

    # ── Shared: guardrail + execution ─────────────────────────────────────────

    def _guardrail_and_execute(
        self,
        request: ActionRequest,
        event: CanonicalEvent,
        profile: SectorProfile,
    ) -> ExecutionResult:
        adapters = self._adapters_for(profile.sector)

        audit_id = self._audit.open_record(
            pilot_id=profile.pilot,
            event_id=event.event_id,
            request_id=request.request_id,
        )
        print(f"[T53Pipeline] C5: Audit record opened: {audit_id}")

        print("[T53Pipeline] C5: Running guardrail checks...")
        guardrail = self._guardrail.check(request, event, profile, self._llm)
        print(
            f"[T53Pipeline] C5 → verdict={guardrail.verdict.value} "
            f"ot_safety_checked={guardrail.ot_safety_checked} "
            f"reasons={guardrail.reasons}"
        )

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
            result = self._executor.execute(request, profile, adapters)

        print(
            f"[T53Pipeline] C3+C4 → overall_success={result.overall_success} "
            f"actions={[r.action for r in result.action_results]}"
        )

        self._audit.close_record(audit_id, result, guardrail)
        print(f"[T53Pipeline] C5: Audit record closed: {audit_id}")

        self._broker.publish(TOPIC_RESULTS, result.model_dump(mode="json"))
        return result

    def _dry_run_result(self, request, event, profile) -> ExecutionResult:
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
        return self._audit

    @property
    def broker(self) -> BaseBroker:
        return self._broker

    @property
    def profiles(self) -> dict[str, SectorProfile]:
        """All loaded sector profiles keyed by sector name."""
        return self._profiles
