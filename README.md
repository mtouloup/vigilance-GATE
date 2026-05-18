# vigilance-GATE

**VIGILANCE — T5.3: Agentic Wrapper Framework for Cybersecurity Technologies**

GAP project ref: GAP-101249737 | Lead: INNOV | Pilots: OTE · Siemens · Port of Rotterdam · CaixaBank

---

## Overview

`vigilance-gate` is the Python implementation of the T5.3 Agentic Wrapper Framework. It is the
operational execution bridge between the WP5 intelligence layer (T5.1 RAG, T5.2 agents,
T5.4 orchestration) and the real cybersecurity tools deployed across all four VIGILANCE pilot
environments.

It provides a 6-component pipeline that ingests raw security events, applies agentic LLM-driven
reasoning, enforces safety guardrails, and executes remediation actions:

| Pilot | Sector | Partner | Threats |
|---|---|---|---|
| #1 | TELECOM | OTE_GR (Greece) | Credential stuffing, brute-force, SS7/BGP attacks |
| #2 | MARITIME | Rotterdam_NL (Netherlands) | AIS/GPS spoofing, cargo system intrusions, port IT/OT |
| #3 | FINANCE | CaixaBank_ES (Spain) | Account takeover, payment fraud, insider threats |
| #4 | INDUSTRY_4 | Siemens_RO (Romania) | OT anomalies, PLC lateral movement, SCADA zone isolation |

The active pilot is selected at startup via `VIGILANCE_SECTOR`. The pipeline (C1→C2→C5→C3→C4→C5)
is identical for all sectors — what changes is the Sector Profile (C6) and the C4 tool plugins.

---

## Architecture

```
                    ┌─────────────────────────────────────────┐
                    │  C6 — Sector Profile Manager             │
                    │  VIGILANCE_SECTOR = TELECOM|MARITIME|FINANCE|INDUSTRY_4  │
                    │  Injects: schema · plugins · LLM prompt  │
                    └──────────────┬──────────────────────────┘
                                   │ config
   Message Broker                  ▼
   pilot.events.raw  ──►  C1  Ingestion & Normalization
                              CEF · ECS · OT JSON · Syslog · LLM fallback
                                   │ CanonicalEvent
                                   ▼
                          C2  Agentic Layer  (Mistral Nemo 12B)
                              multi-turn tool-calling loop
                              RAME co-pilot for Siemens Pilot #4
                                   │ AgentDecision
                                   ▼
                          C5  Safety Gate  (Mistral 7B)
                              confidence · protected IP · proportionality
                              OT safety gate (Siemens only)
                                   │ GuardrailCheck → APPROVED / REJECTED / ESCALATE
                                   ▼
                          C3  Action & Policy Execution
                              NL → OPA/Rego policy translation
                                   │ ActionRequest
                                   ▼
                          C4  Tool Adapter Layer  (no LLM)
                              OTE:       SIEM · IAM · IDS
                              Rotterdam: Port SIEM · Port IAM · Port Ops
                              CaixaBank: Bank SIEM · Bank IAM · Fraud Engine
                              Siemens:   SIEM · IAM · SCADA/OPC-UA
                                   │ ExecutionResult
                                   ▼
                          C5  Audit Log
                              immutable · aud-OTE-* / aud-ROT-* / aud-CAI-* / aud-SIE-*
                                   │
   Message Broker  ◄──────────────┘
   t53.results
```

---

## Components

| ID | Component | LLM | Role |
|---|---|---|---|
| C1 | Event Ingestion & Normalization | Mistral 7B (fallback only) | Parses CEF, ECS, syslog, OT JSON → `CanonicalEvent` |
| C2 | Agentic Interaction Layer | Mistral Nemo 12B | Multi-turn tool-calling loop; RAME co-pilot for Siemens |
| C3 | Action & Policy Execution | Mistral Nemo 12B (conditional) | Dispatches `ActionRequest`; translates NL → OPA/Rego |
| C4 | Tool Adapter Layer | None | Plugin-based deterministic API calls to pilot tools |
| C5 | Safety, Audit & Simulation | Mistral 7B (partial) | Pre-execution guardrail · immutable audit log · dry-run/digital twin |
| C6 | Sector Profile Manager | N/A | Cross-cutting config: loads YAML profile at startup, injects into all components |

### LLM models

| Model | Size | Used by | Purpose |
|---|---|---|---|
| `mistral:7b` | ~4 GB | C1, C5 | Fast extraction of unknown log formats; semantic guardrail on edge cases |
| `mistral-nemo` | ~7 GB | C2, C3 | Multi-step reasoning, tool-calling, RAME co-pilot, NL→Rego translation |

