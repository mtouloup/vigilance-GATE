# CLAUDE.md — VIGILANCE T5.3 Agentic Wrapper Framework

> **This file is the persistent memory and operating manual for this repository.**
> Update it whenever architecture changes, schemas evolve, or milestone status shifts.
> Last updated: June 2026 (auto-generated from repo content + project knowledge).

---

## Project Identity

**Project:** VIGILANCE
**EU Grant:** Horizon Europe — GAP-101249737
**Duration:** 36 months
**INNOV role:** Core technical contributor and task lead for T5.3

**Work Package:** WP5 — Agentic AI Cybersecurity Platform
**Task:** T5.3 — Agentic Wrappers for Cybersecurity Technologies
**Task Lead:** INNOV-ACTS

**One-line purpose:** T5.3 is the operational execution bridge between WP5 AI intelligence (agents, orchestration, knowledge) and the real cybersecurity tools deployed in the pilot environments. It normalises events into a canonical format, exposes tool capabilities to agents, executes AI-approved actions safely, and records every step for audit.

**Primary deliverable contribution:** D5.1 (Framework Architecture and Data Models)

### Pilots in scope for INNOV

| Pilot | Task | Organisation | Country | Sector |
|---|---|---|---|---|
| Pilot #1 | T6.3 | OTE | Greece | Telecom SOC |
| Pilot #4 | T6.5 | Siemens | Romania | Industry 4.0 / Manufacturing |

