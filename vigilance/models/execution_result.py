from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel


class ActionResult(BaseModel):
    action: str
    plugin: str
    success: bool
    latency_ms: int
    response_code: int | None = None
    message: str = ""


class ExecutionResult(BaseModel):
    request_id: str
    event_id: str
    pilot: str
    action_results: list[ActionResult]
    overall_success: bool
    timestamp: datetime
