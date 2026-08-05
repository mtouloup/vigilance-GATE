"""T53Pipeline — ties all components together into a unified processing pipeline.

T5.3 operates exclusively in INTEGRATED mode as part of the wider WP5 workflow:

  Ingest half:   pilot.events.raw → C1 normalize → t53.canonical_events → T5.4
  Execute half:  t53.action_requests (from T5.4) → C5 guardrail → C3 policy
                 → t53.policy_updates (T5.5) + t53.actions.dispatch (pilot tools)
                 → t53.results

T5.4 owns the agentic reasoning and agent selection (T5.2). T5.3 owns
normalization, safety, policy translation, and dispatch.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone

from vigilance.broker import BaseBroker, create_broker
from vigilance.components.c1_ingestion.normalizer import Normalizer
from vigilance.components.c3_execution.policy_translator import PolicyTranslator
from vigilance.workflow_logger import WorkflowCSVLogger
from vigilance.components.c4_adapters.base import ToolAdapter
from vigilance.components.c5_safety.audit import AuditLog
from vigilance.components.c5_safety.guardrail import SafetyGate
from vigilance.components.c6_profiles.profile_manager import ProfileManager, SectorProfile
from vigilance.llm import create_llm
from vigilance.models.action_request import ActionRequest
from vigilance.models.canonical_event import CanonicalEvent
from vigilance.models.execution_result import ActionResult, ExecutionResult
from vigilance.models.guardrail_check import GuardrailCheck, GuardrailVerdict

logger = logging.getLogger(__name__)

TOPIC_CANONICAL_EVENTS = "t53.canonical_events"
TOPIC_ACTION_REQUESTS  = "t53.action_requests"
TOPIC_RESULTS          = "t53.results"
TOPIC_POLICY_UPDATES   = "t53.policy_updates"   # consumed by T5.5 for ZTA blueprint refinement
TOPIC_ACTIONS_DISPATCH = "t53.actions.dispatch"  # consumed by pilot tools (fire-and-forget)

_UNKNOWN_PILOT  = "UNKNOWN"
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
    """T5.3 pipeline — C1 ingestion and C5+C3+C4 execution in INTEGRATED mode.

    All four GA pilots are served from a single instance. Pilot detection
    happens per-event in C1; profile and adapter set are selected automatically.

    Args:
        dry_run: When True, guardrail and audit run but broker dispatch is
                 skipped. Used in tests and development to avoid needing a
                 live RabbitMQ or pilot tool connections.
    """

    def __init__(self, dry_run: bool = False) -> None:
        self._dry_run = dry_run

        # C6 — all four sector profiles loaded at startup
        self._profiles: dict[str, SectorProfile] = ProfileManager.load_all_profiles()

        # LLM — mistral:7b for C1 extraction + C5 semantic guardrail
        #        mistral-nemo for C3 NL→Rego policy translation
        self._llm = create_llm()

        # C1
        self._normalizer = Normalizer(self._llm)

        # C3
        self._policy_translator = PolicyTranslator(self._llm)

        # C4 — all four adapter sets loaded at startup
        self._all_adapters: dict[str, dict[str, ToolAdapter]] = {
            sector_key: builder()
            for sector_key, builder in _ADAPTER_BUILDERS.items()
        }

        # Event cache: event_id → {event, raw_event, parser_used, c1_llm_invoked, c1_llm_fields}
        self._event_cache: dict[str, dict] = {}

        # Action request cache: request_id → raw dict (for decoupled guardrail checks)
        self._action_request_cache: dict[str, dict] = {}

        # Workflow audit CSV
        self._csv_logger = WorkflowCSVLogger()

        # C5
        self._guardrail = SafetyGate()
        self._audit = AuditLog()

        # Broker
        self._broker = create_broker()

        logger.info(f"[T53Pipeline] Initialized: pilots={list(self._profiles.keys())} dry_run={dry_run}")

    # ── Profile + adapter lookup ───────────────────────────────────────────────

    def _profile_for(self, pilot: str) -> SectorProfile:
        profile = self._profiles.get(pilot)
        if profile is None:
            logger.warning(
                f"Pilot '{pilot}' has no registered profile — "
                f"falling back to {_FALLBACK_SECTOR}."
            )
            profile = self._profiles[_FALLBACK_SECTOR]
        return profile

    def _adapters_for(self, sector: str) -> dict[str, ToolAdapter]:
        return self._all_adapters.get(sector, self._all_adapters[_FALLBACK_SECTOR])

    # ── C1: Ingest half ───────────────────────────────────────────────────────

    def ingest_event(self, raw_event: str | dict) -> CanonicalEvent:
        """C1 — normalize raw event, cache it, and publish to t53.canonical_events.

        T5.4 consumes the published CanonicalEvent, runs agentic reasoning
        (with T5.1 RAG + T5.2 agent selection), and dispatches an ActionRequest
        back to T5.3 via t53.action_requests.
        """
        logger.info("[C1] Normalizing event...")
        meta = self._normalizer.normalize_with_meta(raw_event)
        event = meta.event

        profile = self._profile_for(event.pilot)
        event = self._normalizer._enrich_with_profile(event, profile)

        logger.info(
            f"[C1] event_id={event.event_id} type={event.type} "
            f"severity={event.severity} pilot={event.pilot}"
        )

        self._event_cache[event.event_id] = {
            "event":          event,
            "raw_event":      raw_event,
            "parser_used":    meta.parser_used,
            "c1_llm_invoked": meta.llm_invoked,
            "c1_llm_fields":  meta.llm_fields,
        }
        self._broker.publish(TOPIC_CANONICAL_EVENTS, event.model_dump(mode="json"))
        logger.info(f"[C1] CanonicalEvent → {TOPIC_CANONICAL_EVENTS} (awaiting T5.4 ActionRequest)")
        return event

    # ── C5+C3+C4: Execute half ────────────────────────────────────────────────

    def execute_action_request(self, action_request_dict: dict) -> tuple[ExecutionResult, str | None]:
        """C5+C3+C4 — receive ActionRequest from T5.4, run guardrail, dispatch actions.

        Looks up the cached CanonicalEvent by event_id. If not found (e.g. cache
        evicted), constructs a minimal placeholder and logs a warning.

        Returns:
            A tuple of (ExecutionResult, rego_rule) where rego_rule is the
            NL→Rego translation string when policy_update was present, else None.
        """
        request = ActionRequest(**action_request_dict)
        logger.info(
            f"[C5] ActionRequest from T5.4: event_id={request.event_id} "
            f"actions={request.actions} confidence={request.agent_confidence:.2f}"
        )

        cached = self._event_cache.get(request.event_id)
        if cached is None:
            logger.warning(f"event_id={request.event_id} not in cache — using minimal placeholder")
            event = CanonicalEvent(
                event_id=request.event_id,
                type="UNKNOWN",
                pilot=request.pilot,
                severity="HIGH",
                timestamp=datetime.now(timezone.utc),
            )
            c1_ctx = {"raw_event": None, "parser_used": "UNKNOWN",
                      "c1_llm_invoked": False, "c1_llm_fields": None}
        else:
            event = cached["event"]
            c1_ctx = {k: cached[k] for k in ("raw_event", "parser_used",
                                              "c1_llm_invoked", "c1_llm_fields")}

        profile = self._profile_for(event.pilot)
        return self._guardrail_and_execute(request, event, profile, c1_ctx)

    # ── Decoupled guardrail API ───────────────────────────────────────────────

    def store_action_request(self, action_request_dict: dict) -> str:
        """Validate and cache an ActionRequest without executing it.

        Returns the request_id so the caller can later invoke run_guardrail()
        or execute_action_request() independently.
        """
        request = ActionRequest(**action_request_dict)
        self._action_request_cache[request.request_id] = action_request_dict
        logger.info(f"[C5] ActionRequest stored (pending): request_id={request.request_id}")
        return request.request_id

    def run_guardrail(self, request_id: str) -> GuardrailCheck:
        """Run C5 guardrail on a previously stored ActionRequest.

        Does NOT open an audit record, does NOT dispatch to C3/C4.
        Returns the raw GuardrailCheck verdict so the caller can decide
        whether to proceed to execute_action_request().
        """
        action_request_dict = self._action_request_cache.get(request_id)
        if action_request_dict is None:
            raise KeyError(f"ActionRequest {request_id!r} not found — submit it first via /action-requests/submit")

        request = ActionRequest(**action_request_dict)
        cached = self._event_cache.get(request.event_id)
        if cached is None:
            logger.warning(f"[C5] event_id={request.event_id} not in cache — using placeholder for guardrail check")
            event = CanonicalEvent(
                event_id=request.event_id,
                type="UNKNOWN",
                pilot=request.pilot,
                severity="HIGH",
                timestamp=datetime.now(timezone.utc),
            )
        else:
            event = cached["event"]

        profile = self._profile_for(event.pilot)
        guardrail = self._guardrail.check(request, event, profile, self._llm)
        logger.info(
            f"[C5] Guardrail-only check: request_id={request_id} "
            f"verdict={guardrail.verdict.value} reasons={guardrail.reasons}"
        )
        return guardrail

    # ── Guardrail + dispatch ───────────────────────────────────────────────────

    def _guardrail_and_execute(
        self,
        request: ActionRequest,
        event: CanonicalEvent,
        profile: SectorProfile,
        c1_ctx: dict | None = None,
    ) -> tuple[ExecutionResult, str | None]:
        audit_id = self._audit.open_record(
            pilot_id=profile.pilot,
            event_id=event.event_id,
            request_id=request.request_id,
        )
        logger.info(f"[C5] Audit record opened: {audit_id}")

        guardrail = self._guardrail.check(request, event, profile, self._llm)
        logger.info(
            f"[C5] verdict={guardrail.verdict.value} "
            f"ot_safety_checked={guardrail.ot_safety_checked} "
            f"reasons={guardrail.reasons}"
        )

        rego_rule: str | None = None
        if guardrail.verdict == GuardrailVerdict.REJECTED:
            logger.info("[C5] REJECTED — skipping dispatch")
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
        elif self._dry_run:
            logger.info("[C5] dry-run — skipping broker dispatch")
            result = self._dry_run_result(request, event, profile)
        else:
            result, rego_rule = self._dispatch(request, event, profile)

        logger.info(
            f"[C3+C4] overall_success={result.overall_success} "
            f"actions={[r.action for r in result.action_results]}"
        )

        self._audit.close_record(audit_id, result, guardrail)
        logger.info(f"[C5] Audit record closed: {audit_id}")

        self._broker.publish(TOPIC_RESULTS, result.model_dump(mode="json"))

        # ── Workflow audit CSV ────────────────────────────────────────────────
        ctx = c1_ctx or {}
        self._csv_logger.append(
            event_id=event.event_id,
            pilot=profile.pilot,
            severity=event.severity,
            raw_event=ctx.get("raw_event"),
            parser_used=ctx.get("parser_used", "UNKNOWN"),
            c1_llm_invoked=ctx.get("c1_llm_invoked", False),
            c1_llm_fields=ctx.get("c1_llm_fields"),
            canonical_event=event.model_dump(mode="json"),
            request_id=request.request_id,
            actions_requested=request.actions,
            agent_confidence=request.agent_confidence,
            guardrail_verdict=guardrail.verdict.value,
            guardrail_reasons=guardrail.reasons,
            c5_llm_invoked=guardrail.llm_invoked,
            c5_llm_response=guardrail.llm_response,
            policy_update_nl=request.policy_update,
            c3_llm_invoked=bool(request.policy_update),
            c3_rego_rule=rego_rule,
            actions_dispatched=[r.action for r in result.action_results],
            overall_success=result.overall_success,
            audit_id=audit_id,
        )

        return result, rego_rule

    def _dispatch(
        self,
        request: ActionRequest,
        event: CanonicalEvent,
        profile: SectorProfile,
    ) -> tuple[ExecutionResult, str | None]:
        """C3+C4 — translate policy to Rego, fire-and-forget to T5.5 and pilot tools."""
        rego: str | None = None
        # C3: NL policy → Rego → T5.5 ZTA blueprint refinement
        if request.policy_update:
            rego = self._policy_translator.translate(request.policy_update)
            logger.info(f"[C3] NL→Rego translation complete ({len(rego)} chars)")
            self._broker.publish(TOPIC_POLICY_UPDATES, {
                "request_id": request.request_id,
                "event_id":   request.event_id,
                "pilot":      profile.pilot,
                "sector":     profile.sector,
                "nl_policy":  request.policy_update,
                "rego_rule":  rego,
                "timestamp":  datetime.now(timezone.utc).isoformat(),
            })
            logger.info(f"[C3] Policy → {TOPIC_POLICY_UPDATES} ({len(rego)} chars, pilot={profile.pilot})")

        # C4: actions → pilot tools (fire-and-forget)
        self._broker.publish(TOPIC_ACTIONS_DISPATCH, {
            "request_id":       request.request_id,
            "event_id":         request.event_id,
            "pilot":            profile.pilot,
            "sector":           profile.sector,
            "actions":          request.actions,
            "agent_confidence": request.agent_confidence,
            "timestamp":        datetime.now(timezone.utc).isoformat(),
        })
        logger.info(f"[C4] Actions → {TOPIC_ACTIONS_DISPATCH}: {request.actions} (pilot={profile.pilot})")

        return ExecutionResult(
            request_id=request.request_id,
            event_id=event.event_id,
            pilot=profile.pilot,
            action_results=[
                ActionResult(
                    action=action,
                    plugin="broker_dispatch",
                    success=True,
                    latency_ms=0,
                    response_code=202,
                    message=f"Dispatched via {TOPIC_ACTIONS_DISPATCH}",
                )
                for action in request.actions
            ],
            overall_success=True,
            timestamp=datetime.now(timezone.utc),
        ), rego

    def _dry_run_result(self, request: ActionRequest, event: CanonicalEvent, profile: SectorProfile) -> ExecutionResult:
        return ExecutionResult(
            request_id=request.request_id,
            event_id=event.event_id,
            pilot=profile.pilot,
            action_results=[
                ActionResult(
                    action=action,
                    plugin="dry_run",
                    success=True,
                    latency_ms=0,
                    response_code=200,
                    message=f"[DRY-RUN] Would dispatch: {action}",
                )
                for action in request.actions
            ],
            overall_success=True,
            timestamp=datetime.now(timezone.utc),
        )

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def audit_log(self) -> AuditLog:
        return self._audit

    @property
    def broker(self) -> BaseBroker:
        return self._broker

    @property
    def profiles(self) -> dict[str, SectorProfile]:
        return self._profiles
