# vigilance-GATE

**VIGILANCE — T5.3: Agentic Wrapper Framework for Cybersecurity Technologies**

GAP project ref: GAP-101249737 | Lead: INNOV | Pilots: OTE · Siemens · Port of Rotterdam · CaixaBank

---

## Overview

`vigilance-gate` is the Python implementation of the T5.3 Agentic Wrapper Framework. It is the
operational execution bridge between the WP5 intelligence layer (T5.1 RAG, T5.2 agents,
T5.4 orchestration) and the real cybersecurity tools deployed across all four VIGILANCE pilot
environments.

It provides a 6-component pipeline that ingests raw security events, enforces safety guardrails,
and executes remediation actions — operating exclusively in **INTEGRATED mode** alongside T5.4
(orchestration) and T5.5 (ZTA blueprint refinement):

| Pilot | Sector | Partner | Threats |
|---|---|---|---|
| #1 | TELECOM | OTE_GR (Greece) | Credential stuffing, brute-force, SS7/BGP attacks |
| #2 | MARITIME | Rotterdam_NL (Netherlands) | AIS/GPS spoofing, cargo system intrusions, port IT/OT |
| #3 | FINANCE | CaixaBank_ES (Spain) | Account takeover, payment fraud, insider threats |
| #4 | INDUSTRY_4 | Siemens_RO (Romania) | OT anomalies, PLC lateral movement, SCADA zone isolation |

T5.3 is a **single multi-pilot container** that serves all four GA pilots simultaneously. Pilot
detection happens in C1 (parser heuristics + LLM fallback); the correct Sector Profile (C6) and
C4 tool adapter set are then selected per-event automatically. No configuration change or restart
is needed to switch between pilots — all four profiles and adapter sets are loaded at startup.

---

## Architecture

```
                    ┌──────────────────────────────────────────────────────┐
                    │  C6 — Sector Profile Manager (all 4 loaded at startup) │
                    │  TELECOM · MARITIME · FINANCE · INDUSTRY_4             │
                    │  Selected per-event from detected pilot in C1          │
                    └──────────────┬────────────────────────────────────────┘
                                   │ profile (per event)
   Message Broker                  ▼
   pilot.events.raw  ──►  C1  Ingestion & Normalization
                              CEF · ECS · OT JSON · Syslog · LLM fallback
                                   │ CanonicalEvent
                                   ▼
                          t53.canonical_events  ──►  T5.4 Orchestrator
                                                         │ (calls T5.1 RAG, selects T5.2 agent)
                                                         ▼
   Message Broker                          t53.action_requests
   t53.action_requests  ──────────────────────────────────┘
                                   │ ActionRequest
                                   ▼
                          C5  Safety Gate  (Mistral 7B — ESCALATE only)
                              confidence · protected IP · proportionality
                              OT safety gate (INDUSTRY_4)
                                   │ GuardrailCheck → APPROVED / REJECTED / ESCALATE
                                   ▼
                          C3  Action & Policy Execution  (Mistral Nemo — conditional)
                              NL → OPA/Rego policy translation (if policy_update present)
                                   │
                                   ├──► t53.policy_updates  ──► T5.5 ZTA blueprint refinement
                                   ├──► t53.actions.dispatch  ──► pilot tools (fire-and-forget)
                                   │       C4  Tool Adapter Layer  (no LLM)
                                   │           OTE:       SIEM · IAM · IDS
                                   │           Rotterdam: Port SIEM · Port IAM · Port Ops
                                   │           CaixaBank: Bank SIEM · Bank IAM · Fraud Engine
                                   │           Siemens:   SIEM · IAM · SCADA/OPC-UA
                                   ▼
                          C5  Audit Log + ExecutionResult
                              immutable · aud-OTE-* / aud-ROT-* / aud-CAI-* / aud-SIE-*
                                   │
   Message Broker  ◄──────────────┘
   t53.results
```

---

## Components

