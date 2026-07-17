# BLUEPRINT.md — VIGILANCE T5.3 Architectural Blueprint

> This document describes the design rationale, GA mandate mapping, and integration contracts
> for the T5.3 Agentic Wrapper Framework. It is intended as a stable reference for D5.1 contributions,
> partner-facing architecture discussions, and onboarding. For implementation-level details
> (schemas, component internals, developer guides), see `CLAUDE.md` and `README.md`.

**Project:** VIGILANCE — Horizon Europe GAP-101249737
**Task:** T5.3 — Agentic Wrappers for Cybersecurity Technologies
**Task Lead:** INNOV-ACTS
**Last updated:** July 2026

---

## Purpose of T5.3

The T5.3 Agentic Wrapper Framework is the operational execution layer of the VIGILANCE platform. It sits between the WP5 intelligence stack (T5.1 RAG, T5.2 agent repository, T5.4 orchestrator) and the real cybersecurity tools deployed in each pilot environment.

Its three core responsibilities are:

**Normalisation.** Raw security events from heterogeneous pilot tool stacks — spanning CEF, ECS, OT JSON, syslog, and free-text alert formats — are ingested and normalised into a single canonical representation, the `CanonicalEvent`, that the rest of the platform can reason over without source-format dependencies.

**Safety and policy.** Before any remediation action reaches a real tool, T5.3 applies a deterministic safety gate that enforces confidence thresholds, protected-IP allowlists, proportionality limits, and OT-specific isolation rules. Natural language policy changes can also be compiled to enforceable OPA/Rego rules in the same pass.

**Execution.** Approved actions are dispatched to pilot-specific tool adapters — or fire-and-forwarded via the message broker to downstream pilot tool consumers — producing a structured execution record for the orchestrator and the audit log.

Everything that enters the platform as raw data, and everything that leaves as a tool command, passes through T5.3.

---

## GA Mandate Mapping

| GA Requirement | T5.3 Implementation |
|---|---|
| Sector-specific agentic wrappers for all four VIGILANCE pilots | One multi-pilot container; sector detected per-event in C1; four C6 profiles and twelve C4 adapters loaded at startup |
| Zero Trust Architecture enforcement | C5 safety gate enforces ZTA-aligned checks (confidence, IP allowlist, proportionality, OT zone scope); C3 translates NL policy to OPA/Rego for the ZTA policy engine |
| Transferable wrappers across sectors (RS4) | Four profile YAMLs define sector-specific schemas, adapter sets, and LLM prompts independently; swapping a profile is the only change needed to target a different sector |
| EU data sovereignty / GDPR compliance | LLM inference is self-hosted (Ollama + Mistral models on project cloud); no event data leaves the deployment boundary |
| Immutable audit trail | AuditLog records every event lifecycle from gate to closure; WorkflowCSVLogger captures the full telemetry per execution in `workflow_audit.csv` |
| SME-accessible deployment | Single `docker compose up --build` deploys the full stack; no sector configuration required at startup |
| Integration with WP5 AI intelligence stack | Broker interface to T5.4 (canonical events + execution results); broker interfaces to T5.2 (execution results for agent improvement) |

---

## Architectural Principles

### 1. Separation of reasoning and execution

T5.3 owns normalisation, safety, policy, and dispatch. It does not own agentic reasoning, agent selection, or threat classification. Those belong to T5.4 (orchestrator) and T5.2 (agent repository). This boundary keeps T5.3 deterministic and auditable: given the same inputs, it produces the same safety decision.

