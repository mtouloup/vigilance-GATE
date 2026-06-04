# CLAUDE.md — VIGILANCE T5.3 Agentic Wrapper Framework

> **This file is the persistent memory and operating manual for this repository.**
> Update it whenever architecture changes, schemas evolve, or milestone status shifts.
> Last updated: June 2026 — reflects actual implemented state of the repository.

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
  │  Deterministic checks: confidence ≥ 0.80, IP allowlist
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
  ├─→ RabbitMQ [topic: t53.policy_updates]    → T5.5 ZTA engine (fire-and-forget)
  └─→ RabbitMQ [topic: t53.actions.dispatch]  → Pilot tools (fire-and-forget)

C5 — Audit Closure
  │  → ExecutionResult
  ▼
RabbitMQ  [topic: t53.results]   ← T5.4, T5.2 consume
```

**Key properties of this design:**
- T5.3 returns 202 Accepted immediately after dispatching — never blocks on T5.5 or pilot tool response.
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
| `t53.policy_updates` | Outbound | C3 | T5.5 ZTA engine (async) |
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

### CanonicalEvent

Produced by C1. Consumed by T5.4 (via `t53.canonical_events`).

```json
{
  "event_id":   "string  — UUID, always generated by T5.3 (never extracted from raw payload)",
  "type":       "string  — event type enum: BRUTE_FORCE_ATTEMPT, LATERAL_MOVEMENT, etc.",
  "source":     "string  — originating tool class: IDS | SIEM | EDR | IAM",
  "pilot":      "string  — sector profile: TELECOM | INDUSTRY_4 | MARITIME | FINANCE",
  "src_ip":     "string  — IPv4/IPv6 or null",
  "dst_ip":     "string  — IPv4/IPv6 or null",
  "target":     "string  — host/user/resource or null",
  "severity":   "string  — LOW | MEDIUM | HIGH | CRITICAL",
  "count":      "integer — occurrence count or null (coerced; never a raw LLM string)",
  "timestamp":  "string  — ISO 8601 UTC",
  "raw_message": "string — original vendor log line, verbatim",
  "sector_extensions": {
    "TELECOM":    { "subscriber_id": "?string", "cell_id": "?string", "imsi": "?string" },
    "INDUSTRY_4": { "plc_id": "?string", "line_id": "?string", "scada_zone": "?string" },
    "MARITIME":   { "vessel_id": "?string", "berth_id": "?string", "cargo_manifest_id": "?string" },
    "FINANCE":    { "account_id": "?string", "transaction_id": "?string", "fraud_score": "?float" }
  }
}
```

**Implementation notes:**
- `event_id` is always a UUID generated by `LLMParser` — never extracted from log content (PR #29 fix).
- LLM-extracted `int`/`float` fields are coerced via `_to_int()` / `_to_float()` helpers (PR #19) to prevent Pydantic validation errors from malformed LLM output.
- All LLM string fields are coerced to `str` before Pydantic model construction (PR #21).
- Cross-pilot fields (e.g. TELECOM fields in an INDUSTRY_4 event) are never populated by the LLM (PR #24 fix).

> ⚠️ **OPEN BLOCKER:** Field names, types, and enum values have not been agreed across T5.1 (GFT), T5.4 (GFT), and T5.6 (ETRA). This is the INNOV-internal schema. Do not treat it as the consortium-ratified contract.

---

### ActionRequest

Produced by T5.4 (GFT). Consumed by T5.3 / C5. Published on `t53.action_requests`.

```json
{
  "request_id":    "string  — unique ID",
  "event_id":      "string  — triggering CanonicalEvent ID",
  "agent":         "string  — agent identifier",
  "confidence":    "float   — agent confidence (0.0–1.0); must be ≥ 0.80 to proceed",
  "actions": [
    {
      "type":       "string  — canonical action: block_ip | revoke_session | isolate_host | notify_soc | update_policy | ...",
      "target":     "string  — IP, user, host, or resource",
      "parameters": "object  — action-specific parameters"
    }
  ],
  "policy_update": {
    "intent":  "string  — natural language ZTA policy change description",
    "ttl_sec": "integer — time-to-live for the policy rule"
  },
  "simulation":    "boolean — if true, VIGILANCE_DRY_RUN mode; no real API calls"
}
```

> ⚠️ **OPEN BLOCKER:** ActionRequest structure is the INNOV-internal design. The `type` enum, per-action `parameters` schema, and `policy_update` format are not yet agreed with T5.4 (GFT). This is the primary integration blocker for the T5.3 ↔ T5.4 interface.

---

### GuardrailCheck

Produced by C5 pre-execution. Internal only — not published to the broker.

```json
{
  "ip_protected":    "boolean — target IP is in the protected allowlist",
  "confidence_ok":   "boolean — agent confidence ≥ 0.80 threshold",
  "simulation_mode": "boolean",
  "audit_log_id":    "string",
  "verdict":         "string  — APPROVED | REJECTED | ESCALATE"
}
```

`ESCALATE` triggers the Mistral 7B semantic guardrail second-opinion. ESCALATE → APPROVED when proportionate; ESCALATE → REJECTED otherwise.

---

### ExecutionResult

Produced by C5 after audit closure. Published on `t53.results`.

```json
{
  "request_id":     "string",
  "status":         "string  — SUCCESS | PARTIAL | FAILED",
  "results": [
    { "action": "string", "status": "string — OK | ERROR", "latency_ms": "integer" }
  ],
  "policy_updated": "boolean",
  "audit_closed":   "string  — audit log record ID"
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

### Critical blockers

- [ ] **CanonicalEvent / ActionRequest schema agreement** — cross-task sign-off required with T5.1 (GFT), T5.4 (GFT), T5.6 (ETRA). All schemas in this repo are INNOV-internal drafts. **This is the primary integration blocker.**
- [ ] **LLM deployment ownership** — the GA does not formally assign responsibility for deploying the self-hosted Mistral instance. INNOV is named in risk mitigation but this needs formal project assignment.

### Architecture gaps vs GA commitments

- [ ] **Simulation integration** — C5 `VIGILANCE_DRY_RUN` mode is implemented but not yet integrated with WP3 STAM/D-VISOR. Broker topic names and synthetic event format must be agreed with STAM.
- [ ] **SME accessibility** — the GA requires "SME-accessible deployment". A concrete operational guide for non-expert deployment is missing.
- [ ] **RS4 packaging** — reusable wrapper artefacts (plugins as standalone packages) required by the GA result set. Planned for M18 prototype. No packaging design exists yet.
- [ ] **D5.1 contribution plan** — INNOV's specific contribution sections to D5.1 are not yet formally assigned within the consortium.
- [ ] **T5.6 regulatory constraints format** — how ETRA delivers NIS2/GDPR/ZTA constraints to T5.3 for C3 policy templates is not yet defined.

### Milestone status

| Milestone | Status | Description |
|---|---|---|
| M3–M4 | ✅ Done | Initial architecture design, component identification |
| M5 | ✅ Done | Framework implemented: C1, C3, C4, C5, C6 + broker + LLM + Docker |
| M6 | 🔄 WIP | Agentic Interaction Layer design — now scoped to T5.3 ↔ T5.4 integration contract (CanonicalEvent/ActionRequest schema agreement) |

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
