"""T5.3 REST API — standardized HTTP interface for T5.6 Agentic ZTA Platform Integration.

Provides endpoints for external system access to T5.3 capabilities:
  POST /api/v1/events          Submit a raw event for processing (STANDALONE pipeline)
  POST /api/v1/action-requests Submit an ActionRequest for C5+C3+C4 execution (INTEGRATED)
  GET  /api/v1/profiles        List all loaded sector profiles
  GET  /api/v1/health          Liveness / readiness check

The pipeline instance is shared across requests and initialised once at startup.
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

# ── FastAPI app ────────────────────────────────────────────────────────────────

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
        mode       = os.getenv("VIGILANCE_MODE", "STANDALONE").upper()
        simulation = os.getenv("VIGILANCE_SIMULATION", "").lower()
        _pipeline = T53Pipeline(
            mode="STANDALONE" if mode == "DIGITAL_TWIN" else mode,
            simulation_mode=(mode == "DIGITAL_TWIN" or simulation == "digital_twin"),
            dry_run=(simulation == "dry_run"),
        )
    return _pipeline


# ── Request / response models ──────────────────────────────────────────────────

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


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/api/v1/health", tags=["System"])
def health() -> dict:
    """Liveness and readiness check."""
    pipeline = get_pipeline()
    return {
        "status": "ok",
        "pilots": list(pipeline.profiles.keys()),
        "mode": pipeline._mode,
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
    """Submit a raw security event for full pipeline processing (STANDALONE mode).

    Returns the ExecutionResult including per-action outcomes and guardrail verdict.
    In INTEGRATED mode this endpoint performs C1 normalization only and returns
    the CanonicalEvent; the full execution path runs asynchronously via the broker.
    """
    pipeline = get_pipeline()
    try:
        result = pipeline.process_event(body.raw)
    except Exception as exc:
        logger.error(f"Event processing error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))

    if result is None:
        # INTEGRATED mode — C1 only; async execution via broker
        return JSONResponse(
            status_code=202,
            content={"message": "Event accepted; C1 normalization complete. Execution dispatched via broker."},
        )

    return JSONResponse(
        status_code=200 if result.overall_success else 207,
        content=result.model_dump(mode="json"),
    )


@app.post("/api/v1/action-requests", tags=["Execution"])
def submit_action_request(body: ActionRequestPayload) -> JSONResponse:
    """Submit an ActionRequest for C5 guardrail + C3+C4 execution (INTEGRATED mode).

    Intended for T5.4 or external orchestrators that have already performed
    agent selection and threat analysis. T5.3 will run the safety guardrail,
    translate any NL policy to Rego (→ T5.5), and dispatch actions to pilot tools.
    """
    pipeline = get_pipeline()
    try:
        result = pipeline.execute_action_request(body.model_dump())
    except Exception as exc:
        logger.error(f"ActionRequest execution error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))

    return JSONResponse(
        status_code=200 if result.overall_success else 207,
        content=result.model_dump(mode="json"),
    )
