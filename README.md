# vigilance-GATE

**VIGILANCE — T5.3: Agentic Wrapper Framework for Cybersecurity Technologies**

GAP project ref: GAP-101249737

---

## Overview

`vigilance-gate` is a Python package implementing the T5.3 Agentic Wrapper Framework. It provides a 6-component pipeline that ingests raw security events, applies agentic LLM-driven reasoning, enforces safety guardrails, and executes remediation actions across two pilot sectors:

- **OTE_GR (Telecom)** — credential stuffing, brute-force, SS7/BGP attacks
- **Siemens_RO (Industry 4.0)** — OT anomalies, PLC lateral movement, SCADA zone isolation

---

## Architecture

```
Raw Event
   │
   ▼
C1 Ingestion & Normalization  (CEF / ECS / OT JSON / Syslog / LLM fallback)
   │
   ▼
C2 Agentic Layer              (multi-turn tool-calling loop, StubLLM)
   │
   ▼
C5 Safety Gate                (confidence, protected IP, proportionality, OT checks)
   │
   ▼
C3 Action Execution           (policy translation + adapter dispatch)
   │
   ▼
C4 Tool Adapters              (OTE: SIEM/IAM/IDS  |  Siemens: SIEM/IAM/SCADA)
   │
   ▼
C5 Audit Log                  (immutable, append-only)
   │
   ▼
Broker → t53.results
```

**C6 Profile Manager** loads `profiles/telecom.yaml` or `profiles/industry4.yaml` at startup
(controlled by `VIGILANCE_SECTOR` env var, default: `TELECOM`).

---

## Installation

```bash
pip install -e ".[dev]"
```

Requires Python 3.11+.

---

## Running Tests

```bash
python -m pytest tests/ -v
```

To run only the end-to-end scenario tests:

```bash
python -m pytest tests/scenarios/ -v
```

To run with coverage:

```bash
python -m pytest tests/ -v --cov=vigilance --cov-report=term-missing
```

---

## Scenario A — OTE Credential Stuffing

Input: CEF brute-force alert from OTE IDS
```
CEF:0|OTE-IDS|SOCv3|2.0|200|AUTH_BRUTE_FORCE|9|src=91.108.4.12 dst=nms-01 cnt=230 nodes=3 app=SSH
```

Expected outcome: `block_ip` + `revoke_session` + `notify_soc` all succeed.

## Scenario B — Siemens OT Anomaly

Input: OT JSON from Siemens PLC monitoring
```json
{"plc": "PLC-07", "line": "Line-3", "protocol": "OPC-UA",
 "anomaly": "register_write_out_of_range", "severity": "CRITICAL"}
```

Expected outcome: `isolate_plc` (safe-state enforced) + `revoke_ot_session` + `notify_soc` + `update_zt_policy` all succeed.

---

## Notes

- All LLM responses are **stub/hardcoded** — no real API calls are made.
- All C4 adapter "HTTP calls" are stubs with realistic simulated latencies.
- The SCADA plugin enforces OT safety: `isolate_plc` raises `ValueError` unless `mode="safe-state"` is passed. The C3 executor always passes this parameter.
- Audit IDs start at `aud-OTE-0031` for Telecom and `aud-SIE-0074` for Industry 4.0, matching spec examples.
