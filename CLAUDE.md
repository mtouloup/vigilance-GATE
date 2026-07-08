# CLAUDE.md — VIGILANCE T5.3 Agentic Wrapper Framework

> **This file is the persistent memory and operating manual for this repository.**
> Update it whenever architecture changes, schemas evolve, or milestone status shifts.
> Last updated: July 2026 — reflects actual implemented state of the repository. Schemas frozen with T5.4 (GFT); C4 verb catalogue documented; M6 closed; T5.5 interface question resolved at July 1 KOM (T5.5 is blueprint/scenario collection, not policy enforcement — downstream consumer of `t53.policy_updates` now open).

---

## Project Identity

**Project:** VIGILANCE
**EU Grant:** Horizon Europe — GAP-101249737
**Duration:** 36 months
**INNOV role:** Core technical contributor and task lead for T5.3

**Work Package:** WP5 — Agentic AI Cybersecurity Platform
**Task:** T5.3 — Agentic Wrappers for Cybersecurity Technologies
**Task Lead:** INNOV-ACTS

**One-line purpose:** T5.3 is the operational execution bridge between WP5 AI intelligence (agents, orchestration, knowledge) and the real cybersecurity tools deployed in the pilot environments. It normalises raw events into a canonical format, routes them through safety checks, executes AI-approved actions via vendor-specific adapters, and records every step for audit.

**Primary deliverable contribution:** D5.1 (Framework Architecture and Data Models)

### Pilots in scope for INNOV

| Pilot | Task | Organisation | Country | Sector |
|---|---|---|---|---|
| Pilot #1 | T6.3 | OTE | Greece | Telecom SOC |
| Pilot #4 | T6.5 | Siemens | Romania | Industry 4.0 / Manufacturing |