Both models are served by **Ollama** and downloaded once into a persistent Docker volume.
When `OLLAMA_BASE_URL` is not set (local/test mode) the built-in `StubLLMProvider` is used instead —
no model download required, all tests run offline.

---

## Repository structure

```
vigilance-GATE/
├── vigilance/                  Python package
│   ├── pipeline.py             T53Pipeline — main entry point
│   ├── service.py              Service loop (subscribes to broker, runs pipeline)
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
│   │   ├── agent_decision.py
│   │   ├── execution_result.py
│   │   ├── guardrail_check.py
│   │   └── audit_record.py
│   └── components/
│       ├── c1_ingestion/       Normalizer + 5 parsers (CEF, ECS, syslog, OT JSON, LLM)
│       ├── c2_agentic/         AgentLoop + tool definitions
│       ├── c3_execution/       ActionExecutor + PolicyTranslator
│       ├── c4_adapters/        ToolAdapter ABC + 12 plugins (OTE × 3, Rotterdam × 3, CaixaBank × 3, Siemens × 3)
│       ├── c5_safety/          SafetyGate + AuditLog + SimulationMode
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

### Start the stack (TELECOM sector — default)

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
| `vigilance-gate` | **T5.3 Agentic Wrapper Framework** — active sector set by `VIGILANCE_SECTOR` |

### Switch sector

```bash
VIGILANCE_SECTOR=TELECOM     docker compose up --build   # Pilot #1 — OTE / Greece (default)
VIGILANCE_SECTOR=MARITIME    docker compose up --build   # Pilot #2 — Port of Rotterdam / Netherlands
VIGILANCE_SECTOR=FINANCE     docker compose up --build   # Pilot #3 — CaixaBank / Spain
VIGILANCE_SECTOR=INDUSTRY_4  docker compose up --build   # Pilot #4 — Siemens / Romania
```

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

**Step 3** — Start a sector worker:

```bash
VIGILANCE_SECTOR=TELECOM \
AMQP_URL=amqp://vigilance:vigilance@localhost:5672/ \
OLLAMA_BASE_URL=http://localhost:11434 \
python -m vigilance.service
```

### Simulation / dry-run mode

The pipeline supports two simulation modes (no real tool calls executed):

```python
from vigilance.pipeline import T53Pipeline

# Dry-run: logs all decisions and actions, executes nothing
pipeline = T53Pipeline(sector="TELECOM", dry_run=True)

# Digital twin: accepts synthetic events from WP3 D-VISOR
pipeline = T53Pipeline(sector="INDUSTRY_4", simulation_mode=True)
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `VIGILANCE_SECTOR` | `TELECOM` | Active sector profile: `TELECOM` \| `MARITIME` \| `FINANCE` \| `INDUSTRY_4` |
| `VIGILANCE_MODE` | `STANDALONE` | Pipeline mode: `STANDALONE` or `INTEGRATED` (see below) |
| `AMQP_URL` | *(unset)* | RabbitMQ AMQP URL. Unset → in-memory broker (tests/local) |
| `OLLAMA_BASE_URL` | *(unset)* | Ollama API URL. Unset → StubLLMProvider (tests/local). Docker: `http://ollama:11434` |
| `OLLAMA_MODELS_DIR` | `ollama_data` (volume) | Override to bind-mount host model cache (e.g. `~/.ollama`) and skip download |

---

## Pipeline Modes

### STANDALONE (default)

The full pipeline runs inside `vigilance-gate`: C1 → C2 → C5 → C3+C4.
C2 uses Mistral Nemo 12B for internal agentic reasoning and produces the ActionRequest itself.
The CanonicalEvent is also published to `t53.canonical_events` for observability.

```bash
VIGILANCE_MODE=STANDALONE docker compose up --build
```

```
pilot.events.raw ──► C1 normalize ──► C2 reason ──► C5 guardrail ──► C3+C4 execute ──► t53.results
                                       │
                                       └──► t53.canonical_events  (observability)
```

### INTEGRATED (WP5 full workflow)

T5.3 handles only ingestion (C1) and execution (C5+C3+C4).
T5.4 (orchestrator, lead: GFT) sits in the middle: it consumes CanonicalEvents,
calls T5.1 RAG for threat context, selects the right agent from T5.2, and dispatches
the ActionRequest back to T5.3 for guardrail + execution.

