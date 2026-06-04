from __future__ import annotations
from enum import Enum
from pydantic import BaseModel


class GuardrailVerdict(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ESCALATE = "ESCALATE"


class GuardrailCheck(BaseModel):
    check_id: str
    request_id: str
    verdict: GuardrailVerdict
    reasons: list[str]
    ot_safety_checked: bool = False
    # Set when mistral:7b semantic review was invoked (ESCALATE path)
    llm_invoked: bool = False
    llm_response: str | None = None
