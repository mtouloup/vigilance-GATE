# T5.3 Schemas

Formal schema definitions for all inter-component data models and integration
interfaces used by the T5.3 Agentic Wrapper Framework.

---

## Directory structure

```
schemas/
  models/              JSON Schema (auto-generated from Pydantic models)
  broker/topics.yaml   Broker integration interface — topics, direction, payloads
  profiles/            Sector profile YAML schema (C6 configuration)
```

---

## Data models (`schemas/models/`)

Auto-generated from the Pydantic v2 models in `vigilance/models/`. These define
the canonical data structures that flow between T5.3 components.

| File | Pydantic model | Produced by | Consumed by |
|---|---|---|---|
| `canonical_event.schema.json` | `CanonicalEvent` | C1 Ingestion | broker, C5 Safety |
| `action_request.schema.json` | `ActionRequest` | T5.4 (via broker) | C5 Safety, C3 Execution |
| `execution_result.schema.json` | `ExecutionResult` | T53Pipeline | C5 Audit, broker `t53.results` |
| `action_result.schema.json` | `ActionResult` | C4 Adapters | ExecutionResult (aggregated) |
| `guardrail_check.schema.json` | `GuardrailCheck` | C5 Safety Gate | T53Pipeline, C5 Audit |
| `audit_record.schema.json` | `AuditRecord` | C5 Audit Log | EC D5.1/D5.2 reporting |

### Pipeline data flow

```
raw event (pilot.events.raw)
  → [C1]      → CanonicalEvent → t53.canonical_events → T5.4
  → [T5.4]    → ActionRequest  → t53.action_requests  → T5.3
  → [C5]      → GuardrailCheck (APPROVED / REJECTED / ESCALATE)
  → [C3]      → Rego policy    → t53.policy_updates   → T5.5
  → [C4]      → dispatch       → t53.actions.dispatch → pilot tools
  → [C5]      → AuditRecord  + ExecutionResult → t53.results → T5.4
```

### Regenerating model schemas

If data models change, regenerate the JSON Schema files:

```bash
python - <<'EOF'
import json, pathlib
from vigilance.models.canonical_event import CanonicalEvent
from vigilance.models.action_request import ActionRequest
from vigilance.models.execution_result import ExecutionResult, ActionResult
from vigilance.models.guardrail_check import GuardrailCheck
from vigilance.models.audit_record import AuditRecord

base = pathlib.Path("schemas/models")
models = {
    "canonical_event":  CanonicalEvent,
    "action_request":   ActionRequest,
    "execution_result": ExecutionResult,
    "action_result":    ActionResult,
    "guardrail_check":  GuardrailCheck,
    "audit_record":     AuditRecord,
}
for name, model in models.items():
    schema = model.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"https://vigilance-gate/schemas/models/{name}.schema.json"
    (base / f"{name}.schema.json").write_text(json.dumps(schema, indent=2))
    print(f"updated {name}.schema.json")
EOF
```

---

## Broker integration interface (`schemas/broker/topics.yaml`)

Describes all RabbitMQ topics, their direction, producers, consumers, and payload
formats. Written in YAML to support inline comments explaining async behaviour and
WP5 task boundaries.

| Topic | Direction | Description |
|---|---|---|
| `pilot.events.raw` | inbound | Raw events from pilot SIEM/IDS → C1 normalization |
| `t53.canonical_events` | outbound | C1 output → T5.4 (RAG enrichment + agent selection) |
| `t53.action_requests` | inbound | T5.4 ActionRequest → C5+C3+C4 execution |
| `t53.policy_updates` | outbound | C3 NL→Rego rules → T5.5 ZTA blueprint refinement (async) |
| `t53.actions.dispatch` | outbound | C4 fire-and-forget → pilot tools |
| `t53.results` | outbound | ExecutionResult → T5.4 incident closure |
| `dt.events.synthetic` | inbound | WP3 D-VISOR synthetic events (reserved, post-M18) |

---

## Sector profile schema (`schemas/profiles/sector_profile.schema.yaml`)

YAML Schema for the four sector profile files in `profiles/`. Defines all valid
fields, types, constraints, and inline documentation for profiles loaded by C6.

All four pilots are covered by a single schema:

| Profile file | Sector | Pilot |
|---|---|---|
| `profiles/telecom.yaml` | TELECOM | OTE_GR |
| `profiles/maritime.yaml` | MARITIME | Rotterdam_NL |
| `profiles/finance.yaml` | FINANCE | CaixaBank_ES |
| `profiles/industry4.yaml` | INDUSTRY_4 | Siemens_RO |