| ID | Component | LLM | Role |
|---|---|---|---|
| C1 | Event Ingestion & Normalization | Mistral 7B (fallback only) | Parses CEF, ECS, syslog, OT JSON → `CanonicalEvent`; publishes to `t53.canonical_events` |
| C3 | Action & Policy Execution | Mistral Nemo 12B (conditional) | Receives `ActionRequest` from T5.4; translates NL → OPA/Rego if `policy_update` present |
| C4 | Tool Adapter Layer | None | Plugin-based deterministic API calls to pilot tools (fire-and-forget via `t53.actions.dispatch`) |
| C5 | Safety Gate & Audit | Mistral 7B (ESCALATE only) | Pre-execution guardrail (confidence · IP range · proportionality · OT safety) + immutable audit log |
| C6 | Sector Profile Manager | N/A | Cross-cutting config: loads YAML profile at startup, injects into all components |

### LLM models

| Model | Size | Used by | When |
|---|---|---|---|
| `mistral:7b` | ~4 GB | C1, C5 | C1: only when no deterministic parser matches; C5: only when guardrail returns ESCALATE |
| `mistral-nemo` | ~7 GB | C3 | Only when the incoming `ActionRequest` includes a `policy_update` NL string |

On the happy path (known log format, APPROVED confidence, no policy update) **zero LLM calls** are made.

Both models are served by **Ollama** and downloaded once into a persistent Docker volume.
When `OLLAMA_BASE_URL` is not set (local/test mode) the built-in `StubLLMProvider` is used instead —
no model download required, all tests run offline.

---

## Repository structure

```
vigilance-GATE/
├── vigilance/                  Python package
│   ├── pipeline.py             T53Pipeline — main entry point
│   ├── service.py              Broker consumer service (all three run modes)
│   ├── main.py                 Combined entrypoint: REST API + broker consumer
│   ├── api/
│   │   └── app.py              FastAPI REST API (T5.6 integration point, port 8000)
│   ├── llm/
│   │   ├── base.py             LLMProvider ABC + StubLLMProvider (tests)
│   │   ├── ollama_provider.py  OllamaLLMProvider (mistral:7b + mistral-nemo)
│   │   └── __init__.py         create_llm() factory
│   ├── broker/
│   │   ├── base.py             BaseBroker ABC
│   │   ├── memory_broker.py    InMemoryBroker (tests / local)
│   │   ├── rabbitmq_broker.py  RabbitMQBroker (production)
│   │   └── __init__.py         create_broker() factory
│   ├── models/                 Pydantic v2 data models
│   │   ├── canonical_event.py
│   │   ├── action_request.py
│   │   ├── execution_result.py
│   │   ├── guardrail_check.py
│   │   └── audit_record.py
│   └── components/
│       ├── c1_ingestion/       Normalizer + 5 parsers (CEF, ECS, syslog, OT JSON, LLM)
│       ├── c3_execution/       ActionExecutor + PolicyTranslator
│       ├── c4_adapters/        ToolAdapter ABC + 12 plugins (OTE × 3, Rotterdam × 3, CaixaBank × 3, Siemens × 3)
│       ├── c5_safety/          SafetyGate + AuditLog
│       └── c6_profiles/        ProfileManager + SectorProfile dataclass
├── profiles/                   Sector YAML config files
│   ├── telecom.yaml            Pilot #1 OTE/GR: plugins, schema extensions, LLM prompt
│   ├── maritime.yaml           Pilot #2 Rotterdam/NL: port plugins, vessel schema, LLM prompt
│   ├── finance.yaml            Pilot #3 CaixaBank/ES: fraud plugins, account schema, LLM prompt
│   └── industry4.yaml          Pilot #4 Siemens/RO: OT plugins, ot_safety_flag, RAME prompt
├── schemas/                    JSON Schema definitions (see schemas/README.md)
│   ├── models/                 Auto-generated from Pydantic models
│   ├── broker/topics.json      Broker integration interface spec
│   └── profiles/               Sector profile YAML schema
├── tools/
│   ├── publish_event.sh        Example producer script for pilot partners
│   └── simulate_t54.sh         Simulates T5.4 orchestrator response (INTEGRATED mode testing)
├── infra/
│   └── rabbitmq/
│       ├── rabbitmq.conf       Loads definitions at broker startup
│       └── definitions.json    Pre-declares all queues, user, and permissions
├── tests/
│   ├── test_c1_ingestion.py … test_c6_profiles.py
│   └── scenarios/
│       ├── test_scenario_a_ote.py          Full OTE end-to-end (Scenario A)
│       ├── test_scenario_b_siemens.py      Full Siemens end-to-end (Scenario B)
│       ├── test_scenario_c_rotterdam.py    Full Rotterdam end-to-end (Scenario C)
│       └── test_scenario_d_caixabank.py    Full CaixaBank end-to-end (Scenario D)
├── Dockerfile
└── docker-compose.yml
```