```bash
VIGILANCE_MODE=INTEGRATED docker compose up --build
```

```
pilot.events.raw ──► C1 normalize ──► t53.canonical_events ──► T5.4 orchestrator
                                                                      │ calls T5.1 RAG
                                                                      │ selects agent (T5.2)
                                                                      ▼
t53.action_requests ◄────────────────────────────── T5.4 dispatches ActionRequest
       │
       ▼
C5 guardrail ──► C3+C4 execute ──► t53.results ──► T5.4 closes incident
```

| Broker topic | STANDALONE | INTEGRATED |
|---|---|---|
| `pilot.events.raw` | consumed (full pipeline) | consumed (C1 only) |
| `t53.canonical_events` | published (observability) | published (T5.4 input) |
| `t53.action_requests` | not used | consumed (T5.4 output → C5+C3+C4) |
| `t53.results` | published | published |

### Testing INTEGRATED mode end-to-end

`tools/simulate_t54.sh` simulates the T5.4 orchestrator: it consumes the next
`CanonicalEvent` from `t53.canonical_events`, derives an appropriate `ActionRequest`
for the detected sector, and publishes it to `t53.action_requests` so T5.3 continues
with C5 guardrail + C3+C4 execution.

**Full walkthrough:**

```bash
# Step 1 — start the stack in INTEGRATED mode
VIGILANCE_MODE=INTEGRATED docker compose up --build

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

| Component | Model | When invoked | What it does |
|---|---|---|---|
| **C1 — Ingestion** | `mistral:7b` | When CEF/ECS/syslog parsers cannot parse the raw event | Extracts all CanonicalEvent fields (type, severity, pilot, src_ip, target, vessel_id, account_id, etc.) from arbitrary free-text or unknown log formats |
| **C2 — Agentic Loop** | `mistral-nemo` | Every event | Multi-turn tool-calling loop: calls `query_siem_logs`, `query_iam_sessions`, `query_threat_intel` in sequence, then produces the final `AgentDecision` (threat type + proposed actions + confidence score) |
| **C3 — Policy Execution** | `mistral-nemo` | When NL→Rego translation is needed | Translates natural-language action descriptions into OPA/Rego policy rules for ZTA enforcement |
| **C5 — Safety Gate** | `mistral:7b` | When a rule-based guardrail check returns ESCALATE | Semantic second-opinion review: given the proposed actions and the guardrail flags, decides APPROVE or REJECT. Upgrades ESCALATE→APPROVED when proportionate, keeps ESCALATE or downgrades to REJECTED otherwise |

### LLM call chain per event (STANDALONE mode)

```
Raw event arrives
      │
      ▼
C1 ──[mistral:7b, only if needed]──► extract_fields(raw_text, fields) → CanonicalEvent
      │
      ▼
C2 ──[mistral-nemo, turn 1]──► tool_call: query_siem_logs(target, window_min)
   ──[mistral-nemo, turn 2]──► tool_call: query_iam_sessions(target)
   ──[mistral-nemo, turn 3]──► decision: {threat, actions, confidence}
      │
      ▼
C3 ──[mistral-nemo, only if NL→Rego needed]──► generate_rego_policy(nl_description)
      │
      ▼
C5 ──[rule checks: confidence / IP range / proportionality / OT safety]
   ──[mistral:7b, only if ESCALATE]──► semantic_check(context, proposed_actions) → APPROVE|REJECT
```

### What is guaranteed (GA promises fulfilled)

- **mistral:7b in C1**: The `LLMParser` fallback calls `llm.extract_fields()` which routes to the fast model. This handles free-text alerts, unknown SIEM formats, and future pilot log schemas without schema changes.
- **mistral-nemo in C2**: `AgentLoop` calls `llm.complete()` in a multi-turn loop (up to 10 turns, configurable). Each turn the model either calls a tool or produces a final decision. The RAME co-pilot integration for INDUSTRY_4 is provided via the sector-specific C2 system prompt in `profiles/industry4.yaml`.
- **mistral:7b in C5 semantic guardrail**: `SafetyGate._semantic_review()` calls `llm.semantic_check()` using the fast model for borderline cases — not the heavy reasoning model — keeping latency low for the most time-sensitive path.
- **mistral-nemo in C3 NL→Rego**: `PolicyTranslator` calls `llm.complete()` to generate OPA/Rego policy rules for ZTA enforcement, triggered when the AgentDecision includes a `policy_update` field.

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
    agent_decision.schema.json
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
