# T5.3 Schemas

Formal schema definitions for all inter-component data models and integration interfaces used by the T5.3 Agentic Wrapper Framework.

---

## Directory structure

```
schemas/
  models/              JSON Schema for every Pydantic data model
  broker/              Message broker integration interface (topics & payloads)
  profiles/            Sector profile YAML schema (C6 configuration)
```

---

## Data models (`schemas/models/`)

These schemas define the canonical data structures that flow between T5.3 components. They are auto-generated from the Pydantic v2 models in `vigilance/models/`.

| File | Pydantic model | Produced by | Consumed by |
|---|---|---|---|
| `canonical_event.schema.json` | `CanonicalEvent` | C1 Ingestion | C2 Agentic, C5 Safety |
| `action_request.schema.json` | `ActionRequest` | T53Pipeline | C5 Safety, C3 Execution |
| `agent_decision.schema.json` | `AgentDecision` | C2 Agentic | T53Pipeline |
| `execution_result.schema.json` | `ExecutionResult` | C3 Execution | C5 Audit, broker `t53.results` |
| `action_result.schema.json` | `ActionResult` | C4 Adapters | C3 Execution (aggregated) |
| `guardrail_check.schema.json` | `GuardrailCheck` | C5 Safety Gate | T53Pipeline, C5 Audit |
| `audit_record.schema.json` | `AuditRecord` | C5 Audit Log | EC D5.1/D5.2 reporting |

### Pipeline data flow

```
raw event
  → [C1] → CanonicalEvent
  → [C2] → AgentDecision
  → [pipeline] → ActionRequest
  → [C5] → GuardrailCheck
  → [C3] → (per action) ActionResult
  → [C3] → ExecutionResult
  → [C5] → AuditRecord  +  broker t53.results
```

---

## Broker integration interface (`schemas/broker/topics.json`)

Describes the three RabbitMQ topics (queue names), their direction, producers, consumers, and payload formats.

| Topic | Direction | Description |
|---|---|---|
| `pilot.events.raw` | **inbound** | Raw events from OTE SIEM / Siemens SCADA / WP3 Digital Twin |
| `t53.results` | **outbound** | `ExecutionResult` after full pipeline processing |
| `dt.events.synthetic` | **inbound** | WP3 D-VISOR synthetic events for Digital Twin simulation mode |

---

## Sector profile schema (`schemas/profiles/sector_profile.schema.json`)

JSON Schema for the YAML profile files in `profiles/`. Defines all valid fields, types, and constraints for TELECOM and INDUSTRY_4 profiles loaded by C6.

---

## Regenerating model schemas

If data models change, regenerate the JSON Schema files:

```bash
python - <<'EOF'
import json, pathlib
from vigilance.models.canonical_event import CanonicalEvent
from vigilance.models.action_request import ActionRequest
from vigilance.models.agent_decision import AgentDecision
from vigilance.models.execution_result import ExecutionResult, ActionResult
from vigilance.models.guardrail_check import GuardrailCheck
from vigilance.models.audit_record import AuditRecord

base = pathlib.Path("schemas/models")
models = {
    "canonical_event": CanonicalEvent, "action_request": ActionRequest,
    "agent_decision": AgentDecision, "execution_result": ExecutionResult,
    "action_result": ActionResult, "guardrail_check": GuardrailCheck,
    "audit_record": AuditRecord,
}
for name, model in models.items():
    schema = model.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"https://vigilance-gate/schemas/models/{name}.schema.json"
    (base / f"{name}.schema.json").write_text(json.dumps(schema, indent=2))
    print(f"updated {name}.schema.json")
EOF
```