The in-process reasoning loop (C2, AgentLoop) was removed in May 2026 (PR #28) once it became clear that T5.4 was the authoritative locus for agent decision-making. T5.3 now operates exclusively as a gateway — bidirectional, not deliberative.

### 2. Schema-first integration

All cross-task data exchange is defined by frozen Pydantic v2 models with corresponding JSON Schema (draft 2020-12) definitions under `schemas/models/`. The schema set (`CanonicalEvent`, `ActionRequest`, `AgentDecision`, `GuardrailCheck`, `ActionResult`, `ExecutionResult`, `AuditRecord`) was agreed with T5.4 (GFT) at M6 and is the binding integration contract. Field changes require formal cross-task sign-off.

### 3. LLM as a conditional fallback, not a default path

On the happy path — known log format, confidence above threshold, no NL policy update — T5.3 makes zero LLM calls. LLMs are invoked only at three well-defined escalation points: C1 log format fallback, C5 semantic guardrail escalation, and C3 NL→Rego translation. This keeps the common path fast, deterministic, and auditable, while preserving LLM flexibility for edge cases.

### 4. Fail-closed safety semantics

Every safety decision defaults to the more restrictive outcome on failure. If the C5 LLM semantic check is unavailable, the verdict escalates to a human SOC analyst rather than auto-approving. If C3 NL→Rego translation fails after one retry, the published Rego rule is `default deny = true`. The broker dispatch is fire-and-forget but the audit record always closes — even on execution failure.

### 5. Multi-pilot without multi-instance

A single runtime process serves all four GA pilots simultaneously. Sector detection happens per-event in C1 by parser heuristics and LLM field extraction. There is no startup sector selection, no process restart needed to switch pilots, and no cross-pilot state contamination. This is a deliberate design choice to simplify deployment and enable GA transferability without operational complexity.

### 6. Broker as the integration surface

All inter-task communication is mediated by RabbitMQ. T5.3 never calls T5.1, T5.2, T5.4, or T5.5 directly. It publishes to and consumes from well-defined durable queues. This gives each task independent deployment lifecycles, decouples failure domains, and makes the integration surface inspectable via the RabbitMQ management UI.

---

## Component Responsibilities

### C1 — Event Ingestion and Normalization

C1 is the platform's event frontier. It accepts any raw security log in CEF, ECS, OT JSON, or syslog format, and falls back to an LLM-based field extractor (Mistral 7B) for unknown formats. The output is always a `CanonicalEvent` with a T5.3-generated UUID, a normalised severity, and sector-specific extension fields populated from the log content.

C6 enrichment runs after parsing: for INDUSTRY_4 events, the OT safety flag is applied if the profile mandates it. The detected pilot is never overridden by the profile — it comes from the event content itself.

### C3 — Action and Policy Execution

C3 has two sub-responsibilities. First, it translates natural-language policy updates (when present in the ActionRequest) into enforceable OPA/Rego rules using Mistral Nemo 12B with a four-example few-shot prompt, OPA parse validation, and a single retry cycle. Second, it coordinates the dispatch of approved actions to the tool layer (C4) or to the message broker.

### C4 — Tool Adapter Layer

C4 is a plugin system. Each adapter wraps one pilot tool (SIEM, IAM, EDR/IDS, SCADA, fraud engine) and declares the exact action verbs it handles. Adapters are pure Python classes implementing the `ToolAdapter` ABC — they do not perform LLM inference, they do not parse events, and they do not make safety decisions. In the current implementation all adapters return stub responses; real tool connections are planned for M10–M15 for the INNOV-scoped pilots (OTE, Siemens).

In the production pipeline, actions are dispatched fire-and-forget to the `t53.actions.dispatch` broker topic. The per-verb `ActionExecutor` routing is available for direct in-process calls and testing.

### C5 — Safety Gate and Audit

C5 wraps every ActionRequest with a pre-execution guardrail and a post-execution audit closure. The guardrail applies five deterministic checks before any action is dispatched (confidence, protected-IP, proportionality, OT isolation, OT zone scope). ESCALATE verdicts — cases that are borderline rather than clearly approved or rejected — trigger a Mistral 7B semantic second-opinion. The audit log records every decision and its outcome.

### C6 — Sector Profile Manager

C6 is a cross-cutting configuration layer. It loads YAML profiles at startup and makes them available to all other components. A profile defines the confidence threshold, protected IP ranges, OT safety flag, LLM system prompt, and the set of C4 plugins for that sector. All four profiles are loaded at startup; the correct one is selected per-event based on the pilot detected by C1.

---

## Integration Contracts

### T5.3 → T5.4

T5.3 publishes `CanonicalEvent` to `t53.canonical_events`. T5.4 (GFT orchestrator) consumes these, enriches them with T5.1 RAG context, selects a T5.2 agent, and publishes an `ActionRequest` to `t53.action_requests`. T5.3 then consumes the `ActionRequest` and returns an `ExecutionResult` to `t53.results`.

T5.3 is never blocked waiting for T5.4 — it returns 202 Accepted on event submission and proceeds. The round-trip is fully asynchronous.

### T5.3 → T5.2

`ExecutionResult` published to `t53.results` is consumed by T5.2 (AEGIS) for agent improvement feedback loops. T5.3 does not call T5.2 directly.

### T5.3 → T5.5

T5.3 publishes compiled Rego rules to `t53.policy_updates` when an `ActionRequest` carries a `policy_update` NL string. The downstream consumer of this topic is currently undefined — T5.5 (STAM) was ruled out at the July 1 KOM as its scope is blueprint and scenario collection, not policy enforcement. The topic remains active; the consumer question will be resolved in M7–M9.

T5.3 separately provides raw pilot event data to STAM (as committed at the July 1 KOM) for scenario building. This is not a broker integration — it is a direct data-sharing action.

### T5.3 → T5.6

T5.3 exposes a REST API on port 8000 as an integration point for T5.6 (ETRA Agentic ZTA Platform). The API accepts raw events and ActionRequests, and can return full ExecutionResults including any Rego translation output. API key enforcement is planned for M7–M9.

### T5.3 → Pilot tools

Actions are dispatched fire-and-forget to `t53.actions.dispatch`. Pilot tools consuming this topic are responsible for executing the actions and operating within their own reliability envelope. T5.3 does not block on pilot tool responses.

---

## Sector Profiles and Transferability

The four sector profiles (`telecom.yaml`, `industry4.yaml`, `maritime.yaml`, `finance.yaml`) encode everything that is sector-specific in one place: extension field declarations, C4 plugin sets, LLM system prompt framing, confidence thresholds, and OT safety flags. This design separates the generic T5.3 pipeline logic from sector-specific knowledge.

| Aspect | How it varies by sector |
|---|---|
| Confidence threshold | TELECOM, INDUSTRY_4, MARITIME: 0.80; FINANCE: 0.85 (PSD2/DORA regulatory environment) |
| OT safety flag | INDUSTRY_4 only: gates OT-specific guardrail checks ④ and ⑤ |
| LLM system prompt | Each profile carries a sector-specific framing for the LLM fallback and semantic guardrail |
| C4 adapter set | 3 plugins per sector, 12 total; no adapter is shared across sectors |
| Schema extensions | Flat on `CanonicalEvent` — TELECOM (subscriber_id, cell_id, imsi), INDUSTRY_4 (plc_id, line_id, scada_zone, ot_protocol, ot_safety_flag), MARITIME (vessel_id, port_zone, ais_mmsi, cargo_system_id), FINANCE (account_id, transaction_id, branch_id, fraud_score) |

Adding a fifth sector requires: a new YAML profile, three new C4 adapter plugins, and registration in `_ADAPTER_BUILDERS` in `pipeline.py`. No changes to the pipeline logic, schema models, or broker setup are required.

---

## Audit and Observability

T5.3 produces two audit artefacts:

**AuditRecord** — in-memory record opened at C5 gate entry and closed after dispatch. Captures guard verdict, action results, and latencies. Will be exposed via a REST endpoint at M7–M9.

**WorkflowCSVLogger** — thread-safe CSV append per pipeline execution. Captures the full C1 → C5 → C3 → C4 telemetry: raw event, parser used, LLM calls in each stage, guardrail verdict and reasons, generated Rego, dispatched actions, and overall success. Written to `data/workflow_audit.csv` (mounted volume). This is the primary operational observability surface for the current phase.

**RabbitMQ management UI** (http://localhost:15672) provides real-time queue depth and message throughput visibility.

**Dozzle** (http://localhost:9999) aggregates structured logs from all containers in real time.

---

## OPA/Rego Policy Architecture

Rego rules generated by C3 follow a strict convention to ensure they are composable with the wider ZTA policy engine:

**Package naming:** `vigilance.<pilot_lower>.<domain>` — e.g. `package vigilance.ote.auth`, `package vigilance.siemens.ot`

**Dynamic references:** Rules never inline host lists or IP ranges. Variable memberships use `data.vigilance.<pilot>.*` references that the policy engine populates at evaluation time from the ZTA data store.

**Fail-closed defaults:** All rules use either `default deny = true` (with allow conditions) or `default allow = true` (with deny conditions). On translation failure, a `default deny = true` fallback is published.

**Input schema:** Rules may reference `input.action`, `input.source_ip`, `input.destination`, `input.subject`, `input.resource`, `input.mfa_verified`, `input.target`, and `input.scada_zone`. Adding new input fields requires updating the system prompt, the few-shot examples, and notifying the downstream policy engine operator.

---

## Deferred Capabilities

The following capabilities are designed for but not yet implemented. They are part of the T5.3 roadmap, not scope changes.

| Capability | Status | Target |
|---|---|---|
| Real C4 adapter implementations (OTE, Siemens) | Planned | M10–M15 |
| C4 target resolution from CanonicalEvent fields | Planned | M10–M15 |
| API key authentication on REST API | Planned | M7–M9 |
| Audit REST endpoint (`GET /api/v1/audit`) | Planned | M7–M9 |
| Downstream consumer of `t53.policy_updates` | Open | M7–M9 (T5.6 discussion) |
| WP3 / D-VISOR synthetic event integration | Open | Post-M18 |
| RS4 reusable wrapper packaging | Planned | M18 |
| SME non-expert deployment guide | Planned | Before pilot deployment |
