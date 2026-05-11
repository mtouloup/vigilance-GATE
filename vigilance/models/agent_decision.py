from __future__ import annotations
from pydantic import BaseModel


class AgentDecision(BaseModel):
    decision_id: str
    event_id: str
    threat_type: str
    recommended_actions: list[str]
    confidence: float  # 0.0–1.0
    reasoning_turns: int
    pilot: str
