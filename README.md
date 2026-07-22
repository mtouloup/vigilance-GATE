# vigilance-GATE

**VIGILANCE — T5.3: Agentic Wrapper Framework for Cybersecurity Technologies**

GAP project ref: GAP-101249737 | Lead: INNOV | Pilots: OTE · Siemens · Port of Rotterdam · CaixaBank

---

## Overview

`vigilance-gate` is the Python implementation of the T5.3 Agentic Wrapper Framework. It is the
operational execution bridge between the WP5 intelligence layer (T5.1 RAG, T5.2 agents,
T5.4 orchestration) and the real cybersecurity tools deployed across all four VIGILANCE pilot
environments.

It provides a **5-component pipeline** that ingests raw security events, enforces safety guardrails,
translates natural-language policy changes to OPA/Rego, and dispatches remediation actions —
operating exclusively in **INTEGRATED mode** alongside T5.4 (orchestration):

| Pilot | Sector | Partner | Threats |
|---|---|---|---|
| #1 | TELECOM | OTE_GR (Greece) | Credential stuffing, brute-force, SS7/BGP attacks |
| #2 | MARITIME | Rotterdam_NL (Netherlands) | AIS/GPS spoofing, cargo system intrusions, port IT/OT |
| #3 | FINANCE | CaixaBank_ES (Spain) | Account takeover, payment fraud, insider threats |
| #4 | INDUSTRY_4 | Siemens_RO (Romania) | OT anomalies, PLC lateral movement, SCADA zone isolation |

T5.3 is a **single multi-pilot container** that serves all four GA pilots simultaneously. Pilot
detection happens in C1 (parser heuristics + LLM fallback); the correct Sector Profile (C6) and
C4 tool adapter set are selected per-event automatically. No configuration change or restart
is needed to switch between pilots — all four profiles and adapter sets are loaded at startup.

---

## Architecture

```
                    ┌──────────────────────────────────────────────────────────┐
                    │  C6 — Sector Profile Manager (all 4 loaded at startup)    │
                    │  TELECOM · MARITIME · FINANCE · INDUSTRY_4                │
                    │  Selected per-event from pilot detected in C1             │
                    └──────────────┬───────────────────────────────────────────┘
                                   │ profile (per event)
   Message Broker                  ▼
   pilot.events.raw  ──►  C1  Ingestion & Normalization
                              CEF · ECS · OT JSON · Syslog · LLM fallback
                                   │ CanonicalEvent + NormalizationMeta
                                   ▼
                          t53.canonical_events  ──►  T5.4 Orchestrator
                                                         │ (calls T5.1 RAG, selects T5.2 agent)
                                                         ▼
                                               t53.action_requests
                                   │ ActionRequest
                                   ▼
                          C5  Safety Gate  (Mistral 7B — ESCALATE only)
                              ① confidence ≥ threshold  ② protected IP
                              ③ proportionality ≤ 5     ④⑤ OT safety (INDUSTRY_4)
                                   │ GuardrailCheck → APPROVED / REJECTED / ESCALATE
                                   ▼
                          C3  Policy Translation  (Mistral Nemo — conditional)
                              NL → OPA/Rego (few-shot + OPA validation + retry)
                                   │
                                   ├──► t53.policy_updates  ──► downstream consumer TBD
                                   └──► t53.actions.dispatch  ──► pilot tools (fire-and-forget)
                                             C4  Tool Adapter Layer  (no LLM)
                                                 OTE:       ote_siem · ote_iam · ote_ids
                                                 Rotterdam: port_siem · port_iam · port_ops
                                                 CaixaBank: bank_siem · bank_iam · fraud_engine
                                                 Siemens:   industrial_siem · ot_iam · scada_opcua
                                   ▼
                          C5  Audit Log + ExecutionResult
                              AuditLog per request · WorkflowCSVLogger → data/workflow_audit.csv
                                   │
   Message Broker  ◄──────────────┘
   t53.results  ──►  T5.4 (incident closure) · T5.2 (agent improvement)
```

---

## Components

