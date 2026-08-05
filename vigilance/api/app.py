"""T5.3 REST API — T5.6 Agentic ZTA Platform Integration point.

Endpoints:
  POST /api/v1/events          Submit raw event → C1 normalize → publish to broker (202)
  POST /api/v1/action-requests Submit ActionRequest → C5+C3+C4 execute → result (200/207)
  GET  /api/v1/profiles        All four sector profiles
  GET  /api/v1/health          Liveness check
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from vigilance.pipeline import T53Pipeline

logger = logging.getLogger(__name__)

app = FastAPI(
    title="T5.3 Agentic Wrapper Framework",
    description=(
        "REST API for the VIGILANCE T5.3 Agentic Wrapper Framework. "
        "Supports all four GA pilots (TELECOM, MARITIME, FINANCE, INDUSTRY_4)."
    ),
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

_pipeline: T53Pipeline | None = None


def get_pipeline() -> T53Pipeline:
    global _pipeline
    if _pipeline is None:
        dry_run = os.getenv("VIGILANCE_DRY_RUN", "").lower() in ("1", "true", "yes")
        _pipeline = T53Pipeline(dry_run=dry_run)
    return _pipeline


class RawEventRequest(BaseModel):
    raw: Any
    description: str = ""


class ActionRequestPayload(BaseModel):
    request_id: str
    event_id: str
    pilot: str
    actions: list[str]
    policy_update: str | None = None
    agent_confidence: float = 0.9


@app.get("/api/v1/health", tags=["System"])
def health() -> dict:
    """Liveness and readiness check."""
    pipeline = get_pipeline()
    return {
        "status": "ok",
        "pilots": list(pipeline.profiles.keys()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/v1/profiles", tags=["Configuration"])
def list_profiles() -> dict:
    """Return all loaded sector profiles."""
    pipeline = get_pipeline()
    return {
        sector: {
            "pilot": p.pilot,
            "sector": p.sector,
            "tool_plugins": p.tool_plugins,
            "confidence_threshold": p.confidence_threshold,
            "ot_safety_flag": p.ot_safety_flag,
        }
        for sector, p in pipeline.profiles.items()
    }


@app.get("/api/v1/formats", tags=["Events"])
def list_formats() -> dict:
    """Return the log formats C1 can parse and which pilots each format applies to.

    Formats are tried in priority order. The LLM fallback is always last and
    accepts any input type, but requires Ollama to be reachable.
    """
    return {
        "parser_priority": ["CEF", "ECS", "OT_JSON", "Syslog", "LLM"],
        "formats": [
            {
                "name": "CEF",
                "full_name": "Common Event Format",
                "priority": 1,
                "input_type": "string",
                "detection": "String starting with 'CEF:'",
                "pilots": ["TELECOM", "INDUSTRY_4", "MARITIME", "FINANCE"],
                "pilot_detection": "Inferred from device_product field keywords",
                "example": (
                    "CEF:0|OTE-IDS|SOCv3|2.0|200|AUTH_BRUTE_FORCE|9|"
                    "src=91.108.4.12 dst=nms-01 cnt=230"
                ),
            },
            {
                "name": "ECS",
                "full_name": "Elastic Common Schema",
                "priority": 2,
                "input_type": "dict",
                "detection": "Dict containing key 'event.kind'",
                "pilots": ["TELECOM", "INDUSTRY_4", "MARITIME", "FINANCE"],
                "pilot_detection": "Inferred from agent.type or observer.type keywords",
                "example": {
                    "event.kind": "alert",
                    "event.category": "authentication",
                    "event.action": "brute_force",
                    "event.severity": "high",
                    "agent.type": "ote-soc",
                    "source.ip": "91.108.4.12",
                },
            },
            {
                "name": "OT_JSON",
                "full_name": "OT JSON (Siemens Industry 4.0)",
                "priority": 3,
                "input_type": "dict",
                "detection": "Dict containing key 'plc' or 'protocol'",
                "pilots": ["INDUSTRY_4"],
                "pilot_detection": "Always INDUSTRY_4 — format is OT-specific",
                "example": {
                    "plc": "PLC-42",
                    "line": "line-7",
                    "protocol": "OPC-UA",
                    "anomaly": "register_write_out_of_range",
                    "severity": "CRITICAL",
                },
            },
            {
                "name": "Syslog",
                "full_name": "Syslog (RFC 3164 / RFC 5424)",
                "priority": 4,
                "input_type": "string",
                "detection": "String matching RFC 3164 or RFC 5424 pattern (<priority>...)",
                "pilots": ["TELECOM", "INDUSTRY_4", "MARITIME", "FINANCE"],
                "pilot_detection": (
                    "Pilot is UNKNOWN from syslog alone — falls back to TELECOM profile. "
                    "Use CEF or ECS for explicit pilot identification."
                ),
                "example": (
                    "<34>Oct 11 22:14:15 firewall-01 sshd: "
                    "Failed password for root from 91.108.4.12 port 22"
                ),
            },
            {
                "name": "LLM",
                "full_name": "LLM Fallback (Mistral 7B)",
                "priority": 5,
                "input_type": "string or dict",
                "detection": "Any input that does not match CEF, ECS, OT_JSON, or Syslog",
                "pilots": ["TELECOM", "INDUSTRY_4", "MARITIME", "FINANCE"],
                "pilot_detection": "Extracted by LLM from free-text content",
                "requires_ollama": True,
                "note": (
                    "Used as a last resort for novel or proprietary formats. "
                    "Requires Ollama (mistral:7b) to be reachable. "
                    "When Ollama is unavailable, StubLLMProvider returns a minimal event."
                ),
                "example": (
                    "ALERT: Anomalous login detected for subscriber IMSI-204041234567890 "
                    "from cell tower CELL-Athens-NW-014 at 03:42 UTC"
                ),
            },
        ],
    }


@app.post("/api/v1/events", tags=["Events"])
def submit_event(body: RawEventRequest) -> JSONResponse:
    """Submit a raw security event for C1 normalization.

    T5.3 normalizes the event, caches it, and publishes it to
    t53.canonical_events for T5.4 to consume. Returns 202 Accepted —
    the full execution result arrives later via t53.results.
    """
    pipeline = get_pipeline()
    try:
        event = pipeline.ingest_event(body.raw)
    except Exception as exc:
        logger.error(f"Ingest error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))

    return JSONResponse(
        status_code=202,
        content={
            "message": "Event accepted — CanonicalEvent published to t53.canonical_events.",
            "event_id": event.event_id,
            "pilot": event.pilot,
            "type": event.type,
            "severity": event.severity,
            "canonical_event": event.model_dump(mode="json"),
        },
    )


@app.get("/api/v1/results/{request_id}", tags=["Results"])
def get_result(request_id: str) -> JSONResponse:
    """Retrieve the ExecutionResult for a completed ActionRequest.

    Returns the full result including action outcomes, overall success,
    and the generated Rego rule if a policy_update was present.
    """
    pipeline = get_pipeline()
    result = pipeline.get_result(request_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No result found for request_id '{request_id}'. "
                   "The request may not have been executed yet.",
        )
    content = dict(result)
    rego = content.pop("rego_rule", None)
    if rego:
        content["policy_translation"] = {"rego_output": rego}
    return JSONResponse(status_code=200, content=content)


@app.get("/api/v1/audit", tags=["Audit"])
def list_audit_records(pilot: str | None = None) -> JSONResponse:
    """List all audit records, optionally filtered by pilot.

    Query param: ?pilot=INDUSTRY_4
    Each record covers one ActionRequest lifecycle from C5 gate entry
    to dispatch closure, including verdict, action results, and latencies.
    """
    pipeline = get_pipeline()
    records = pipeline.get_audit_records(pilot=pilot)
    return JSONResponse(
        status_code=200,
        content={"total": len(records), "records": records},
    )


@app.get("/api/v1/audit/{audit_id}", tags=["Audit"])
def get_audit_record(audit_id: str) -> JSONResponse:
    """Retrieve a single audit record by its audit_id (e.g. aud-SIE-0074)."""
    pipeline = get_pipeline()
    record = pipeline.get_audit_record(audit_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"Audit record '{audit_id}' not found.",
        )
    return JSONResponse(status_code=200, content=record)


@app.post("/api/v1/action-requests/submit", tags=["Execution"])
def store_action_request(body: ActionRequestPayload) -> JSONResponse:
    """Receive and store an ActionRequest without running the pipeline.

    Use this when you want to control execution timing manually.
    After storing, call POST /api/v1/action-requests/{request_id}/guardrail
    to run the C5 safety check, then POST /api/v1/action-requests to execute
    the full pipeline when ready.
    """
    pipeline = get_pipeline()
    try:
        request_id = pipeline.store_action_request(body.model_dump())
    except Exception as exc:
        logger.error(f"Store error: {exc}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse(
        status_code=202,
        content={
            "message": "ActionRequest stored — call /guardrail to run the C5 safety check.",
            "request_id": request_id,
            "status": "pending",
        },
    )


@app.post("/api/v1/action-requests/{request_id}/guardrail", tags=["Execution"])
def check_guardrail(request_id: str) -> JSONResponse:
    """Run the C5 guardrail check on a stored ActionRequest.

    Returns the GuardrailCheck verdict (APPROVED / REJECTED / ESCALATE)
    and the reasons for each outcome. Does not dispatch to C3 or C4 —
    use POST /api/v1/action-requests for the full execution pipeline.
    """
    pipeline = get_pipeline()
    try:
        guardrail = pipeline.run_guardrail(request_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error(f"Guardrail error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
    return JSONResponse(status_code=200, content=guardrail.model_dump(mode="json"))


@app.post("/api/v1/action-requests", tags=["Execution"])
def submit_action_request(body: ActionRequestPayload) -> JSONResponse:
    """Submit an ActionRequest for C5 guardrail + C3+C4 dispatch.

    Intended for T5.4 or testing tools. T5.3 runs the safety guardrail,
    translates any NL policy to Rego (→ T5.5), and dispatches actions to
    pilot tools (→ t53.actions.dispatch). Returns the ExecutionResult.
    """
    pipeline = get_pipeline()
    try:
        result, rego = pipeline.execute_action_request(body.model_dump())
    except Exception as exc:
        logger.error(f"Execution error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))

    response_content = result.model_dump(mode="json")
    if rego and body.policy_update:
        response_content["policy_translation"] = {
            "nl_input": body.policy_update,
            "rego_output": rego,
        }

    return JSONResponse(
        status_code=200 if result.overall_success else 207,
        content=response_content,
    )
