# vigilance-GATE

**VIGILANCE — T5.3: Agentic Wrapper Framework for Cybersecurity Technologies**

GAP project ref: GAP-101249737 | Lead: INNOV | Pilots: OTE (Telecom/GR) · Siemens (Industry 4.0/RO)

---

## Overview

`vigilance-gate` is a Python package implementing the T5.3 Agentic Wrapper Framework. It provides a 6-component pipeline that ingests raw security events, applies agentic LLM-driven reasoning, enforces safety guardrails, and executes remediation actions across two pilot sectors:

- **OTE_GR (Telecom)** — credential stuffing, brute-force, SS7/BGP attacks
- **Siemens_RO (Industry 4.0)** — OT anomalies, PLC lateral movement, SCADA zone isolation

---

## Architecture

```
Raw Event  (CEF / ECS / OT JSON / Syslog)
   │
   ▼
C1  Ingestion & Normalization   deterministic parsers + LLM fallback
   │
   ▼
C2  Agentic Layer               multi-turn tool-calling loop (RAME co-pilot for Siemens)
   │
   ▼
C5  Safety Gate                 confidence threshold · protected IP · proportionality · OT checks
   │
   ▼
C3  Action Execution            policy translation (NL → OPA/Rego) + adapter dispatch
   │
   ▼
C4  Tool Adapters               OTE: SIEM / IAM / IDS   |   Siemens: SIEM / IAM / SCADA
   │
   ▼
C5  Audit Log                   immutable, append-only (aud-OTE-* / aud-SIE-*)
   │
   ▼
Message Broker  ──►  t53.results
```

**C6 Profile Manager** loads `profiles/telecom.yaml` or `profiles/industry4.yaml` at startup,
controlled by the `VIGILANCE_SECTOR` environment variable (default: `TELECOM`).

**Message Broker** defaults to an in-memory broker for local/test use. Set `AMQP_URL` to connect
to RabbitMQ in production.

**LLM backend** defaults to the built-in stub provider (no dependencies, used for tests).
Set `OLLAMA_BASE_URL` to connect to a real Ollama instance. The Docker stack includes Ollama
and pulls the required models automatically.

---

## Quick Start — Docker (recommended)

