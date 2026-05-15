# vigilance-GATE

**VIGILANCE — T5.3: Agentic Wrapper Framework for Cybersecurity Technologies**

GAP project ref: GAP-101249737 | Lead: INNOV | Pilots: OTE (Telecom/GR) · Siemens (Industry 4.0/RO)

---

## Overview

`vigilance-gate` is the Python implementation of the T5.3 Agentic Wrapper Framework. It is the
operational execution bridge between the WP5 intelligence layer (T5.1 RAG, T5.2 agents,
T5.4 orchestration) and the real cybersecurity tools deployed in the two INNOV pilot environments.

It provides a 6-component pipeline that ingests raw security events, applies agentic LLM-driven
reasoning, enforces safety guardrails, and executes remediation actions:

- **OTE_GR (Telecom/Greece)** — credential stuffing, brute-force, SS7/BGP attacks
- **Siemens_RO (Industry 4.0/Romania)** — OT anomalies, PLC lateral movement, SCADA zone isolation

---

## Architecture

```
                    ┌─────────────────────────────────────────┐
                    │  C6 — Sector Profile Manager             │
                    │  VIGILANCE_SECTOR = TELECOM|INDUSTRY_4   │
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
                              OTE:     SIEM · IAM · IDS
                              Siemens: SIEM · IAM · SCADA/OPC-UA
                                   │ ExecutionResult
                                   ▼
                          C5  Audit Log
                              immutable · aud-OTE-* / aud-SIE-*
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
no model download required, all 73 tests run offline.

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
│       ├── c4_adapters/        ToolAdapter ABC + 6 plugins (OTE × 3, Siemens × 3)
│       ├── c5_safety/          SafetyGate + AuditLog + SimulationMode
│       └── c6_profiles/        ProfileManager + SectorProfile dataclass
├── profiles/                   Sector YAML config files
│   ├── telecom.yaml            OTE/GR: plugins, schema extensions, LLM prompt
│   └── industry4.yaml          Siemens/RO: OT plugins, ot_safety_flag, RAME prompt
├── schemas/                    JSON Schema definitions (see schemas/README.md)
│   ├── models/                 Auto-generated from Pydantic models
│   ├── broker/topics.json      Broker integration interface spec
│   └── profiles/               Sector profile YAML schema
├── tools/
│   └── publish_event.sh        Example producer script for pilot partners
├── infra/
│   └── rabbitmq/
│       ├── rabbitmq.conf       Loads definitions at broker startup
│       └── definitions.json    Pre-declares all queues, user, and permissions
├── tests/
│   ├── test_c1_ingestion.py … test_c6_profiles.py
│   └── scenarios/
│       ├── test_scenario_a_ote.py      Full OTE end-to-end (Scenario A)
│       └── test_scenario_b_siemens.py  Full Siemens end-to-end (Scenario B)
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

### Switch to INDUSTRY_4 sector (Siemens)

```bash
VIGILANCE_SECTOR=INDUSTRY_4 docker compose up --build
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

```bash
# OTE brute-force alert (CEF string)
./tools/publish_event.sh \
  'CEF:0|OTE-IDS|SOCv3|2.0|200|AUTH_BRUTE_FORCE|9|src=91.108.4.12 dst=nms-01 cnt=230 nodes=3 app=SSH'

# Siemens OT anomaly (JSON object — wrapped automatically as {"raw": {...}})
./tools/publish_event.sh \
  '{"plc":"PLC-07","line":"Line-3","protocol":"OPC-UA","anomaly":"register_write_out_of_range","severity":"CRITICAL"}'

# Point at a remote RabbitMQ instance
./tools/publish_event.sh -h broker.example.com -u myuser -P mypass \
  'CEF:0|OTE-IDS|SOCv3|2.0|100|AUTH_FAIL|5|src=10.1.2.3 dst=nms-02 cnt=10 app=SSH'

# Inject a WP3 D-VISOR synthetic event into the Digital Twin queue
./tools/publish_event.sh -q dt.events.synthetic \
  '{"plc":"PLC-01","anomaly":"voltage_spike","severity":"HIGH"}'
```

Run `./tools/publish_event.sh --help` for the full option reference.

#### Option B — rabbitmqadmin (inside the running broker container)

```bash
# OTE credential-stuffing alert (CEF format)
docker exec vigilance-rabbitmq \
  rabbitmqadmin publish exchange=amq.default \
    routing_key=pilot.events.raw \
    payload='{"raw":"CEF:0|OTE-IDS|SOCv3|2.0|200|AUTH_BRUTE_FORCE|9|src=91.108.4.12 dst=nms-01 cnt=230 nodes=3 app=SSH"}'

# Siemens OT anomaly (JSON format)
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
| `VIGILANCE_SECTOR` | `TELECOM` | Active sector profile: `TELECOM` or `INDUSTRY_4` |
| `AMQP_URL` | *(unset)* | RabbitMQ AMQP URL. Unset → in-memory broker (tests/local) |
| `OLLAMA_BASE_URL` | *(unset)* | Ollama API URL. Unset → StubLLMProvider (tests/local). Docker: `http://ollama:11434` |
| `OLLAMA_MODELS_DIR` | `ollama_data` (volume) | Override to bind-mount host model cache (e.g. `~/.ollama`) and skip download |

---

## Scenarios

### Scenario A — OTE Credential Stuffing (Pilot #1)

**Threat:** 230 failed auth attempts from external IP on OTE Network Management System.

**Input (CEF):**
```
CEF:0|OTE-IDS|SOCv3|2.0|200|AUTH_BRUTE_FORCE|9|src=91.108.4.12 dst=nms-01 cnt=230 nodes=3 app=SSH
```

**Pipeline actions:** `block_ip` → `revoke_session` → `notify_soc`

**Audit ID:** `aud-OTE-0031`

### Scenario B — Siemens OT Anomaly (Pilot #4)

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
    sector_profile.schema.json  Validates telecom.yaml / industry4.yaml
```

See [`schemas/README.md`](schemas/README.md) for the pipeline data-flow table and schema
regeneration instructions.