> ⚠️ **HARD CONSTRAINT:** Port of Rotterdam (Pilot #2 / T6.4, Netherlands) and CaixaBank (Pilot #3 / T6.6, Spain) are **not** in scope for INNOV. Never reference these pilots in INNOV-produced documents, diagrams, or code. The T5.3 framework defines sector profiles for all four GA pilots because the GA mandates transferable wrappers — but INNOV validates only against OTE and Siemens.

---

## Repository Structure

This repository is currently in the **documentation and design phase** (M3–M5). There is no runnable code yet. All files are design artefacts.

```
vigilance-GATE/
│
├── CLAUDE.md                              ← this file
│
├── Grant_Agreement_-_GAP-101249737.pdf    ← authoritative GA source; supersedes all
│                                             other documents on what is mandated
│
├── T5_3_Architecture_Workflow.docx        ← primary engineering reference (v2.0, May 2026)
│                                             component specs, workflow trace, LLM usage
│                                             table, GA traceability table
│
├── Architecture_explain.docx              ← presenter notes for the architecture diagram;
│                                             verbal walkthrough of the internal components
│
├── t53_internal_architecture.drawio       ← canonical architecture diagram (draw.io XML)
│                                             single tab: internal architecture showing
│                                             C1–C5 pipeline + external interfaces
│
├── t5_3_internal_Architecture.jpg         ← rasterised export of the drawio diagram
│                                             (use drawio source as truth, not this)
│
└── WP5_Global_Architecture_GFT_Perspective.png
                                           ← GFT's view of the full WP5 architecture;
                                             reference only — T5.3 positioning shown as
                                             bidirectional gateway (INNOV view), not
                                             unidirectional processor (GFT view)
```

**No source code, no test suite, no CI config, no package manifests exist yet.** The next development phase will add these. When they are added, update this file.

---

## Architecture Summary

### Core design pattern

T5.3 implements an **Observe → Reason → Act** loop:

1. **Observe:** Raw events from pilot tools are consumed from the message broker and normalised into a typed `CanonicalEvent`.
2. **Reason:** An LLM agent loop analyses the event, queries tools for additional context, and produces an `AgentDecision` with recommended actions and a confidence score.
3. **Act:** Approved `ActionRequest` objects are safety-checked, then dispatched to vendor-specific tool adapters that translate canonical actions into real API calls.

T5.3 is the **only** WP5 component that communicates directly with real pilot tools. All upstream components (T5.1, T5.2, T5.4) operate exclusively on canonical data structures produced and consumed by T5.3. This isolation enforces vendor independence, safety, and testability.

T5.3 is a **bidirectional gateway**: it both receives events from tools (inbound normalisation) and dispatches actions back to tools (outbound execution). This is architecturally distinct from a one-directional event processor.

### Six internal components

| ID | Name | Role | LLM? |
|---|---|---|---|
| C1 | Event Ingestion & Normalization | Entry point; converts raw vendor logs into `CanonicalEvent` | Conditional (unknown formats only) |
| C2 | Agentic Interaction Layer | LLM reasoning core; runs the multi-turn Observe-Reason-Act loop | Yes (core) |
| C3 | Action & Policy Execution | Receives `ActionRequest` from T5.4; dispatches to C4; applies ZTA policy changes | Conditional (NL→Rego translation) |
| C4 | Tool Adapter Layer | Translates canonical actions into vendor API calls via per-tool plugins | No (deterministic) |
| C5 | Safety, Audit & Simulation | Pre-execution safety gate; immutable audit log; Digital Twin / dry-run mode | Partial (semantic guardrail) |
| C6 | Sector Profile Manager | Cross-cutting config layer; injects sector-specific settings into C1–C4 at startup | Indirect (sets C2 system prompt) |

### Data flow (happy path)

```
Pilot Tool
  │  (CEF / ECS / syslog / JSON alert)
  ▼
Message Broker  [topic: pilot.events.raw]
  │
  ▼
C1 — Event Ingestion & Normalization
  │  (+ C6 sector schema extensions)
  │  → CanonicalEvent
  ▼
C2 — Agentic Interaction Layer
  │  (LLM multi-turn loop; queries C4 for context if needed)
  │  → AgentDecision {recommended_actions, confidence}
  ▼
T5.4 (external — GFT)
  │  (validates confidence ≥ 0.80; composes ActionRequest)
  │
Message Broker  [topic: t53.actions.execute]
  │
  ▼
C5 — Safety Gate (pre-execution)
  │  (deterministic checks + LLM semantic guardrail)
  │  → GuardrailCheck {verdict: APPROVED | REJECTED}
  ▼
C3 — Action & Policy Execution
  │  (NL→Rego if policy_update present; dispatches to C4)
  ▼
C4 — Tool Adapter Layer
  │  (SIEM / IAM / EDR / IDS / Notification plugins)
  ▼
Pilot Tool  (real API call)
  │
  ▼
C5 — Audit Closure
  │  → ExecutionResult
  ▼
Message Broker  [topic: t53.results]
  │
  ▼
T5.4 / T5.2  (orchestration state update / agent memory)
```

**Digital Twin mode:** When `VIGILANCE_SIMULATION=true`, C5 routes all actions to the WP3 STAM/D-VISOR simulation environment instead of real tools. Synthetic events arrive on broker topic `dt.events.synthetic` and flow through the full pipeline identically.

### LLM usage

| Component | Model | Purpose | Frequency |
|---|---|---|---|
| C1 | Mistral 7B | Field extraction from unknown/novel log formats | Low — only unrecognised formats |
| C2 | Mistral Nemo 12B | Multi-turn reasoning loop: investigate then decide | High — every event |
| C3 | Mistral Nemo 12B | Translate natural-language policy intent into OPA/Rego rule | Low — only when `policy_update` field present |
| C4 | None | Deterministic API translation; no LLM involvement | — |
| C5 | Mistral 7B | Semantic guardrail for ambiguous or disproportionate action sets | Low — edge cases |
| C6 | N/A | Sets per-sector system prompt injected into C2 at startup | Once at startup |

**Design rule:** The LLM in C2 never calls real tools directly. Every tool call it emits is intercepted by T5.3, executed via C4, and the result is injected back into the conversation context. The LLM operates on canonical representations only.

### Deployment model

- **LLM runtime:** Self-hosted Mistral via [Ollama](https://ollama.com/) or [vLLM](https://github.com/vllm-project/vllm) on the VIGILANCE project cloud.
- **API surface:** OpenAI-compatible API (`/v1/chat/completions`), so LLM clients require no vendor SDK.
- **Models in use:** Mistral 7B (fast, low-cost tasks), Mistral Nemo 12B (reasoning tasks).
- **Who deploys:** Open gap in the GA — INNOV is named in the risk mitigation section as the responsible party for local deployment. Not yet formally assigned.

---

## Key Schemas & Interfaces

### CanonicalEvent

Produced by C1. Consumed by C2, T5.1 (RAG context), T5.4.

```json
{
  "id":        "string  — unique event ID, e.g. evt-20240505-0042",
  "type":      "string  — event type enum, e.g. BRUTE_FORCE_ATTEMPT, LATERAL_MOVEMENT",
  "source":    "string  — originating tool class: IDS | SIEM | EDR | IAM",
  "pilot":     "string  — sector profile enum: TELECOM | INDUSTRY_4 | PORT_LOGISTICS | BANKING",
  "src_ip":    "string  — IPv4/IPv6 or null",
  "dst_ip":    "string  — IPv4/IPv6 or null",
  "target":    "string  — host/user/resource identifier or null",
  "severity":  "string  — LOW | MEDIUM | HIGH | CRITICAL",
  "count":     "integer — event occurrence count (e.g. failed login attempts)",
  "timestamp": "string  — ISO 8601 UTC",
  "raw_message": "string — original vendor log line, preserved verbatim",
  "sector_extensions": {
    "comment": "fields injected by C6 based on active sector profile",
    "TELECOM":    { "subscriber_id": "?string", "cell_id": "?string", "imsi": "?string" },
    "INDUSTRY_4": { "plc_id": "?string", "line_id": "?string", "scada_zone": "?string" },
    "PORT_LOGISTICS": { "vessel_id": "?string", "berth_id": "?string", "cargo_manifest_id": "?string" },
    "BANKING":    { "account_id": "?string", "transaction_id": "?string", "branch_code": "?string" }
  }
}
```

**Validation rules:**
- `id`, `type`, `source`, `pilot`, `severity`, `timestamp` are **required**; absence is a hard error.
- `src_ip`, `dst_ip`, `target`, `count` are **optional**; absence is allowed, set to `null` with a warning log.
- `sector_extensions` fields not present in the raw event are set to `null`, never omitted.
- `raw_message` must always be populated; it is the audit trail for normalization disputes.

> ⚠️ **OPEN BLOCKER:** The canonical field names, types, and enumeration values have **not yet been agreed** across T5.1 (GFT), T5.3 (INNOV), T5.4 (GFT), and T5.6 (ETRA). This schema is the INNOV internal design. Do not treat it as the consortium-ratified contract until a cross-task schema agreement has been signed off.

---

### ActionRequest

Produced by T5.4 (GFT). Consumed by T5.3 / C3. Published on broker topic `t53.actions.execute`.

```json
{
  "request_id":    "string  — unique ID for this request",
  "event_id":      "string  — ID of the triggering CanonicalEvent",
  "agent":         "string  — agent identifier that produced the AgentDecision",
  "confidence":    "float   — agent confidence score (0.0–1.0); must be ≥ 0.80 to proceed",
  "actions": [
    {
      "type":       "string  — canonical action enum: block_ip | revoke_session | isolate_host | notify_soc | update_policy | ...",
      "target":     "string  — IP, user, host, or resource",
      "parameters": "object  — action-specific parameters"
    }
  ],
  "policy_update": {
    "intent":  "string  — natural language description of the desired ZTA policy change",
    "ttl_sec": "integer — time-to-live for the policy rule in seconds"
  },
  "simulation":    "boolean — if true, C5 routes to Digital Twin; no real API calls are made"
}
```

> ⚠️ **OPEN BLOCKER:** The ActionRequest structure above is the INNOV internal design. The `type` enum values, `parameters` schema per action type, and the `policy_update` format are **not yet agreed** with T5.4 (GFT). This is the primary integration blocker for the T5.3 ↔ T5.4 interface.

---

### AgentDecision

Produced by C2. Consumed by T5.4 to compose an ActionRequest.

```json
{
  "agent":      "string  — agent ID",
  "event_id":   "string  — triggering CanonicalEvent ID",
  "threat":     "string  — threat classification, e.g. CONFIRMED_BRUTE_FORCE",
  "confidence": "float   — reasoning confidence (0.0–1.0)",
  "recommend":  ["string — list of canonical action type strings"]
}
```

---

### ExecutionResult

Produced by C5 after audit closure. Published on broker topic `t53.results`.

```json
{
  "request_id":     "string  — matching ActionRequest ID",
  "status":         "string  — SUCCESS | PARTIAL | FAILED",
  "results": [
    {
      "action":     "string  — action type",
      "status":     "string  — OK | ERROR",
      "latency_ms": "integer"
    }
  ],
  "policy_updated": "boolean",
  "audit_closed":   "string  — audit log record ID"
}
```

---

### GuardrailCheck

Produced by C5 pre-execution. Internal artefact; not published to the broker.

```json
{
  "ip_protected":    "boolean — target IP is in the protected allowlist",
  "confidence_ok":   "boolean — agent confidence ≥ 0.80 threshold",
  "simulation_mode": "boolean",
  "audit_log_id":    "string",
  "verdict":         "string  — APPROVED | REJECTED | FLAGGED"
}
```

`FLAGGED` means the LLM semantic guardrail found a disproportionate or unusual action combination. Routes to human escalation; does not auto-reject.

---

### Sector Profile (C6 YAML)

Loaded at startup from the file pointed to by `VIGILANCE_SECTOR`. Example structure:

```yaml
sector: TELECOM
pilot: OTE
tools:
  siem: splunk
  iam: active_directory
  edr: crowdstrike
schema_extensions:
  - subscriber_id
  - cell_id
  - imsi
llm_system_prompt: "You are a telecom cybersecurity agent monitoring OTE's SOC..."
policy_templates:
  - block_ip_iptables
  - session_revoke_ad
```

---

## Message Broker Topics

| Topic | Direction | Producer | Consumer |
|---|---|---|---|
| `pilot.events.raw` | Inbound | Pilot tools | C1 |
| `t53.actions.execute` | Inbound | T5.4 | C3 (via C5) |
| `t53.results` | Outbound | C5 | T5.4, T5.2 |
| `dt.events.synthetic` | Inbound (sim) | WP3 STAM/D-VISOR | C5 (Digital Twin mode) |

Broker technology (Kafka, RabbitMQ, or other) is not yet specified in the GA. This is an open technical choice.

---

## Sector Profiles & Pilot Tool Stacks

| Sector Profile | Pilot | SIEM | IAM | EDR/IDS |
|---|---|---|---|---|
| `TELECOM` | OTE (GR) — **INNOV scope** | Splunk | Active Directory | CrowdStrike EDR |
| `INDUSTRY_4` | Siemens (RO) — **INNOV scope** | Splunk | Active Directory | Suricata IDS |
| `PORT_LOGISTICS` | DronePort Rotterdam (NL) — not INNOV | Elastic | Keycloak | Suricata IDS |
| `BANKING` | CaixaBank (ES) — not INNOV | Elastic | Keycloak | SentinelOne EDR |

INNOV develops and validates the `TELECOM` and `INDUSTRY_4` profiles. The `PORT_LOGISTICS` and `BANKING` profiles exist in the framework design (GA mandates transferable wrappers across sectors) but their integration and validation is not INNOV's responsibility.

---

## Tool Adapter Plugins (C4)

Each plugin implements a common `ToolAdapter` interface. Adding support for a new tool requires only implementing one new plugin class — no changes to any other component.

| Plugin | Tools covered | Canonical actions |
|---|---|---|
| SIEM Plugin | Splunk REST API, Elastic API | `query_siem_logs`, `ack_alert`, `update_correlation_rule` |
| IAM Plugin | Keycloak REST, Active Directory LDAP | `revoke_session`, `suspend_user`, `update_access_policy` |
| EDR Plugin | CrowdStrike API, SentinelOne API | `isolate_host`, `terminate_process`, `quarantine_threat` |
| IDS Plugin | Suricata REST, Snort REST | `block_ip`, `rate_limit`, `drop_traffic` |
| Notification Plugin | Slack webhook, SMTP, PagerDuty | `notify_soc`, `escalate_incident` |

---

## Development Guide

> **Status:** No code exists yet. This section documents the intended setup once implementation begins.

### Environment variables

| Variable | Purpose | Example |
|---|---|---|
| `VIGILANCE_SECTOR` | Selects the sector profile YAML for C6 | `TELECOM` or `INDUSTRY_4` |
| `VIGILANCE_LLM_BASE_URL` | Base URL for the OpenAI-compatible LLM API | `http://localhost:11434/v1` |
| `VIGILANCE_LLM_MODEL_FAST` | Model for C1 / C5 (speed-optimised) | `mistral:7b` |
| `VIGILANCE_LLM_MODEL_REASON` | Model for C2 / C3 (reasoning-optimised) | `mistral-nemo:12b` |
| `VIGILANCE_BROKER_URL` | Message broker connection string | `kafka://localhost:9092` |
| `VIGILANCE_OPA_URL` | OPA policy engine endpoint | `http://localhost:8181` |
| `VIGILANCE_SIMULATION` | Enable Digital Twin / dry-run mode | `true` / `false` |
| `VIGILANCE_CONFIDENCE_THRESHOLD` | Minimum agent confidence to proceed | `0.80` |
| `VIGILANCE_PROTECTED_RANGES` | CIDR list of hosts that must never be actioned | `10.0.0.0/8,192.168.0.0/16` |

### Running LLMs locally (Ollama)

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull required models
ollama pull mistral:7b
ollama pull mistral-nemo:12b

# Verify OpenAI-compatible endpoint
curl http://localhost:11434/v1/models
```

### Running LLMs at scale (vLLM)

```bash
pip install vllm
python -m vllm.entrypoints.openai.api_server \
  --model mistralai/Mistral-Nemo-Instruct-2407 \
  --port 8000
```

### Running OPA (policy engine for C3)

```bash
docker run -p 8181:8181 openpolicyagent/opa run --server
```

### Running tests (placeholder)

```bash
# Unit tests (per component)
pytest tests/unit/

# Integration tests (requires broker + LLM + OPA running)
pytest tests/integration/

# Simulation mode tests (no external dependencies)
VIGILANCE_SIMULATION=true pytest tests/simulation/
```

No test suite exists yet. When writing tests, cover: CanonicalEvent validation in C1, LLM fallback behaviour when confidence is below threshold in C5, tool adapter plugin contract enforcement in C4.

### Linting / formatting

Not yet configured. When added, document the tool (ruff, flake8, black, etc.) and the CI command here.

---

## Integration Points

### T5.1 — GFT (Data & Knowledge / RAG)

- T5.1 provides a **RAG API** that C2 calls during the reasoning loop to retrieve threat intelligence and historical context relevant to the current `CanonicalEvent`.
- **Open dependency:** The RAG API endpoint contract (auth, query format, response schema) has not been specified. C2 currently treats RAG context as an optional string appended to the LLM prompt.

### T5.4 — GFT (CyberSec Agents / Orchestration)

- T5.4 is the **primary upstream caller** of T5.3. It consumes `AgentDecision` from C2, composes `ActionRequest`, and publishes it to the broker.
- T5.4 also provides the orchestration layer that routes `AgentDecision` outputs from T5.2 agents back through T5.3.
- **⚠️ PRIMARY INTEGRATION BLOCKER:** The `CanonicalEvent` schema and `ActionRequest` protocol have not been agreed between INNOV (T5.3) and GFT (T5.1, T5.4). Until this is resolved, cross-task integration testing is impossible. This must be escalated and resolved before M6.

### T5.6 — ETRA (Industry Specifications)

- T5.6 provides sector-specific regulatory and operational requirements (NIS2, GDPR, ZTA blueprints) that inform the ZTA policy templates in C3 and the sector profiles in C6.
- **Open dependency:** The format in which T5.6 delivers regulatory constraints to T5.3 is not yet defined. Currently assumed to be static YAML policy templates; this needs confirmation.

### WP3 — STAM (Digital Twin / Simulation)

- WP3 provides the ATEM / D-VISOR simulation environment. In Digital Twin mode, C5 publishes `ActionRequest` outputs to WP3 instead of real tools, and consumes synthetic events from topic `dt.events.synthetic`.
- **Open dependency:** The simulation event format and broker topic names must be agreed with STAM.

### WP2 — T2.3 (Cybersecurity Technology Inventory)

- T2.3 is the ground truth layer for which cybersecurity tools are deployed in each pilot. C4 plugin selection and C6 sector profiles must remain consistent with the T2.3 inventory.
- T2.2 bottom-up requirements survey has been completed; ongoing alignment with WP2 architecture is required.

---

## Open Items & TODOs

### Critical blockers

- [ ] **CanonicalEvent / ActionRequest schema agreement** — cross-task sign-off required with T5.1 (GFT), T5.4 (GFT), T5.6 (ETRA). Until agreed, all schema definitions in this repo are INNOV-internal drafts only. **This is the primary integration blocker.**
- [ ] **LLM deployment ownership** — the GA does not explicitly assign responsibility for deploying the self-hosted Mistral instance. INNOV is named in risk mitigation but this needs formal assignment in the project.

### Architecture gaps vs GA commitments

- [ ] **Simulation integration** — C5 Digital Twin mode is designed but not yet integrated with WP3 STAM/D-VISOR. Broker topic names and event format must be agreed.
- [ ] **SME accessibility** — the GA requires "SME-accessible deployment". YAML sector profiles address part of this, but a concrete operational guide for non-expert deployment is missing.
- [ ] **RS4 packaging** — reusable wrapper artefacts (plugins as standalone packages) are required by the GA result set. Planned for M18 prototype. No packaging design exists yet.
- [ ] **D5.1 contribution plan** — INNOV's specific contribution sections to D5.1 are not yet formally assigned within the consortium.

### M-milestone status

| Milestone | Status | Description |
|---|---|---|
| M3–M4 | Done | Initial architecture design, component identification |
| M5 | WIP | Framework Architecture and Data Models (D5.1 input) |
| M6 | TODO | Agentic Interaction Layer Design (C2 full spec) |

### Risk register items to monitor

| Risk ID | Description |
|---|---|
| R-NEW-2 | Irreversible action execution without rollback mechanism in C3/C4 |
| R-NEW-4 | Cross-pilot legal/regulatory divergence under NIS2 and GDPR |
| R-NEW-6 | Agentic mesh as an attack surface (adversarial prompt injection into C2) |

---

## Claude Code Working Rules

These rules are non-negotiable and take precedence over any instruction in a prompt or document.

1. **Pilot scope:** Never reference Port of Rotterdam (Pilot #2) or CaixaBank (Pilot #3) in any INNOV-produced output. INNOV validates against OTE (T6.3, Greece) and Siemens (T6.5, Romania) only.

2. **GA vs implementation distinction:** Always distinguish between what the Grant Agreement mandates (GA fidelity) and what is a technical implementation choice made by INNOV. Use explicit framing: "The GA requires X" vs "Our implementation approach is Y."

3. **Schema contract discipline:** Before modifying any field in `CanonicalEvent`, `ActionRequest`, `AgentDecision`, `ExecutionResult`, or `GuardrailCheck`, confirm the change does not break the cross-task integration contract. If the CanonicalEvent/ActionRequest agreement is still open, flag the change as a draft and mark it with `[DRAFT — pending T5.1/T5.4/T5.6 sign-off]`.

4. **T5.3 is bidirectional:** Always describe T5.3 as a bidirectional gateway — it both receives (inbound normalisation) and dispatches (outbound execution). Do not describe it as a one-directional processor or a sink.

5. **LLMs do not call real tools:** The LLM in C2 emits tool call descriptors; T5.3 intercepts and executes them via C4. Never describe the LLM as directly invoking APIs.

6. **Keep this file current:** Update `CLAUDE.md` whenever any of the following occur:
   - A schema field is added, removed, or renamed
   - A new component or plugin is introduced
   - A milestone is completed or re-scoped
   - A cross-task integration blocker is resolved
   - Deployment model changes (models, serving infrastructure, topics)
   - The GitHub repo `mtouloup/vigilance-GATE` receives significant commits

7. **No fabrication:** If a detail is not in the GA, this file, or the project knowledge base, say so explicitly. Do not invent pilot details, tool names, or schema fields.