---

## Quick Start — Docker (recommended)

The Agentic Wrapper Framework runs as a single container (`vigilance-gate`) alongside
RabbitMQ (message broker) and Ollama (LLM server).

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) ≥ 24
- [Docker Compose](https://docs.docker.com/compose/) v2 (bundled with Docker Desktop)
- ~12 GB free disk space for LLM models (`mistral:7b` ≈ 4 GB, `mistral-nemo` ≈ 7 GB)

### Start the stack

```bash
docker compose up --build
```

On **first run** the `ollama-init` container downloads `mistral:7b` and `mistral-nemo` into the
`ollama_data` Docker volume. Subsequent runs reuse the cached models instantly.

Startup order enforced by healthchecks:
1. `rabbitmq` → healthy (queues pre-declared from `infra/rabbitmq/definitions.json`)
2. `ollama` → healthy (API responding)
3. `ollama-init` → exits 0 (models pulled)
4. `vigilance-gate` → starts and listens on `pilot.events.raw`

| Container | Role |
|---|---|
| `vigilance-rabbitmq` | RabbitMQ 3.13 — queues pre-declared at startup |
| `vigilance-ollama` | Ollama LLM server — serves mistral:7b and mistral-nemo |
| `vigilance-ollama-init` | One-shot model downloader (exits after pull) |
| `vigilance-gate` | **T5.3 Agentic Wrapper Framework** — serves all four GA pilots in a single container |

No sector switch is needed. All four profiles (TELECOM, MARITIME, FINANCE, INDUSTRY_4) and their
C4 adapter sets are loaded at startup. The correct profile is selected per-event based on the
pilot detected by C1.

### Reuse models already on your host

If Ollama is already installed locally and models are in `~/.ollama`, skip the download:

```bash
OLLAMA_MODELS_DIR=~/.ollama docker compose up --build
```

### GPU acceleration (NVIDIA)

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

Then restart with `docker compose up --build`.

### Send a test event

#### Option A — example producer script (recommended for pilot partners)

`tools/publish_event.sh` is the reference producer that pilot partners can adapt into their
own log-shipping integration. It wraps the raw event and publishes it via the RabbitMQ
Management HTTP API (no AMQP client library required — just `curl`).

**Pilot #1 — OTE / TELECOM (Greece)**
```bash
# Credential stuffing / brute-force alert (CEF format)
./tools/publish_event.sh \
  'CEF:0|OTE-IDS|SOCv3|2.0|200|AUTH_BRUTE_FORCE|9|src=91.108.4.12 dst=nms-01 cnt=230 nodes=3 app=SSH'

# SS7 signaling anomaly (syslog format)
./tools/publish_event.sh \
  'Jan 15 03:22:11 ss7gw-01 SS7GW: ALERT src_gt=491760000000 dst=nms-01 msg_type=SRI_SM anomaly=location_tracking_attempt severity=HIGH'
```

**Pilot #2 — Port of Rotterdam / MARITIME (Netherlands)**
```bash
# AIS position spoofing (JSON format)
./tools/publish_event.sh \
  '{"vessel_id":"VESSEL-042","ais_mmsi":"244820000","port_zone":"Berth-7","anomaly":"ais_position_spoofing","severity":"HIGH"}'

# Cargo system intrusion (JSON format)
./tools/publish_event.sh \
  '{"vessel_id":"VESSEL-117","cargo_system_id":"CMS-ROT-04","port_zone":"Container-Terminal-A","anomaly":"unauthorized_cargo_manifest_access","severity":"CRITICAL"}'
```

**Pilot #3 — CaixaBank / FINANCE (Spain)**
```bash
# Account takeover attempt (JSON format)
./tools/publish_event.sh \
  '{"account_id":"ACC-ES-0099182","transaction_id":"TXN-2026-887341","branch_id":"BCN-CENTRAL","anomaly":"account_takeover_attempt","fraud_score":0.94,"severity":"HIGH"}'

# High-value payment fraud (JSON format)
./tools/publish_event.sh \
  '{"account_id":"ACC-ES-0041872","transaction_id":"TXN-2026-553901","branch_id":"MAD-NORTE","anomaly":"payment_fraud_high_value","fraud_score":0.91,"severity":"CRITICAL"}'
```

**Pilot #4 — Siemens / INDUSTRY_4 (Romania)**
```bash
# OT anomaly — OPC-UA register write out of range (JSON format)
./tools/publish_event.sh \
  '{"plc":"PLC-07","line":"Line-3","protocol":"OPC-UA","anomaly":"register_write_out_of_range","severity":"CRITICAL"}'

# PLC lateral movement suspected (JSON format)
./tools/publish_event.sh \
  '{"plc":"PLC-12","scada_zone":"Zone-B","protocol":"Modbus","anomaly":"unexpected_command_sequence","severity":"HIGH","ot_safety_flag":true}'
```

**Common options:**
```bash
# Point at a remote RabbitMQ instance
./tools/publish_event.sh -h broker.example.com -u myuser -P mypass \
  'CEF:0|OTE-IDS|SOCv3|2.0|100|AUTH_FAIL|5|src=10.1.2.3 dst=nms-02 cnt=10 app=SSH'

# Inject a WP3 D-VISOR synthetic event into the Digital Twin queue
./tools/publish_event.sh -q dt.events.synthetic \
  '{"plc":"PLC-01","anomaly":"voltage_spike","severity":"HIGH"}'
```

Run `./tools/publish_event.sh --help` for the full option reference.

#### Option B — rabbitmqadmin (inside the running broker container)

**Pilot #1 — OTE / TELECOM**
```bash
docker exec vigilance-rabbitmq \
  rabbitmqadmin publish exchange=amq.default \
    routing_key=pilot.events.raw \
    payload='{"raw":"CEF:0|OTE-IDS|SOCv3|2.0|200|AUTH_BRUTE_FORCE|9|src=91.108.4.12 dst=nms-01 cnt=230 nodes=3 app=SSH"}'
```

**Pilot #2 — Port of Rotterdam / MARITIME**
```bash
docker exec vigilance-rabbitmq \
  rabbitmqadmin publish exchange=amq.default \
    routing_key=pilot.events.raw \
    payload='{"raw":{"vessel_id":"VESSEL-042","ais_mmsi":"244820000","port_zone":"Berth-7","anomaly":"ais_position_spoofing","severity":"HIGH"}}'
```

**Pilot #3 — CaixaBank / FINANCE**
```bash
docker exec vigilance-rabbitmq \
  rabbitmqadmin publish exchange=amq.default \
    routing_key=pilot.events.raw \
    payload='{"raw":{"account_id":"ACC-ES-0099182","transaction_id":"TXN-2026-887341","branch_id":"BCN-CENTRAL","anomaly":"account_takeover_attempt","fraud_score":0.94,"severity":"HIGH"}}'
```

**Pilot #4 — Siemens / INDUSTRY_4**
```bash
docker exec vigilance-rabbitmq \
  rabbitmqadmin publish exchange=amq.default \
    routing_key=pilot.events.raw \
    payload='{"raw":{"plc":"PLC-07","line":"Line-3","protocol":"OPC-UA","anomaly":"register_write_out_of_range","severity":"CRITICAL"}}'
```

### Check results

Results land in the `t53.results` queue. View them in the management UI or consume via:

```bash
docker exec vigilance-rabbitmq \
  rabbitmqadmin get queue=t53.results ackmode=ack_requeue_true
```

### RabbitMQ management UI

[http://localhost:15672](http://localhost:15672) — username: `vigilance`, password: `vigilance`

### Stop the stack

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

### Run tests

Tests use `StubLLMProvider` and `InMemoryBroker` — no external services needed:

```bash
python -m pytest tests/ -v
```

Run only the end-to-end scenario tests:

```bash
python -m pytest tests/scenarios/ -v
```

With coverage:

```bash
python -m pytest tests/ -v --cov=vigilance --cov-report=term-missing
```

### Run the service locally with real LLM and RabbitMQ

**Step 1** — Start Ollama (if not already running):

```bash
# Install from https://ollama.com, then pull the required models
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

**Step 3** — Start the T5.3 service (handles all pilots, includes REST API on port 8000):

```bash
AMQP_URL=amqp://vigilance:vigilance@localhost:5672/ \
OLLAMA_BASE_URL=http://localhost:11434 \
python -m vigilance.main
```

Swagger UI will be available at [http://localhost:8000/api/docs](http://localhost:8000/api/docs).

For broker-only (no REST API):
```bash
python -m vigilance.service
```

### Dry-run mode

The pipeline supports a dry-run flag for development and testing (no real tool calls executed):

```python
from vigilance.pipeline import T53Pipeline

# Dry-run: logs all decisions and actions, executes nothing (all pilots)
pipeline = T53Pipeline(dry_run=True)
```

Or via environment variable:

```bash
VIGILANCE_DRY_RUN=true python -m vigilance.main
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `VIGILANCE_DRY_RUN` | *(unset)* | Set to `true` to skip real tool execution (logs actions only). Useful for development. |
| `AMQP_URL` | *(unset)* | RabbitMQ AMQP URL. Unset → in-memory broker (tests/local) |
| `OLLAMA_BASE_URL` | *(unset)* | Ollama API URL. Unset → StubLLMProvider (tests/local). Docker: `http://ollama:11434` |
| `OLLAMA_MODELS_DIR` | `ollama_data` (volume) | Override to bind-mount host model cache (e.g. `~/.ollama`) and skip download |
| `API_HOST` | `0.0.0.0` | REST API bind address |
| `API_PORT` | `8000` | REST API port |

---

## Pipeline Architecture (INTEGRATED)

T5.3 operates exclusively in **INTEGRATED** mode. It has two public pipeline methods:

1. **`ingest_event(raw)`** — C1: normalise the raw event into a `CanonicalEvent` and publish to `t53.canonical_events`. T5.4 (orchestrator, lead: GFT) then enriches it with T5.1 RAG context, selects a T5.2 agent, and dispatches an `ActionRequest` back.

2. **`execute_action_request(dict)`** — C5+C3+C4: apply guardrails, optionally translate a NL policy update to OPA/Rego, dispatch actions to pilot tools, write an immutable audit record, and return an `ExecutionResult`.

```
pilot.events.raw ──► C1 normalize ──► t53.canonical_events ──► T5.4 orchestrator
                                                                      │ T5.1 RAG + T5.2 agent
                                                                      ▼
t53.action_requests ◄────────────────────────────── T5.4 dispatches ActionRequest
       │
       ▼
C5 guardrail ──► C3 policy ──► t53.policy_updates  ──► T5.5 (ZTA blueprint refinement, async)
                    │
                    ├──► t53.actions.dispatch  ──► pilot tools  (fire-and-forget)
                    └──► t53.results
```

T5.3 publishes to `t53.policy_updates` and `t53.actions.dispatch` and returns immediately.
T5.5 (STAM — ZTA blueprint refinement) and the pilot tools consume in their own time —
T5.3 is never blocked waiting for them.

| Broker topic | Direction | Description |
|---|---|---|
| `pilot.events.raw` | consumed | Raw events from pilot SIEM/IDS → C1 |
| `t53.canonical_events` | published | C1 output → T5.4 input |
| `t53.action_requests` | consumed | T5.4 output → C5+C3+C4 |
| `t53.policy_updates` | published | C3 NL→Rego output → T5.5 ZTA blueprint refinement |
| `t53.actions.dispatch` | published | C4 fire-and-forget → pilot tools |
| `t53.results` | published | ExecutionResult → T5.4 incident closure |
| `dt.events.synthetic` | (reserved) | WP3 D-VISOR synthetic events (post-M18) |

---

## REST API (T5.6 Integration)

T5.3 exposes a REST API on port **8000** for T5.6 Agentic ZTA Platform Integration and
any external system that cannot use the RabbitMQ broker directly.

### Interactive documentation

| UI | URL |
|---|---|
| **Swagger UI** | [http://localhost:8000/api/docs](http://localhost:8000/api/docs) |
| **ReDoc** | [http://localhost:8000/api/redoc](http://localhost:8000/api/redoc) |
| **OpenAPI JSON** | [http://localhost:8000/api/openapi.json](http://localhost:8000/api/openapi.json) |

### Endpoints

| Method | Path | Response | Description |
|---|---|---|---|
| `GET` | `/api/v1/health` | 200 | Liveness / readiness check — returns loaded pilots and timestamp |
| `GET` | `/api/v1/profiles` | 200 | List all sector profiles (tool plugins, thresholds, OT flags) |
| `POST` | `/api/v1/events` | **202 Accepted** | Submit a raw event — runs C1 normalization and publishes to `t53.canonical_events`; returns `event_id` and detected `pilot` |
| `POST` | `/api/v1/action-requests` | 200 / 207 | Submit an `ActionRequest` for C5+C3+C4 execution — for T5.4 or external orchestrators; returns `ExecutionResult` |

### Example — submit event via REST

```bash
# C1 normalization — always returns 202 Accepted with event_id and detected pilot
curl -X POST http://localhost:8000/api/v1/events \
  -H "Content-Type: application/json" \
  -d '{"raw": "CEF:0|OTE-IDS|SOCv3|2.0|200|AUTH_BRUTE_FORCE|9|src=91.108.4.12 dst=nms-01 cnt=230 nodes=3 app=SSH"}'

# MARITIME event
curl -X POST http://localhost:8000/api/v1/events \
  -H "Content-Type: application/json" \
  -d '{"raw": {"vessel_id":"VESSEL-042","ais_mmsi":"244820000","port_zone":"Berth-7","anomaly":"ais_position_spoofing","severity":"HIGH"}}'
```

```bash
# Health check
curl http://localhost:8000/api/v1/health

# List profiles
curl http://localhost:8000/api/v1/profiles
```

---

### Testing INTEGRATED mode end-to-end

`tools/simulate_t54.sh` simulates the T5.4 orchestrator: it consumes the next
`CanonicalEvent` from `t53.canonical_events`, derives an appropriate `ActionRequest`
for the detected sector, and publishes it to `t53.action_requests` so T5.3 continues
with C5 guardrail + C3+C4 execution.

**Full walkthrough:**

```bash
# Step 1 — start the stack
docker compose up --build

# Step 2 — send a raw event (T5.3 normalises it and publishes CanonicalEvent)
./tools/publish_event.sh \
  'CEF:0|OTE-IDS|SOCv3|2.0|200|AUTH_BRUTE_FORCE|9|src=91.108.4.12 dst=nms-01 cnt=230 nodes=3 app=SSH'

# Step 3 — simulate T5.4 consuming the CanonicalEvent and dispatching ActionRequest
# Use --purge to clear any stale events from a previous run (avoids event_id mismatch)
./tools/simulate_t54.sh --purge

# Step 4 — check the ExecutionResult in t53.results
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

# INDUSTRY_4 — Siemens/Romania (with OT policy update for NL→Rego translation)
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

### Scenario B — Siemens OT Anomaly (Pilot #4 · INDUSTRY_4)

**Threat:** Anomalous OPC-UA register writes on PLC-07 — suspected IT→OT lateral movement.

**Input (OT JSON):**
```json
{"plc": "PLC-07", "line": "Line-3", "protocol": "OPC-UA",
 "anomaly": "register_write_out_of_range", "severity": "CRITICAL"}
```

**Pipeline actions:** `isolate_plc` (safe-state) → `revoke_ot_session` → `notify_soc` → `update_zt_policy`

**OT safety:** The SCADA plugin enforces safe-state-first — `isolate_plc` raises `ValueError` if
`mode="safe-state"` is not passed. C3 always passes this automatically.

**Audit ID:** `aud-SIE-0074`

### Scenario C — Port of Rotterdam AIS Spoofing (Pilot #2 · MARITIME)

**Threat:** AIS position spoofing detected on VESSEL-042 at Berth-7 — GPS coordinates inconsistent
with radar tracking; suspected maritime cyber intrusion.

**Input (JSON):**
```json
{"vessel_id": "VESSEL-042", "ais_mmsi": "244820000", "port_zone": "Berth-7",
 "anomaly": "ais_position_spoofing", "severity": "HIGH"}
```

**Pipeline actions:** `block_vessel_access` → `quarantine_cargo_system` → `notify_port_authority` → `notify_soc`

**Audit ID:** `aud-ROT-0001`

### Scenario D — CaixaBank Account Takeover (Pilot #3 · FINANCE)

**Threat:** Account takeover attempt on ACC-ES-0099182 — fraud score 0.94, anomalous login from
unknown device followed by high-value transaction attempt.

**Input (JSON):**
```json
{"account_id": "ACC-ES-0099182", "transaction_id": "TXN-2026-887341",
 "branch_id": "BCN-CENTRAL", "anomaly": "account_takeover_attempt",
 "fraud_score": 0.94, "severity": "HIGH"}
```

**Pipeline actions:** `freeze_account` → `block_transaction` → `notify_fraud_team` → `notify_soc`

**Note:** FINANCE sector uses a higher confidence threshold (0.85 vs 0.80) to reduce false positives
in regulated financial environments (PSD2, DORA).

**Audit ID:** `aud-CAI-0001`

---

## LLM Usage in T5.3

This section documents exactly where and how the Agentic Wrapper Framework uses the
two LLM models, in fulfilment of the GA promises for T5.3.

### Where LLMs are used

T5.3 makes **at most three conditional LLM calls** per event. Zero LLM calls on the happy path.

| Component | Model | When invoked | What it does |
|---|---|---|---|
| **C1 — Ingestion** | `mistral:7b` | Only when CEF/ECS/syslog/OT-JSON parsers all fail | Extracts CanonicalEvent fields (severity, pilot, src_ip, target, etc.) from arbitrary free-text or unknown log formats |
| **C3 — Policy Execution** | `mistral-nemo` | Only when `ActionRequest.policy_update` is set | Translates the NL policy description into an OPA/Rego rule and publishes to `t53.policy_updates` |
| **C5 — Safety Gate** | `mistral:7b` | Only when a rule-based guardrail check returns `ESCALATE` | Semantic second-opinion: given the proposed actions and guardrail flags, decides `APPROVE` or `REJECT` |

### LLM call chain per event (INTEGRATED mode)

```
ActionRequest arrives from T5.4
      │
      ▼
C5 ──[rule checks: confidence / IP range / proportionality / OT safety]──► APPROVED / REJECTED
   ──[mistral:7b, ESCALATE only]──► semantic_check() → APPROVE|REJECT
      │
      ▼ (if APPROVED)
C3 ──[mistral-nemo, only if policy_update present]──► generate_rego_policy()
      │
      ▼
C4 ──► pilot tools (fire-and-forget via t53.actions.dispatch)

C1 (separate thread, pilot.events.raw):
C1 ──[mistral:7b, only if no deterministic parser matches]──► extract_fields() → CanonicalEvent
```

### What is guaranteed (GA promises fulfilled)

- **mistral:7b in C1**: `LLMParser` fallback handles free-text alerts, unknown SIEM formats, and future pilot log schemas without schema changes.
- **Pilot resolution**: A single multi-pilot instance. Parsers detect the pilot from event content; `T53Pipeline._profile_for(pilot)` selects the matching `SectorProfile` and C4 adapter set. If pilot remains `UNKNOWN`, the TELECOM profile is used as a last resort with a warning. The OT JSON parser is the only parser that hard-codes `pilot="INDUSTRY_4"` — gated on `plc`/`protocol` keys.
- **mistral:7b in C5 semantic guardrail**: `SafetyGate._semantic_review()` uses the fast model for ESCALATE cases only — keeping latency low on the critical execution path.
- **mistral-nemo in C3 NL→Rego**: `PolicyTranslator` generates OPA/Rego policy rules for ZTA enforcement when the incoming `ActionRequest` carries a `policy_update` field.

### Offline / test mode

When `OLLAMA_BASE_URL` is not set, the framework uses `StubLLMProvider` automatically:
- `complete()` → deterministic multi-turn responses ending in a sector-appropriate decision
- `semantic_check()` → always returns `APPROVE` with a proportionality justification
- `extract_fields()` → heuristic extraction from keywords in the raw text

No LLM server required. All tests pass offline with the stub provider.

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
    topics.json               Broker topics: direction, producers, consumers, payloads
  profiles/
    sector_profile.schema.json  Validates all four sector YAML profiles
```

See [`schemas/README.md`](schemas/README.md) for the pipeline data-flow table and schema
regeneration instructions.