The full stack (RabbitMQ + Ollama + both sector workers) runs with a single command.

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) ≥ 24
- [Docker Compose](https://docs.docker.com/compose/) v2 (bundled with Docker Desktop)
- ~12 GB free disk space for LLM models (`mistral:7b` ≈ 4 GB, `mistral-nemo` ≈ 7 GB)

### Start the stack

```bash
docker compose up --build
```

On **first run** the `ollama-init` container downloads `mistral:7b` and `mistral-nemo`
into the `ollama_data` Docker volume. Subsequent runs reuse the cached models instantly.

This starts five containers:

| Container | Role |
|---|---|
| `vigilance-rabbitmq` | RabbitMQ 3.13 — queues pre-declared at startup via `infra/rabbitmq/definitions.json` |
| `vigilance-ollama` | Ollama LLM server (mistral:7b + mistral-nemo) |
| `vigilance-ollama-init` | One-shot model downloader (exits after pull) |
| `vigilance-telecom` | T5.3 pipeline — TELECOM sector (OTE/GR) |
| `vigilance-industry4` | T5.3 pipeline — INDUSTRY_4 sector (Siemens/RO) |

Service workers start only after RabbitMQ is healthy **and** models are downloaded.

### Reuse models already on your host

If Ollama is installed locally and models are already in `~/.ollama`, skip the download entirely:

```bash
OLLAMA_MODELS_DIR=~/.ollama docker compose up --build
```

### GPU acceleration (NVIDIA)

Uncomment the `deploy.resources` block in `docker-compose.yml` under the `ollama` service,
then restart:

```bash
docker compose up --build
```

### Send a test event

Publish a raw event to the `pilot.events.raw` queue and the appropriate worker will process it:

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

Results are published to the `t53.results` queue.

### RabbitMQ management UI

Open [http://localhost:15672](http://localhost:15672) in a browser.

| Field | Value |
|---|---|
| Username | `vigilance` |
| Password | `vigilance` |

### Stop the stack

```bash
docker compose down          # stop containers, keep RabbitMQ data volume
docker compose down -v       # stop containers and delete the data volume
```

### Run only one sector

```bash
docker compose up rabbitmq vigilance-telecom --build
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

```bash
python -m pytest tests/ -v
```

Tests run entirely in-memory — no RabbitMQ required.

To run only the end-to-end scenario tests:

```bash
python -m pytest tests/scenarios/ -v
```

With coverage:

```bash
python -m pytest tests/ -v --cov=vigilance --cov-report=term-missing
```

### Run the service locally (with RabbitMQ)

Start RabbitMQ separately (e.g. via Docker):

```bash
docker run -d --name rabbitmq \
  -p 5672:5672 -p 15672:15672 \
  -e RABBITMQ_DEFAULT_USER=vigilance \
  -e RABBITMQ_DEFAULT_PASS=vigilance \
  rabbitmq:3.13-management-alpine
```

Then start a sector worker:

```bash
VIGILANCE_SECTOR=TELECOM \
AMQP_URL=amqp://vigilance:vigilance@localhost:5672/ \
python -m vigilance.service
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `VIGILANCE_SECTOR` | `TELECOM` | Active sector profile: `TELECOM` or `INDUSTRY_4` |
| `AMQP_URL` | *(unset)* | RabbitMQ connection URL. Unset = in-memory broker |
| `OLLAMA_BASE_URL` | *(unset)* | Ollama API URL. Unset = stub LLM (for tests). Set to `http://localhost:11434` locally or `http://ollama:11434` in Docker |
| `OLLAMA_MODELS_DIR` | `ollama_data` (Docker volume) | Host path to mount as Ollama model cache. Set to `~/.ollama` to reuse existing host models |

---

## Scenario A — OTE Credential Stuffing

**Threat:** Credential stuffing attack on OTE Network Management System.

**Input (CEF):**
```
CEF:0|OTE-IDS|SOCv3|2.0|200|AUTH_BRUTE_FORCE|9|src=91.108.4.12 dst=nms-01 cnt=230 nodes=3 app=SSH
```

**Pipeline output:** `block_ip` + `revoke_session` + `notify_soc` — all succeed.

**Audit ID:** `aud-OTE-0031`

---

## Scenario B — Siemens OT Anomaly

**Threat:** Anomalous OPC-UA register writes on PLC-07 — suspected IT→OT lateral movement.

**Input (OT JSON):**
```json
{"plc": "PLC-07", "line": "Line-3", "protocol": "OPC-UA",
 "anomaly": "register_write_out_of_range", "severity": "CRITICAL"}
```

**Pipeline output:** `isolate_plc` (safe-state enforced) + `revoke_ot_session` + `notify_soc` + `update_zt_policy` — all succeed.

**Audit ID:** `aud-SIE-0074`

---

## Schemas

Formal JSON Schema definitions for all data models and the broker integration interface live in [`schemas/`](schemas/README.md):

- `schemas/models/` — `CanonicalEvent`, `ActionRequest`, `AgentDecision`, `ExecutionResult`, `GuardrailCheck`, `AuditRecord`
- `schemas/broker/topics.json` — broker topics, directions, producers, consumers, payload formats
- `schemas/profiles/sector_profile.schema.json` — sector profile YAML validation schema

---

## Notes

- All LLM responses are **stub/hardcoded** — no API keys required.
- All C4 adapter "HTTP calls" are stubs with realistic simulated latencies.
- The SCADA plugin enforces OT safety: `isolate_plc` raises `ValueError` unless `mode="safe-state"` is passed. The C3 executor always passes this parameter automatically.
- Audit IDs start at `aud-OTE-0031` for Telecom and `aud-SIE-0074` for Industry 4.0, matching the spec examples in the T5.3 Architecture & Workflow document (v3.0).