| ID | Component | LLM | Role |
|---|---|---|---|
| C1 | Event Ingestion & Normalization | Mistral 7B (fallback only) | Parses CEF, ECS, OT JSON, syslog → `CanonicalEvent`; publishes to `t53.canonical_events` |
| C3 | Action & Policy Execution | Mistral Nemo 12B (conditional) | Receives `ActionRequest` from T5.4; compiles NL policy to OPA/Rego when `policy_update` present |
| C4 | Tool Adapter Layer | None | 12 plugin-based deterministic adapters for all four pilots; fire-and-forget via `t53.actions.dispatch` |
| C5 | Safety Gate & Audit | Mistral 7B (ESCALATE only) | Pre-execution guardrail (5 checks) + AuditLog + WorkflowCSVLogger |
| C6 | Sector Profile Manager | N/A | Loads 4 YAML profiles at startup; injects per-sector config into all components |

### LLM models

| Model | Size | Used by | When |
|---|---|---|---|
| `mistral:7b` | ~4 GB | C1, C5 | C1: only when no deterministic parser matches; C5: only when guardrail returns ESCALATE |
| `mistral-nemo` | ~7 GB | C3 | Only when the incoming `ActionRequest` includes a `policy_update` NL string |

On the happy path (known log format, confidence above threshold, no policy update) **zero LLM calls** are made.

Both models are served by **Ollama** and downloaded once into a persistent Docker volume.
When `OLLAMA_BASE_URL` is not set (local/test mode) the built-in `StubLLMProvider` is used —
no model download required, all tests run offline.

---

## Repository Structure

```
vigilance-GATE/
├── vigilance/                  Python package
│   ├── pipeline.py             T53Pipeline — main entry point
│   ├── service.py              Broker consumer service
│   ├── main.py                 Combined entrypoint: REST API + broker consumer
│   ├── workflow_logger.py      WorkflowCSVLogger — per-execution CSV audit trail
│   ├── api/
│   │   └── app.py              FastAPI REST API (port 8000)
│   ├── llm/
│   │   ├── base.py             LLMProvider ABC + StubLLMProvider (tests)
│   │   ├── ollama_provider.py  OllamaLLMProvider (mistral:7b + mistral-nemo)
│   │   └── __init__.py         create_llm() factory
│   ├── broker/
│   │   ├── base.py             BaseBroker ABC
│   │   ├── memory_broker.py    InMemoryBroker (tests / local)
│   │   ├── rabbitmq_broker.py  RabbitMQBroker (production)
│   │   └── __init__.py         create_broker() factory
│   ├── models/                 Pydantic v2 data models (frozen schema)
│   │   ├── canonical_event.py
│   │   ├── action_request.py
│   │   ├── execution_result.py
│   │   ├── guardrail_check.py
│   │   └── audit_record.py
│   └── components/
│       ├── c1_ingestion/       Normalizer + 5 parsers (CEF, ECS, OT JSON, Syslog, LLM)
│       ├── c3_execution/       ActionExecutor + PolicyTranslator (few-shot NL→Rego + OPA validation)
│       ├── c4_adapters/        ToolAdapter ABC + 12 plugins
│       │   ├── telecom/        ote_siem · ote_iam · ote_ids
│       │   ├── maritime/       port_siem · port_iam · port_ops
│       │   ├── finance/        bank_siem · bank_iam · fraud_engine
│       │   └── industry4/      industrial_siem · ot_iam · scada_opcua
│       ├── c5_safety/          SafetyGate + AuditLog
│       └── c6_profiles/        ProfileManager + SectorProfile dataclass
├── profiles/                   Sector YAML config files
│   ├── telecom.yaml            Pilot #1 OTE/GR
│   ├── maritime.yaml           Pilot #2 Rotterdam/NL
│   ├── finance.yaml            Pilot #3 CaixaBank/ES
│   └── industry4.yaml          Pilot #4 Siemens/RO
├── schemas/                    JSON Schema definitions
│   ├── models/                 Auto-generated from Pydantic models
│   ├── broker/topics.yaml      Broker integration interface spec
│   └── profiles/               Sector profile YAML schema
├── data/                       Generated output (mounted volume)
│   └── workflow_audit.csv      Per-execution pipeline telemetry (C1 → C5 → C3 → C4)
├── tools/
│   ├── publish_event.sh        Example producer script for pilot partners
│   └── simulate_t54.sh         Simulates T5.4 orchestrator (INTEGRATED mode testing)
├── infra/
│   └── rabbitmq/
│       ├── rabbitmq.conf       Loads definitions at broker startup
│       └── definitions.json    Pre-declares all queues, user, and permissions
├── tests/                      115 tests across 10 files
│   ├── test_c1_ingestion.py … test_c6_profiles.py
│   └── scenarios/
│       ├── test_scenario_a_ote.py          Full OTE end-to-end
│       ├── test_scenario_b_siemens.py      Full Siemens end-to-end
│       ├── test_scenario_c_rotterdam.py    Full Rotterdam end-to-end
│       └── test_scenario_d_caixabank.py    Full CaixaBank end-to-end
├── Dockerfile
└── docker-compose.yml
```

