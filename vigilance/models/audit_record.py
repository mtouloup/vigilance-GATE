from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel


class AuditRecord(BaseModel):
    audit_id: str       # e.g. aud-OTE-0031
    pilot_id: str
    event_id: str
    request_id: str
    timestamp_opened: datetime
    timestamp_closed: datetime | None = None
    verdict: str
    action_results: list[dict] = []
    latencies_ms: list[int] = []
    closed: bool = False
