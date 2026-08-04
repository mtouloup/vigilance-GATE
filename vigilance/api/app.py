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