---

## Quick Start — Docker (Recommended)

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) ≥ 24
- [Docker Compose](https://docs.docker.com/compose/) v2 (bundled with Docker Desktop)
- ~12 GB free disk space for LLM models (`mistral:7b` ≈ 4 GB, `mistral-nemo` ≈ 7 GB)

### Start the Stack

```bash
docker compose up --build
```

On **first run** `ollama-init` downloads `mistral:7b` and `mistral-nemo` into the `ollama_data`
Docker volume. Subsequent runs reuse the cached models instantly.

Startup order enforced by healthchecks:
1. `rabbitmq` → healthy (queues pre-declared from `infra/rabbitmq/definitions.json`)
2. `ollama` → healthy (API responding)
3. `ollama-init` → exits 0 (models pulled)
4. `vigilance-gate` → starts, listens on `pilot.events.raw` and serves REST API on port 8000

| Container | Role |
|---|---|
| `vigilance-rabbitmq` | RabbitMQ 3.13 — queues pre-declared at startup |
| `vigilance-ollama` | Ollama LLM server — serves mistral:7b and mistral-nemo |
| `vigilance-ollama-init` | One-shot model downloader (exits after pull) |
| `vigilance-gate` | **T5.3 Agentic Wrapper Framework** — all four GA pilots in a single container |
| `vigilance-dozzle` | Real-time log viewer → http://localhost:9999 |

Generated files on your host:
- `./data/workflow_audit.csv` — one row per completed pipeline execution (see [Workflow Audit CSV](#workflow-audit-csv))

### Reuse Models Already on Your Host

```bash
OLLAMA_MODELS_DIR=~/.ollama docker compose up --build
```

### GPU Acceleration (NVIDIA)

Uncomment the `deploy.resources` block under the `ollama` service in `docker-compose.yml`:

```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: 1
          capabilities: [gpu]
```

---

## Send a Test Event

### Option A — `publish_event.sh` (recommended for pilot partners)

`tools/publish_event.sh` is the reference producer. It wraps the raw event and publishes via the
RabbitMQ Management HTTP API (no AMQP client required — just `curl`).

**Pilot #1 — OTE / TELECOM (Greece)**
```bash
# Credential stuffing / brute-force alert (CEF)
./tools/publish_event.sh \
  'CEF:0|OTE-IDS|SOCv3|2.0|200|AUTH_BRUTE_FORCE|9|src=91.108.4.12 dst=nms-01 cnt=230 nodes=3 app=SSH'

# SS7 signaling anomaly (syslog)
./tools/publish_event.sh \
  'Jan 15 03:22:11 ss7gw-01 SS7GW: ALERT src_gt=491760000000 dst=nms-01 msg_type=SRI_SM anomaly=location_tracking_attempt severity=HIGH'
```

**Pilot #2 — Port of Rotterdam / MARITIME (Netherlands)**
```bash
# AIS position spoofing (JSON)
./tools/publish_event.sh \
  '{"vessel_id":"VESSEL-042","ais_mmsi":"244820000","port_zone":"Berth-7","anomaly":"ais_position_spoofing","severity":"HIGH"}'

# Cargo system intrusion (JSON)
./tools/publish_event.sh \
  '{"vessel_id":"VESSEL-117","cargo_system_id":"CMS-ROT-04","port_zone":"Container-Terminal-A","anomaly":"unauthorized_cargo_manifest_access","severity":"CRITICAL"}'
```

**Pilot #3 — CaixaBank / FINANCE (Spain)**
```bash
# Account takeover attempt (JSON)
./tools/publish_event.sh \
  '{"account_id":"ACC-ES-0099182","transaction_id":"TXN-2026-887341","branch_id":"BCN-CENTRAL","anomaly":"account_takeover_attempt","fraud_score":0.94,"severity":"HIGH"}'

# High-value payment fraud (JSON)
./tools/publish_event.sh \
  '{"account_id":"ACC-ES-0041872","transaction_id":"TXN-2026-553901","branch_id":"MAD-NORTE","anomaly":"payment_fraud_high_value","fraud_score":0.91,"severity":"CRITICAL"}'
```

**Pilot #4 — Siemens / INDUSTRY_4 (Romania)**
```bash
# OT anomaly — OPC-UA register write out of range (OT JSON)
./tools/publish_event.sh \
  '{"plc":"PLC-07","line":"Line-3","protocol":"OPC-UA","anomaly":"register_write_out_of_range","severity":"CRITICAL"}'

# PLC lateral movement suspected (OT JSON)
./tools/publish_event.sh \
  '{"plc":"PLC-12","scada_zone":"Zone-B","protocol":"Modbus","anomaly":"unexpected_command_sequence","severity":"HIGH","ot_safety_flag":true}'
```

**Common options:**
```bash
# Point at a remote RabbitMQ instance
./tools/publish_event.sh -h broker.example.com -u myuser -P mypass \
  'CEF:0|OTE-IDS|SOCv3|2.0|100|AUTH_FAIL|5|src=10.1.2.3 dst=nms-02 cnt=10 app=SSH'
```

Run `./tools/publish_event.sh --help` for the full option reference.

### Option B — `rabbitmqadmin` (inside the broker container)

```bash
docker exec vigilance-rabbitmq \
  rabbitmqadmin publish exchange=amq.default \
    routing_key=pilot.events.raw \
    payload='{"raw":"CEF:0|OTE-IDS|SOCv3|2.0|200|AUTH_BRUTE_FORCE|9|src=91.108.4.12 dst=nms-01 cnt=230 nodes=3 app=SSH"}'
```

---

## Check Results

Results land in the `t53.results` queue:

```bash
docker exec vigilance-rabbitmq \
  rabbitmqadmin get queue=t53.results ackmode=ack_requeue_true
```

RabbitMQ management UI: [http://localhost:15672](http://localhost:15672) — `vigilance` / `vigilance`

---

## Stop the Stack

```bash
docker compose down          # stop containers, keep volumes (models + broker data)
docker compose down -v       # stop containers and delete all volumes
```

---

## Local Development (without Docker)

### Prerequisites

- Python 3.11+

### Install

```bash
pip install -e ".[dev]"
```

### Run Tests

Tests use `StubLLMProvider` and `InMemoryBroker` — no external services needed:

```bash
python -m pytest tests/ -v
```

End-to-end scenario tests only:

```bash
python -m pytest tests/scenarios/ -v
```

With coverage:

```bash
python -m pytest tests/ -v --cov=vigilance --cov-report=term-missing
```

### Run the Service Locally with Real LLM and RabbitMQ

**Step 1** — Start Ollama:

```bash
ollama pull mistral:7b
ollama pull mistral-nemo
```

**Step 2** — Start RabbitMQ with queue definitions:

```bash
docker run -d --name rabbitmq \
  -p 5672:5672 -p 15672:15672 \
  -v "$(pwd)/infra/rabbitmq/rabbitmq.conf:/etc/rabbitmq/rabbitmq.conf:ro" \
  -v "$(pwd)/infra/rabbitmq/definitions.json:/etc/rabbitmq/definitions.json:ro" \
  -v rabbitmq_data:/var/lib/rabbitmq \
  rabbitmq:3.13-management-alpine
```

**Step 3** — Start T5.3 (REST API + broker consumer, all pilots):

```bash
AMQP_URL=amqp://vigilance:vigilance@localhost:5672/ \
OLLAMA_BASE_URL=http://localhost:11434 \
python -m vigilance.main
```

Swagger UI: [http://localhost:8000/api/docs](http://localhost:8000/api/docs)

For broker-only (no REST API):
```bash
python -m vigilance.service
```

### Dry-Run Mode

```bash
VIGILANCE_DRY_RUN=true python -m vigilance.main
```

Or in Python:

```python
from vigilance.pipeline import T53Pipeline
pipeline = T53Pipeline(dry_run=True)
```

Dry-run: C5 guardrail and AuditLog run normally; broker dispatch is skipped; all `ActionResult.plugin` values are `"dry_run"`.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `AMQP_URL` | *(unset)* | RabbitMQ AMQP URL. Unset → InMemoryBroker (tests/local) |
| `OLLAMA_BASE_URL` | *(unset)* | Ollama API URL. Unset → StubLLMProvider (tests/local) |
| `OLLAMA_MODELS_DIR` | `ollama_data` (volume) | Bind-mount host model cache to skip download |
| `VIGILANCE_DRY_RUN` | *(unset)* | `true` → skip broker dispatch; logs actions only |
| `WORKFLOW_CSV_PATH` | `workflow_audit.csv` | Path for workflow audit CSV output |
| `API_HOST` | `0.0.0.0` | REST API bind address |
| `API_PORT` | `8000` | REST API port |

---

## Pipeline Architecture (INTEGRATED Mode)

T5.3 operates exclusively in INTEGRATED mode with two public pipeline methods:

**`ingest_event(raw)`** — C1: normalise the raw event into a `CanonicalEvent` and publish to `t53.canonical_events`. T5.4 then enriches it with T5.1 RAG context, selects a T5.2 agent, and dispatches an `ActionRequest` back to T5.3.

**`execute_action_request(dict)`** — C5+C3+C4: apply guardrails, optionally compile a NL policy update to OPA/Rego, dispatch actions to pilot tools via the broker, close the audit record, and return an `ExecutionResult`.

```
pilot.events.raw ──► C1 normalize ──► t53.canonical_events ──► T5.4 orchestrator
                                                                      │
t53.action_requests ◄──────────────────────────── T5.4 dispatches ActionRequest
       │
       ▼
C5 guardrail ──► C3 NL→Rego (conditional) ──► t53.policy_updates  ──► consumer TBD
                    │
                    ├──► t53.actions.dispatch  ──► pilot tools  (fire-and-forget)
                    └──► t53.results ──► T5.4 incident closure / T5.2 feedback

C5 AuditLog.close() + WorkflowCSVLogger.append() ──► data/workflow_audit.csv
```

### Broker Topics

| Topic | Direction | Description |
|---|---|---|
| `pilot.events.raw` | consumed | Raw events from pilot SIEM/IDS → C1 |
| `t53.canonical_events` | published | C1 output → T5.4 input |
| `t53.action_requests` | consumed | T5.4 output → C5+C3+C4 |
| `t53.policy_updates` | published | C3 NL→Rego output → downstream consumer TBD |
| `t53.actions.dispatch` | published | C4 fire-and-forget → pilot tools |
| `t53.results` | published | ExecutionResult → T5.4 incident closure, T5.2 feedback |

---

## REST API (T5.6 Integration)

T5.3 exposes a REST API on port **8000** for T5.6 Agentic ZTA Platform Integration and
any external system that cannot use the RabbitMQ broker directly.

### Endpoints

| Method | Path | Response | Description |
|---|---|---|---|
| `GET` | `/api/v1/health` | 200 | Liveness check — returns loaded pilots and timestamp |
| `GET` | `/api/v1/profiles` | 200 | All four sector profiles (plugins, thresholds, OT flags) |
| `POST` | `/api/v1/events` | **202 Accepted** | Submit raw event → C1 → `t53.canonical_events`; returns `event_id` and detected `pilot` |
| `POST` | `/api/v1/action-requests` | 200 / 207 | Submit `ActionRequest` → C5+C3+C4; returns `ExecutionResult` (+ `policy_translation` when Rego was generated) |

### Interactive Documentation

| UI | URL |
|---|---|
| **Swagger UI** | [http://localhost:8000/api/docs](http://localhost:8000/api/docs) |
| **ReDoc** | [http://localhost:8000/api/redoc](http://localhost:8000/api/redoc) |
| **OpenAPI JSON** | [http://localhost:8000/api/openapi.json](http://localhost:8000/api/openapi.json) |

### Example — Submit Event via REST

```bash
curl -X POST http://localhost:8000/api/v1/events \
  -H "Content-Type: application/json" \
  -d '{"raw": "CEF:0|OTE-IDS|SOCv3|2.0|200|AUTH_BRUTE_FORCE|9|src=91.108.4.12 dst=nms-01 cnt=230 nodes=3 app=SSH"}'

curl http://localhost:8000/api/v1/health
curl http://localhost:8000/api/v1/profiles
```

---

## Testing INTEGRATED Mode End-to-End

`tools/simulate_t54.sh` simulates the T5.4 orchestrator: consumes a `CanonicalEvent` from
`t53.canonical_events`, derives an appropriate `ActionRequest` for the detected sector, and
publishes it to `t53.action_requests` so T5.3 continues with C5+C3+C4.

**Full walkthrough:**

```bash
# Step 1 — start the stack
docker compose up --build

# Step 2 — send a raw event
./tools/publish_event.sh \
  'CEF:0|OTE-IDS|SOCv3|2.0|200|AUTH_BRUTE_FORCE|9|src=91.108.4.12 dst=nms-01 cnt=230 nodes=3 app=SSH'

# Step 3 — simulate T5.4
./tools/simulate_t54.sh --purge   # --purge clears stale events first

# Step 4 — check results
docker exec vigilance-rabbitmq \
  rabbitmqadmin get queue=t53.results ackmode=ack_requeue_true
```

**Manual dispatch (all 4 pilots):**

```bash
# TELECOM — OTE/Greece
./tools/simulate_t54.sh --no-consume \
  --event-id evt-ote-001 --pilot OTE_GR \
  --actions block_ip,revoke_session,notify_soc \
  --confidence 0.96

# MARITIME — Port of Rotterdam
./tools/simulate_t54.sh --no-consume \
  --event-id evt-rot-001 --pilot Rotterdam_NL \
  --actions block_vessel_access,quarantine_cargo_system,notify_port_authority,notify_soc \
  --confidence 0.88

# FINANCE — CaixaBank
./tools/simulate_t54.sh --no-consume \
  --event-id evt-cai-001 --pilot CaixaBank_ES \
  --actions freeze_account,block_transaction,notify_fraud_team,notify_soc \
  --confidence 0.93

# INDUSTRY_4 — Siemens/Romania (with NL policy update → Rego)
./tools/simulate_t54.sh --no-consume \
  --event-id evt-sie-001 --pilot Siemens_RO \
  --actions isolate_plc,revoke_ot_session,notify_soc,update_zt_policy \
  --confidence 0.91 \
  --policy "Deny all OPC-UA traffic from Zone-B to Zone-A for 4 hours"
```

Run `./tools/simulate_t54.sh --help` for the full option reference.

---

## Scenarios

### Scenario A — OTE Credential Stuffing (Pilot #1 · TELECOM)

**Threat:** 230 failed auth attempts from external IP on OTE Network Management System.

**Input (CEF):**
```
CEF:0|OTE-IDS|SOCv3|2.0|200|AUTH_BRUTE_FORCE|9|src=91.108.4.12 dst=nms-01 cnt=230 nodes=3 app=SSH
```

**Pipeline actions:** `block_ip` → `revoke_session` → `notify_soc`

**Audit ID:** `aud-OTE-0031`

---

### Scenario B — Siemens OT Anomaly (Pilot #4 · INDUSTRY_4)

**Threat:** Anomalous OPC-UA register writes on PLC-07 — suspected IT→OT lateral movement.

**Input (OT JSON):**
```json
{"plc": "PLC-07", "line": "Line-3", "protocol": "OPC-UA",
 "anomaly": "register_write_out_of_range", "severity": "CRITICAL"}
```

**Pipeline actions:** `isolate_plc` (safe-state enforced) → `revoke_ot_session` → `notify_soc` → `update_zt_policy`

**OT safety:** The SCADA plugin (`scada_opcua`) enforces `mode="safe-state"` on `isolate_plc`.
`ActionExecutor._build_params()` injects this automatically — T5.4 does not need to carry it.

**Audit ID:** `aud-SIE-0074`

---

### Scenario C — Port of Rotterdam AIS Spoofing (Pilot #2 · MARITIME)

**Threat:** AIS position spoofing on VESSEL-042 at Berth-7 — GPS coordinates inconsistent with radar.

**Input (JSON):**
```json
{"vessel_id": "VESSEL-042", "ais_mmsi": "244820000", "port_zone": "Berth-7",
 "anomaly": "ais_position_spoofing", "severity": "HIGH"}
```

**Pipeline actions:** `block_vessel_access` → `quarantine_cargo_system` → `notify_port_authority` → `notify_soc`

**Audit ID:** `aud-ROT-0001`

---

### Scenario D — CaixaBank Account Takeover (Pilot #3 · FINANCE)

**Threat:** Account takeover attempt on ACC-ES-0099182 — fraud score 0.94.

**Input (JSON):**
```json
{"account_id": "ACC-ES-0099182", "transaction_id": "TXN-2026-887341",
 "branch_id": "BCN-CENTRAL", "anomaly": "account_takeover_attempt",
 "fraud_score": 0.94, "severity": "HIGH"}
```

**Pipeline actions:** `freeze_account` → `block_transaction` → `notify_fraud_team` → `notify_soc`

**Note:** FINANCE uses `confidence_threshold: 0.85` (from `finance.yaml`) rather than the 0.80
default — higher bar for auto-action in regulated PSD2/DORA environments.

**Audit ID:** `aud-CAI-0001`

---

## C4 Adapter Vocabulary

All 12 adapters are stubs in the current implementation; real connections to pilot tools are planned for M10–M15.

### OTE (Telecom)

| `plugin_name` | Wrapped tool | `supported_actions` |
|---|---|---|
| `ote_siem` | Splunk | `block_ip`, `query_logs`, `create_incident` |
| `ote_iam` | Active Directory | `revoke_session`, `query_sessions` |
| `ote_ids` | CrowdStrike | `notify_soc` |

**Verb union:** `block_ip`, `query_logs`, `create_incident`, `revoke_session`, `query_sessions`, `notify_soc`

### Siemens (Industry 4.0)

| `plugin_name` | Wrapped tool | `supported_actions` |
|---|---|---|
| `scada_opcua` | OPC-UA SCADA | `isolate_plc`, `notify_soc`, `update_zt_policy` |
| `ot_iam` | OT IAM | `revoke_ot_session`, `query_sessions` |
| `industrial_siem` | Splunk | `query_logs`, `block_ip`, `create_incident` |

**Verb union:** `isolate_plc`, `notify_soc`, `update_zt_policy`, `revoke_ot_session`, `query_sessions`, `query_logs`, `block_ip`, `create_incident`

### Port of Rotterdam (Maritime)

| `plugin_name` | Wrapped tool | `supported_actions` |
|---|---|---|
| `port_siem` | Elastic SIEM | `block_vessel_access`, `query_logs`, `update_vessel_acl` |
| `port_iam` | Keycloak | `revoke_session`, `query_sessions`, `notify_soc` |
| `port_ops` | Port Operations | `quarantine_cargo_system`, `notify_port_authority`, `notify_soc`, `update_vessel_acl` |

**Verb union:** `block_vessel_access`, `query_logs`, `update_vessel_acl`, `revoke_session`, `query_sessions`, `notify_soc`, `quarantine_cargo_system`, `notify_port_authority`

### CaixaBank (Finance)

| `plugin_name` | Wrapped tool | `supported_actions` |
|---|---|---|
| `bank_siem` | Elastic SIEM | `query_logs`, `block_transaction`, `notify_soc` |
| `bank_iam` | Keycloak | `freeze_account`, `revoke_session`, `query_sessions` |
| `fraud_engine` | Fraud Engine | `block_transaction`, `notify_fraud_team`, `escalate_to_compliance`, `notify_soc` |

**Verb union:** `query_logs`, `block_transaction`, `notify_soc`, `freeze_account`, `revoke_session`, `query_sessions`, `notify_fraud_team`, `escalate_to_compliance`

---

## LLM Usage in T5.3

### Where LLMs Are Used

T5.3 makes **at most three conditional LLM calls** per event. Zero on the happy path.

| Component | Model | When invoked | What it does |
|---|---|---|---|
| **C1** | `mistral:7b` | No deterministic parser matched | Extracts CanonicalEvent fields from free-text or unknown log formats |
| **C5** | `mistral:7b` | Guardrail returns ESCALATE | Semantic second-opinion: `APPROVE` or `REJECT` with one-sentence reason |
| **C3** | `mistral-nemo` | `ActionRequest.policy_update` is set | Few-shot NL→Rego translation; OPA parse validation; single retry; fail-closed fallback |

### NL→Rego Pipeline (C3)

1. Build user message: four domain examples (OTE auth, Siemens network, OTE IAM, Siemens OT) + NL input
2. Call Mistral Nemo 12B
3. Strip markdown code fences
4. Validate with `opa parse` (if OPA binary available)
5. On failure: retry once with the parse error fed back to the model
6. On double failure: publish `package vigilance.fallback / default deny = true` (fail-closed)

Package naming convention: `vigilance.<pilot_lower>.<domain>` — e.g. `vigilance.ote.auth`, `vigilance.siemens.ot`

### Offline / Test Mode

When `OLLAMA_BASE_URL` is not set, `StubLLMProvider` is used automatically — deterministic
responses, no model required. All 115 tests pass offline with the stub.

---

## Workflow Audit CSV

`data/workflow_audit.csv` is written by `WorkflowCSVLogger` — one row per completed pipeline
execution. It is the primary observability surface for the current phase.

### Columns

| Column | Description |
|---|---|
| `timestamp` | ISO 8601 UTC at row write time |
| `event_id` | CanonicalEvent UUID |
| `pilot` | Detected sector |
| `severity` | Normalized severity |
| `raw_event` | Original input (JSON-encoded) |
| `parser_used` | CEF \| ECS \| OT_JSON \| Syslog \| LLM |
| `c1_llm_invoked` | True when LLM fallback ran in C1 |
| `c1_llm_fields` | Fields extracted by LLM, or empty |
| `canonical_event` | Full CanonicalEvent JSON |
| `request_id` | ActionRequest UUID from T5.4 |
| `actions_requested` | Pipe-separated action verb list |
| `agent_confidence` | Confidence value from T5.4 |
| `guardrail_verdict` | APPROVED \| REJECTED \| ESCALATE |
| `guardrail_reasons` | Pipe-separated guardrail reason strings |
| `c5_llm_invoked` | True when Mistral 7B semantic check ran |
| `c5_llm_response` | Raw LLM JSON response, or empty |
| `policy_update_nl` | NL policy input, or empty |
| `c3_llm_invoked` | True when Nemo 12B NL→Rego ran |
| `c3_rego_rule` | Generated Rego string, or empty |
| `actions_dispatched` | Pipe-separated dispatched actions |
| `overall_success` | True if all actions succeeded |
| `audit_id` | Internal AuditLog record ID |

---

## Schemas

Formal JSON Schema definitions for all data models and the broker integration interface:

```
schemas/
  models/                     JSON Schema auto-generated from Pydantic v2 models
    canonical_event.schema.json
    action_request.schema.json
    execution_result.schema.json
    guardrail_check.schema.json
    audit_record.schema.json
  broker/
    topics.yaml                Broker topics: direction, producers, consumers, payloads
  profiles/
    sector_profile.schema.yaml  Validates all four sector YAML profiles
```

See [`schemas/README.md`](schemas/README.md) for the pipeline data-flow table and schema
regeneration instructions.