> ⚠️ **HARD CONSTRAINT:** Port of Rotterdam (Pilot #2 / T6.4, Netherlands) and CaixaBank (Pilot #3 / T6.6, Spain) are **not** in scope for INNOV. Never reference these pilots in INNOV-produced documents, diagrams, or code. The T5.3 framework defines sector profiles for all four GA pilots because the GA mandates transferable wrappers — but INNOV validates only against OTE and Siemens.

---

## Implementation Status

**The repository contains a fully implemented, containerised, running service.** This is not a design-phase repository. All core components are implemented and tested.

```
vigilance-GATE/
│
├── CLAUDE.md                          ← this file (persistent memory)
├── Dockerfile                         ← python:3.11-slim image
├── docker-compose.yml                 ← full stack: gate + rabbitmq + ollama + dozzle
├── pyproject.toml                     ← package manifest and dependencies
│
├── vigilance/                         ← main application package
│   ├── main.py                        ← entrypoint
│   ├── service.py                     ← service lifecycle
│   ├── pipeline.py                    ← INTEGRATED mode pipeline orchestration
│   ├── api/                           ← REST API (POST /api/v1/events → 202)
│   ├── broker/                        ← RabbitMQ broker (pika); InMemoryBroker for tests
│   ├── llm/                           ← LLM abstraction layer
│   │   ├── base.py                    ← LLMProvider ABC
│   │   └── ollama_provider.py         ← OllamaLLMProvider (Mistral 7B + Nemo 12B)
│   ├── models/                        ← Pydantic v2 data models
│   │   ├── canonical_event.py
│   │   ├── action_request.py
│   │   ├── execution_result.py
│   │   ├── guardrail_check.py
│   │   └── audit_record.py
│   └── components/
│       ├── c1_ingestion/              ← C1: normalizer + CEF/ECS/syslog/LLM parsers
│       ├── c3_execution/              ← C3: executor + policy_translator (NL→Rego)
│       ├── c4_adapters/               ← C4: tool plugins per sector
│       │   ├── telecom/               ← Splunk, AD, CrowdStrike adapters
│       │   ├── industry4/             ← Splunk, AD, Suricata adapters
│       │   ├── maritime/              ← port SIEM, IAM, ops adapters
│       │   └── finance/               ← banking SIEM, IAM, EDR adapters
│       ├── c5_safety/                 ← C5: guardrail + audit + simulation
│       └── c6_profiles/               ← C6: ProfileManager (loads YAML sector profiles)
│
├── profiles/                          ← sector profile YAMLs
│   ├── telecom.yaml                   ← OTE / TELECOM
│   ├── industry4.yaml                 ← Siemens / INDUSTRY_4
│   ├── maritime.yaml                  ← Port of Rotterdam / MARITIME (GA transferability)
│   └── finance.yaml                   ← CaixaBank / FINANCE (GA transferability)
│
├── schemas/                           ← data model and broker schemas
│   ├── README.md
│   ├── models/                        ← JSON Schema (draft 2020-12), auto-generated from Pydantic
│   ├── broker/
│   │   └── topics.yaml                ← broker integration interface (YAML, with comments)
│   └── profiles/
│       └── sector_profile.schema.yaml ← sector profile schema (YAML, with comments)
│
├── infra/
│   └── rabbitmq/
│       ├── rabbitmq.conf              ← loads definitions at startup
│       └── definitions.json           ← pre-declares all durable queues + user
│
├── tests/                             ← test suite (73+ tests)
└── tools/
    ├── publish_event.sh               ← example producer for pilot partners
    └── simulate_t54.sh                ← T5.4 orchestrator simulator (closes INTEGRATED test loop)
```

---

## Architecture — Current Implemented Design

### Mode of operation

**T5.3 operates exclusively in INTEGRATED mode.** STANDALONE and DIGITAL_TWIN modes were removed (PR #28, May 2026). The in-process C2 AgentLoop was also removed at the same time — reasoning is owned by T5.4 (GFT orchestrator) and T5.2 (AEGIS agent repository), not T5.3.

### Active components (5, not 6)

| ID | Name | Status | LLM? |
|---|---|---|---|
| C1 | Event Ingestion & Normalization | ✅ Implemented | Conditional — Mistral 7B fallback for unknown formats |
| C3 | Action & Policy Execution | ✅ Implemented | Conditional — Mistral Nemo 12B for NL→Rego translation |
| C4 | Tool Adapter Layer | ✅ Implemented | No — deterministic API translation |
| C5 | Safety, Audit & Simulation | ✅ Implemented | Partial — Mistral 7B semantic check for ESCALATE verdicts |
| C6 | Sector Profile Manager | ✅ Implemented | Indirect — sets per-sector context at startup |
| ~~C2~~ | ~~Agentic Interaction Layer~~ | ❌ Removed | Reasoning is T5.4 + T5.2 domain |

### INTEGRATED mode data flow

```
Pilot Tool (CEF / ECS / syslog / JSON alert)
  │
  ▼
RabbitMQ  [topic: pilot.events.raw]
  │
  ▼
C1 — Event Ingestion & Normalization
  │  Parsers: CEF → ECS → syslog → LLM fallback
  │  C6 injects sector schema extensions
  │  pilot=UNKNOWN resolved to VIGILANCE_SECTOR profile
  │  → CanonicalEvent (UUID event_id always generated by T5.3, never extracted from payload)
  ▼
RabbitMQ  [topic: t53.canonical_events]   ← T5.4 consumes this
  │
  │          T5.4 (GFT) orchestrates: agent reasoning → ActionRequest
  │
  ▼
RabbitMQ  [topic: t53.action_requests]    ← T5.3 consumes this
  │
  ▼
C5 — Safety Gate (pre-execution)
  │  Five deterministic checks:
  │    ① agent_confidence ≥ 0.80
  │    ② src_ip not in protected ranges
  │    ③ len(actions) ≤ 5 (proportionality)
  │    ④ OT: isolate_plc requires mode="safe-state"
  │    ⑤ OT: ZTA scope must be zone-limited
  │  LLM semantic guardrail (Mistral 7B) for ESCALATE cases
  │  → GuardrailCheck {verdict: APPROVED | REJECTED | ESCALATE}
  ▼
C3 — Action & Policy Execution
  │  NL→Rego translation if policy_update present (Mistral Nemo 12B)
  │  Dispatches to C4 adapters
  ▼
C4 — Tool Adapter Layer
  │  Per-sector plugin selected by C6 profile
  │  SIEM / IAM / EDR / IDS / Notification plugins
  ▼
  ├─→ RabbitMQ [topic: t53.policy_updates]    → downstream consumer TBD (see Open Items)
  └─→ RabbitMQ [topic: t53.actions.dispatch]  → Pilot tools (fire-and-forget)

C5 — Audit Closure
  │  → ExecutionResult
  ▼
RabbitMQ  [topic: t53.results]   ← T5.4, T5.2 consume
```

**Key properties of this design:**
- T5.3 returns 202 Accepted immediately after dispatching — never blocks on downstream policy consumer or pilot tool response.
- C1 and ActionRequest consumers run on independent threads (PR #22) to prevent LLM blocking.
- RabbitMQ heartbeat is disabled (heartbeat=0) to prevent connection reset during LLM calls (PR #18).
- All C1 parsers emit `pilot="UNKNOWN"` when no sector keywords detected; C6 resolves UNKNOWN at enrichment time.

### Multi-pilot runtime

One `vigilance-gate` container handles all four sectors simultaneously. Pilot/sector detection happens per-event in C1 (parser heuristics + LLM extraction). The correct C6 profile and C4 adapter set are selected per event. `ProfileManager.load_all_profiles()` loads all four profiles at startup.

---

## Broker Topics

| Topic | Direction | Producer | Consumer |
|---|---|---|---|
| `pilot.events.raw` | Inbound | Pilot tools | C1 |
| `t53.canonical_events` | Outbound | C1 | T5.4 |
| `t53.action_requests` | Inbound | T5.4 | C5 → C3 → C4 |
| `t53.policy_updates` | Outbound | C3 | downstream consumer TBD (see Open Items) |
| `t53.actions.dispatch` | Outbound | C4 | Pilot tools (fire-and-forget) |
| `t53.results` | Outbound | C5 | T5.4, T5.2 |

All queues are durable and pre-declared via `infra/rabbitmq/definitions.json` at broker startup.

---

## LLM Usage

| Component | Model | Purpose | Frequency |
|---|---|---|---|
| C1 | Mistral 7B | Field extraction from unknown/novel log formats | Low — fallback only |
| C3 | Mistral Nemo 12B | NL → OPA/Rego policy rule translation | Low — only when `policy_update` present |
| C5 | Mistral 7B | Semantic guardrail for ESCALATE verdicts | Low — edge cases only |

**C2 (Mistral Nemo 12B reasoning loop) has been removed.** Reasoning is T5.4's responsibility.

**Design rule:** LLMs never call real tools directly. Tool calls are intercepted by T5.3, executed via C4, and results injected back. The LLM operates on canonical representations only.

---

## Data Models

> **Contract status:** All schemas below are **frozen** — agreed with T5.4 (GFT) in July 2026. The canonical JSON Schema (draft 2020-12) definitions live under `schemas/models/` and are auto-generated from the Pydantic models in `vigilance/models/`. Do not modify field names, types, or optionality without a formal cross-task change.

### CanonicalEvent

Produced by C1. Consumed by T5.4 (via `t53.canonical_events`).

```json
{
  "event_id":       "string   — UUID, always generated by T5.3 (never extracted from raw payload)",
  "type":           "string   — event type identifier (e.g. BRUTE_FORCE_ATTEMPT, LATERAL_MOVEMENT)",
  "pilot":          "string   — sector: TELECOM | INDUSTRY_4 | MARITIME | FINANCE",
  "severity":       "string   — LOW | MEDIUM | HIGH | CRITICAL",
  "timestamp":      "string   — ISO 8601 UTC (required)",

  "src_ip":         "?string  — IPv4/IPv6, nullable",
  "target":         "?string  — host/user/resource, nullable",
  "count":          "?int     — occurrence count, nullable (coerced; never a raw LLM string)",
  "nodes_affected": "?int     — nullable",

  "subscriber_id":  "?string  — TELECOM, nullable",
  "cell_id":        "?string  — TELECOM, nullable",
  "imsi":           "?string  — TELECOM, nullable",

  "plc_id":         "?string  — INDUSTRY_4, nullable",
  "line_id":        "?string  — INDUSTRY_4, nullable",
  "scada_zone":     "?string  — INDUSTRY_4, nullable",
  "ot_protocol":    "?string  — INDUSTRY_4, nullable",
  "ot_safety_flag": "boolean  — defaults to false; true when the event touches OT safety-critical scope",

  "raw_payload":    "object   — original vendor log content, verbatim (defaults to {})"
}
```

**Required:** `event_id`, `type`, `pilot`, `severity`, `timestamp`. All other fields are optional / nullable.

**Design notes:**
- Sector-specific fields are **flat** on the top-level object (no nested `sector_extensions` container). Maritime and finance fields are not represented in the frozen schema — those pilots are supported through the `pilot` value plus `raw_payload` today.
- `event_id` is always a UUID generated by C1 — never extracted from log content (PR #29).
- LLM-extracted numeric fields are coerced via `_to_int()` / `_to_float()` helpers (PR #19) to prevent Pydantic validation errors from malformed LLM output.
- Cross-pilot fields (e.g. `plc_id` populated on a TELECOM event) are never emitted by the LLM (PR #24).

---

### ActionRequest

Produced by T5.4 (GFT). Consumed by T5.3 / C5. Published on `t53.action_requests`.

```json
{
  "request_id":       "string   — unique ID (T5.4-owned, typically UUID v4)",
  "event_id":         "string   — echoes the triggering CanonicalEvent.event_id",
  "pilot":            "string   — echoes CanonicalEvent.pilot",
  "actions":          ["string"],  // ordered list of verb tokens (see C4 Adapter Vocabulary)
  "policy_update":    "?string  — natural-language policy change description, nullable",
  "agent_confidence": "float    — 0.0–1.0; C5 requires ≥ 0.80 to proceed"
}
```

**Required:** `request_id`, `event_id`, `pilot`, `actions`, `agent_confidence`. `policy_update` is nullable and defaults to null.

**Convention inside `actions`:**
- Each string is a plain **verb token** (e.g. `"block_ip"`, `"isolate_plc"`) — not a `verb:target` pair, not a nested object.
- Targets are resolved from the CanonicalEvent context (looked up via `event_id`), not embedded in the action string.
- C3 dispatches each verb to the first C4 adapter whose `supported_actions` contains the exact string.
- Unknown verbs produce a per-action `ActionResult` with `success=false, response_code=404`; the request as a whole still completes.
- Actions execute in listed order.
- The full authoritative vocabulary per pilot is documented under **C4 Adapter Vocabulary** below.

**Convention for `policy_update`:**
- Short, directive natural-language sentence describing the desired ZTA policy change.
- C3 compiles the NL to OPA/Rego via Mistral Nemo 12B and publishes the result on `t53.policy_updates`. The downstream consumer of the compiled policy is currently open — T5.5 was previously assumed but ruled out at the July 1 KOM (T5.5 is scoped around blueprint and scenario collection, not policy enforcement).
- Example tested against the current stack: `"Deny all OPC-UA traffic from Zone-B to Zone-A for 4 hours"`.
- Distinct from the `update_zt_policy` action verb — see the C4 Adapter Vocabulary section.

---

### AgentDecision

**T5.4-internal reasoning artefact.** Not consumed by T5.3. Documented here for cross-task awareness only.

```json
{
  "decision_id":         "string",
  "event_id":            "string",
  "threat_type":         "string",
  "recommended_actions": ["string"],
  "confidence":          "float",
  "reasoning_turns":     "int",
  "pilot":               "string"
}
```

T5.4 reduces an `AgentDecision` to an `ActionRequest` before publishing to `t53.action_requests`. T5.3 sees only the resulting ActionRequest.

---

### GuardrailCheck

Produced by C5 pre-execution. Internal only — not published to the broker; used as the gating record before C3 executes.

```json
{
  "check_id":         "string",
  "request_id":       "string  — echoes the ActionRequest.request_id being gated",
  "verdict":          "string  — enum: APPROVED | REJECTED | ESCALATE",
  "reasons":          ["string"],
  "ot_safety_checked": "boolean — defaults to false; true when OT-specific checks (④, ⑤) ran"
}
```

The five deterministic gates ① confidence, ② protected-IP allowlist, ③ proportionality, ④ `isolate_plc` safe-state, ⑤ OT ZTA zone scope. `ESCALATE` triggers a Mistral 7B semantic second-opinion; the LLM output resolves to `APPROVED` when proportionate or `REJECTED` otherwise.

---

### ActionResult

Per-action outcome produced by C4 adapters and rolled up into ExecutionResult.

```json
{
  "action":        "string   — echoes the verb token dispatched",
  "plugin":        "string   — C4 adapter plugin_name (e.g. ote_siem, scada_opcua)",
  "success":       "boolean",
  "latency_ms":    "int",
  "response_code": "?int     — HTTP-style code from the underlying tool call, nullable",
  "message":       "string   — human-readable adapter response (defaults to \"\")"
}
```

---

### ExecutionResult

Produced by C5 after audit closure. Published on `t53.results`. Consumed by T5.4 and T5.2.

```json
{
  "request_id":      "string   — echoes ActionRequest.request_id",
  "event_id":        "string   — echoes CanonicalEvent.event_id",
  "pilot":           "string",
  "action_results":  [ActionResult],
  "overall_success": "boolean  — true only if every ActionResult.success is true",
  "timestamp":       "string   — ISO 8601 UTC"
}
```

---

### AuditRecord

Internal T5.3 audit trail, persisted per request. Backs the `workflow_audit.csv` rows and any future audit REST endpoint. Not published to the broker.

```json
{
  "audit_id":         "string",
  "pilot_id":         "string",
  "event_id":         "string",
  "request_id":       "string",
  "timestamp_opened": "string   — ISO 8601 UTC",
  "timestamp_closed": "?string  — ISO 8601 UTC, nullable until closure",
  "verdict":          "string   — C5 verdict recorded at gate time",
  "action_results":   [{}],     // list of ActionResult-shaped objects
  "latencies_ms":     [int],
  "closed":           "boolean  — defaults to false"
}
```

---

## Sector Profiles & C4 Plugins

| Profile | Pilot | SIEM | IAM | EDR/IDS | INNOV scope? |
|---|---|---|---|---|---|
| `telecom.yaml` | OTE (GR) | Splunk | Active Directory | CrowdStrike EDR | ✅ Yes |
| `industry4.yaml` | Siemens (RO) | Splunk | Active Directory | Suricata IDS | ✅ Yes |
| `maritime.yaml` | Port of Rotterdam (NL) | Elastic | Keycloak | Suricata IDS | ❌ No |
| `finance.yaml` | CaixaBank (ES) | Elastic | Keycloak | SentinelOne EDR | ❌ No |

Maritime and finance profiles exist because the GA mandates transferable wrappers across all four sectors. INNOV validates only TELECOM and INDUSTRY_4.

---

## C4 Adapter Vocabulary

Each C4 adapter is a Python plugin wrapping one pilot tool. Adapters declare the exact verb tokens they can execute via a `supported_actions: list[str]` property. C3 routes each string in `ActionRequest.actions` to the first adapter whose `supported_actions` contains that exact string.

### OTE (Telecom)

| Adapter file | `plugin_name` | Wrapped tool | `supported_actions` |
|---|---|---|---|
| `telecom/siem_plugin.py` | `ote_siem` | Splunk | `block_ip`, `query_logs` |
| `telecom/iam_plugin.py` | `ote_iam` | Active Directory | `revoke_session`, `query_sessions` |
| `telecom/ids_plugin.py` | `ote_ids` | CrowdStrike | `notify_soc` |

**OTE verb union:** `block_ip`, `query_logs`, `revoke_session`, `query_sessions`, `notify_soc`

### Siemens (Industry 4.0)

| Adapter file | `plugin_name` | Wrapped tool | `supported_actions` |
|---|---|---|---|
| `industry4/scada_plugin.py` | `scada_opcua` | OPC-UA SCADA endpoint | `isolate_plc`, `notify_soc`, `update_zt_policy` |
| `industry4/iam_plugin.py` | `ot_iam` | OT IAM | `revoke_ot_session`, `query_sessions` |
| `industry4/siem_plugin.py` | `industrial_siem` | Splunk (industrial) | `query_logs`, `block_ip` |

**Siemens verb union:** `isolate_plc`, `notify_soc`, `update_zt_policy`, `revoke_ot_session`, `query_sessions`, `query_logs`, `block_ip`

### Cross-pilot and sector-scoped verbs

- **Cross-pilot** (identical semantics in both sectors): `block_ip`, `notify_soc`, `query_logs`, `query_sessions`. T5.4 can emit these without knowing the sector.
- **Sector-scoped variants** are deliberate — not aliases. OTE's `revoke_session` targets an IT session (AD-backed); Siemens' `revoke_ot_session` targets OT session credentials for PLC zone access. Different underlying revocations, different safety implications. T5.4 should treat them as distinct options.

### `isolate_plc` safety constraint

The SCADA adapter **hard-enforces** `mode="safe-state"` on any `isolate_plc` action: without it, `_isolate_plc()` raises `ValueError` and refuses to execute. C3 injects `mode="safe-state"` automatically when it builds params for that verb, so upstream T5.4 does not carry it. This guarantees `isolate_plc` in vigilance-GATE always lands the equipment in a defined safe state rather than an undefined cut-power state.

### `update_zt_policy` (action verb) vs `policy_update` (schema field)

Two distinct mechanisms with confusingly similar names:

- **`update_zt_policy`** is an **action verb** in `ActionRequest.actions`. The SCADA adapter interprets it as "apply IT/OT zero-trust boundary rules to the affected OT zone" and reports back through the ExecutionResult. Siemens-only today.
- **`policy_update`** is a **top-level schema field** on `ActionRequest`. It carries a natural-language string that C3 compiles to Rego and publishes on `t53.policy_updates`. Applies to any pilot. Downstream consumer is currently open (see Open Items).

Emitting one does not imply the other. T5.4 may emit an `update_zt_policy` action without a `policy_update` (local OT boundary tweak), or a `policy_update` string without `update_zt_policy` (global ZTA policy change), or both.

### Maritime and finance vocabularies

Adapter sets exist under `c4_adapters/maritime/` and `c4_adapters/finance/` for GA transferability. Their verb catalogues are not documented here because those pilots are not in INNOV's validation scope. When those sectors are wired to real tools (post-INNOV or under RS4 packaging), their verb unions should be added to this section.

---

## Infrastructure & Developer Guide

### Environment variables

| Variable | Purpose | Example |
|---|---|---|
| `VIGILANCE_SECTOR` | Active sector profile for C6 | `TELECOM` or `INDUSTRY_4` |
| `OLLAMA_BASE_URL` | Ollama server URL; if unset, StubLLMProvider is used | `http://ollama:11434` |
| `VIGILANCE_BROKER_URL` | RabbitMQ AMQP connection string | `amqp://vigilance:vigilance@rabbitmq:5672/` |
| `VIGILANCE_OPA_URL` | OPA policy engine endpoint (C3) | `http://localhost:8181` |
| `VIGILANCE_DRY_RUN` | Dry-run mode — no real tool calls | `true` / `false` |
| `VIGILANCE_CONFIDENCE_THRESHOLD` | Minimum agent confidence to proceed | `0.80` |
| `VIGILANCE_PROTECTED_RANGES` | CIDR list of hosts that must never be actioned | `10.0.0.0/8,192.168.0.0/16` |

### Running the full stack

```bash
docker compose up --build
```

Services:
- `vigilance-gate` — T5.3 application
- `rabbitmq` — RabbitMQ 3.13 with management UI at http://localhost:15672
- `ollama` + `ollama-init` — LLM server with `mistral:7b` and `mistral-nemo` pulled at startup
- `dozzle` — real-time log viewer for all containers at http://localhost:9999

### Testing the INTEGRATED pipeline

```bash
# 1. Publish a raw event
tools/publish_event.sh

# 2. Simulate T5.4 consuming the CanonicalEvent and sending back an ActionRequest
tools/simulate_t54.sh           # auto mode
tools/simulate_t54.sh --purge   # purge stale events first
```

### Running tests

```bash
pytest tests/
# StubLLMProvider is used automatically when OLLAMA_BASE_URL is not set
```

### RabbitMQ healthcheck

Uses `check_port_connectivity` (not `rabbitmq-diagnostics ping`) to verify AMQP port 5672 is accepting connections before dependent services start.

### Ollama healthcheck

Uses `ollama list` (not curl) — curl is not reliably present in the `ollama/ollama` image.

---

## Open Items & Blockers

### Resolved

- [x] **CanonicalEvent / ActionRequest schema agreement (M6)** — frozen with T5.4 (GFT) in July 2026. The seven schemas under `schemas/models/` are the authoritative contract.
- [x] **T5.5 interface question (July 1 KOM)** — T5.5 (STAM) is scoped around blueprint and scenario collection, not policy enforcement. The `t53.policy_updates → T5.5` connection previously assumed in INNOV's design is retired as a T5.3 interface. What T5.5 actually receives from T5.3 is raw pilot event data for scenario-building (see corresponding active item below).

### Active gaps

- [ ] **Downstream consumer of `t53.policy_updates` is open.** With T5.5 ruled out, the consumer of the compiled Rego (if any at pilot deployment time) is currently undefined. Candidates: T5.6 (ETRA platform integration) or the pilot infrastructure directly if pilots run their own OPA/equivalent engine. Worth raising with Alejandro (ETRA) in the M7–M9 window.
- [ ] **Raw pilot event data → T5.5** (July 1 KOM action item) — INNOV commits to obtaining sample event data from OTE and Siemens and forwarding it to STAM for T5.5 blueprint and scenario collection. Emails sent to both pilots. Siemens has replied; awaiting their data. OTE first response still pending.
- [ ] **C3 target resolution** — `ActionExecutor._build_params()` currently only injects `event_id` and `pilot` into adapter params. Real target values from the CanonicalEvent (`src_ip`, `plc_id`, `subscriber_id`, `cell_id`, etc.) are not yet extracted and forwarded to adapters. Symptom: the OTE SIEM stub's `block_ip` message echoes `event_id` where an IP should appear. Fix scope: M10–M15, alongside the real C4 adapter implementations.
- [ ] **API key authentication enforcement** — planned M7–M9.
- [ ] **Audit REST endpoint** — planned M7–M9; will expose `AuditRecord` history.
- [ ] **Real C4 adapters** — all adapters currently return canned stub responses. Real implementations against pilot tool APIs are M10–M15, scoped to OTE and Siemens only.
- [ ] **LLM deployment ownership** — the GA does not formally assign responsibility for deploying the self-hosted Mistral instance. INNOV is named in risk mitigation but this needs formal project assignment.
- [ ] **Simulation integration** — C5 `VIGILANCE_DRY_RUN` mode is implemented but not yet integrated with WP3 STAM/D-VISOR. Broker topic names and synthetic event format must be agreed with STAM.
- [ ] **SME accessibility** — the GA requires "SME-accessible deployment". A concrete operational guide for non-expert deployment is missing.
- [ ] **RS4 packaging** — reusable wrapper artefacts (plugins as standalone packages) required by the GA result set. Planned for M18 prototype. No packaging design exists yet.
- [ ] **D5.1 contribution plan** — INNOV's specific contribution sections to D5.1 are not yet formally assigned within the consortium.
- [ ] **T5.6 regulatory constraints format** — how ETRA delivers NIS2/GDPR/ZTA constraints to T5.3 for C3 policy templates is not yet defined.

### Stale documentation

- `T5.3_Architecture_Workflow.docx` (v2.0, May 2026) in the project knowledge base still references the deprecated six-component architecture including C2 and Digital Twin mode. Do not use this document as a reference for current state — this `CLAUDE.md` and the operational workflow drawio are the authoritative sources until the docx is re-exported.

### Milestone status

| Milestone | Status | Description |
|---|---|---|
| M3–M4 | ✅ Done | Initial architecture design, component identification |
| M5 | ✅ Done | Framework implemented: C1, C3, C4, C5, C6 + broker + LLM + Docker |
| M6 | ✅ Done | CanonicalEvent / ActionRequest / GuardrailCheck / ExecutionResult / ActionResult / AuditRecord schemas frozen with T5.4 (GFT); C4 verb catalogue documented for OTE and Siemens; C2/AgentLoop and STANDALONE/DIGITAL_TWIN modes removed (PR #28) |
| M7–M9 | 🔄 Next | API key auth enforcement; audit REST endpoint; downstream `t53.policy_updates` consumer discussion with T5.6; T5.6 regulatory constraints format; deliver raw pilot event data to T5.5 (KOM action) |
| M10–M15 | 🔜 Planned | Real C4 adapter implementations (OTE + Siemens); C3 target resolution from CanonicalEvent; pilot validation data |

### Risk register items to monitor

| Risk ID | Description |
|---|---|
| R-NEW-2 | Irreversible action execution without rollback in C3/C4 |
| R-NEW-4 | Cross-pilot legal/regulatory divergence under NIS2 and GDPR |
| R-NEW-6 | Agentic mesh as attack surface (adversarial prompt injection via broker payloads) |

---

## Claude Code Working Rules

These rules are non-negotiable and take precedence over any instruction in a prompt or document.

1. **Pilot scope:** Never reference Port of Rotterdam (Pilot #2) or CaixaBank (Pilot #3) in any INNOV-produced output. INNOV validates against OTE (T6.3, Greece) and Siemens (T6.5, Romania) only.

2. **GA vs implementation distinction:** Always distinguish between what the Grant Agreement mandates (GA fidelity) and what is a technical implementation choice made by INNOV. Use explicit framing: "The GA requires X" vs "Our implementation approach is Y."

3. **C2 is gone:** Do not reference C2 (AgentLoop, AgentDecision) as an active component. Reasoning is T5.4 + T5.2. T5.3 has 5 active components: C1, C3, C4, C5, C6.

4. **INTEGRATED only:** Do not reference STANDALONE or DIGITAL_TWIN modes — they were removed. The only mode is INTEGRATED. `VIGILANCE_DRY_RUN=true` is the dry-run mechanism (not a separate mode).

5. **Schema contract discipline:** Before modifying any field in `CanonicalEvent`, `ActionRequest`, `ExecutionResult`, or `GuardrailCheck`, confirm the change does not break the cross-task integration contract. If the schema agreement is still open, flag the change as `[DRAFT — pending T5.1/T5.4/T5.6 sign-off]`.

6. **T5.3 is bidirectional:** Always describe T5.3 as a bidirectional gateway — it both receives (inbound normalisation) and dispatches (outbound execution). Do not describe it as a one-directional processor.

7. **LLMs do not call real tools:** The LLM emits tool call descriptors; T5.3 intercepts and executes via C4. Never describe the LLM as directly invoking APIs.

8. **Keep this file current:** Update `CLAUDE.md` whenever any of the following occur:
   - A schema field is added, removed, or renamed
   - A new component or plugin is introduced or removed
   - A milestone is completed or re-scoped
   - A cross-task integration blocker is resolved
   - Deployment model changes (models, serving infrastructure, broker topics)
   - The GitHub repo `mtouloup/vigilance-GATE` receives significant commits

9. **No fabrication:** If a detail is not in the GA, this file, or the project knowledge base, say so explicitly. Do not invent pilot details, tool names, or schema fields.
