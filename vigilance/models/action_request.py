from __future__ import annotations
from pydantic import BaseModel


class ActionRequest(BaseModel):
    request_id: str
    event_id: str
    pilot: str
    actions: list[str]
    policy_update: str | None = None  # NL description for OPA/Rego translation
    agent_confidence: float
