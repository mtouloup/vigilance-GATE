from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel


class CanonicalEvent(BaseModel):
    event_id: str
    type: str          # e.g. AUTH_BRUTE_FORCE, OT_ANOMALY
    pilot: str         # TELECOM | INDUSTRY_4
    severity: str      # LOW | MEDIUM | HIGH | CRITICAL
    src_ip: str | None = None
    target: str | None = None
    count: int | None = None
    nodes_affected: int | None = None
    raw_payload: dict = {}
    # TELECOM extensions
    subscriber_id: str | None = None
    cell_id: str | None = None
    imsi: str | None = None
    # INDUSTRY_4 extensions
    plc_id: str | None = None
    line_id: str | None = None
    scada_zone: str | None = None
    ot_protocol: str | None = None  # OPC-UA | Modbus
    ot_safety_flag: bool = False
    timestamp: datetime
