"""SQLite persistence layer for T5.3 pipeline artefacts.

All four stores (events, action_requests, results, audit_records) are backed
by a single SQLite file at DB_PATH (default: data/vigilance.db).

Thread safety: a single threading.Lock serialises all writes. Reads use
separate short-lived connections so they never block each other.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_PATH = os.getenv("DB_PATH", "data/vigilance.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id        TEXT PRIMARY KEY,
    pilot           TEXT NOT NULL,
    type            TEXT NOT NULL,
    severity        TEXT NOT NULL,
    timestamp       TEXT NOT NULL,
    parser_used     TEXT,
    c1_llm_invoked  INTEGER DEFAULT 0,
    c1_llm_fields   TEXT,
    canonical_event TEXT NOT NULL,
    raw_event       TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS action_requests (
    request_id       TEXT PRIMARY KEY,
    event_id         TEXT NOT NULL,
    pilot            TEXT NOT NULL,
    actions          TEXT NOT NULL,
    policy_update    TEXT,
    agent_confidence REAL NOT NULL,
    received_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS results (
    request_id      TEXT PRIMARY KEY,
    event_id        TEXT NOT NULL,
    pilot           TEXT NOT NULL,
    overall_success INTEGER NOT NULL,
    action_results  TEXT NOT NULL,
    rego_rule       TEXT,
    timestamp       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_records (
    audit_id          TEXT PRIMARY KEY,
    pilot_id          TEXT NOT NULL,
    event_id          TEXT NOT NULL,
    request_id        TEXT NOT NULL,
    timestamp_opened  TEXT NOT NULL,
    timestamp_closed  TEXT,
    verdict           TEXT NOT NULL,
    action_results    TEXT NOT NULL DEFAULT '[]',
    latencies_ms      TEXT NOT NULL DEFAULT '[]',
    closed            INTEGER NOT NULL DEFAULT 0
);
"""


class Database:
    """SQLite-backed persistence for pipeline artefacts."""

    def __init__(self, path: str = _DEFAULT_PATH) -> None:
        self._path = path
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        self._lock = threading.Lock()
        self._init_schema()
        logger.info(f"[DB] SQLite store initialised at {path}")

    # ── Schema ────────────────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(_SCHEMA)

    # ── Events ────────────────────────────────────────────────────────────────

    def upsert_event(
        self,
        canonical_event: dict,
        raw_event: Any,
        parser_used: str,
        c1_llm_invoked: bool,
        c1_llm_fields: dict | None,
    ) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO events
                  (event_id, pilot, type, severity, timestamp,
                   parser_used, c1_llm_invoked, c1_llm_fields,
                   canonical_event, raw_event, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    canonical_event["event_id"],
                    canonical_event["pilot"],
                    canonical_event["type"],
                    canonical_event["severity"],
                    canonical_event["timestamp"],
                    parser_used,
                    int(c1_llm_invoked),
                    json.dumps(c1_llm_fields) if c1_llm_fields else None,
                    json.dumps(canonical_event),
                    json.dumps(raw_event) if not isinstance(raw_event, str) else raw_event,
                    _now(),
                ),
            )

    def get_event(self, event_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT canonical_event FROM events WHERE event_id = ?", (event_id,)
            ).fetchone()
        return json.loads(row["canonical_event"]) if row else None

    def list_events(self, pilot: str | None = None, limit: int = 100) -> list[dict]:
        with self._connect() as conn:
            if pilot:
                rows = conn.execute(
                    "SELECT canonical_event FROM events WHERE pilot = ? ORDER BY created_at DESC LIMIT ?",
                    (pilot, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT canonical_event FROM events ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [json.loads(r["canonical_event"]) for r in rows]

    # ── Action requests ───────────────────────────────────────────────────────

    def upsert_action_request(self, d: dict) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO action_requests
                  (request_id, event_id, pilot, actions, policy_update,
                   agent_confidence, received_at)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    d["request_id"],
                    d["event_id"],
                    d["pilot"],
                    json.dumps(d.get("actions", [])),
                    d.get("policy_update"),
                    d.get("agent_confidence", 0.0),
                    _now(),
                ),
            )

    def list_action_requests(self, pilot: str | None = None, limit: int = 100) -> list[dict]:
        with self._connect() as conn:
            if pilot:
                rows = conn.execute(
                    "SELECT * FROM action_requests WHERE pilot = ? ORDER BY received_at DESC LIMIT ?",
                    (pilot, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM action_requests ORDER BY received_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [
            {
                "request_id": r["request_id"],
                "event_id": r["event_id"],
                "pilot": r["pilot"],
                "actions": json.loads(r["actions"]),
                "policy_update": r["policy_update"],
                "agent_confidence": r["agent_confidence"],
                "received_at": r["received_at"],
            }
            for r in rows
        ]

    def get_action_request(self, request_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM action_requests WHERE request_id = ?", (request_id,)
            ).fetchone()
        if row is None:
            return None
        return {
            "request_id": row["request_id"],
            "event_id": row["event_id"],
            "pilot": row["pilot"],
            "actions": json.loads(row["actions"]),
            "policy_update": row["policy_update"],
            "agent_confidence": row["agent_confidence"],
        }

    # ── Results ───────────────────────────────────────────────────────────────

    def upsert_result(self, result: dict, rego_rule: str | None) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO results
                  (request_id, event_id, pilot, overall_success,
                   action_results, rego_rule, timestamp)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    result["request_id"],
                    result["event_id"],
                    result["pilot"],
                    int(result["overall_success"]),
                    json.dumps(result.get("action_results", [])),
                    rego_rule,
                    result.get("timestamp", _now()),
                ),
            )

    def get_result(self, request_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM results WHERE request_id = ?", (request_id,)
            ).fetchone()
        if row is None:
            return None
        return {
            "request_id": row["request_id"],
            "event_id": row["event_id"],
            "pilot": row["pilot"],
            "overall_success": bool(row["overall_success"]),
            "action_results": json.loads(row["action_results"]),
            "rego_rule": row["rego_rule"],
            "timestamp": row["timestamp"],
        }

    def list_results(self, pilot: str | None = None, limit: int = 100) -> list[dict]:
        with self._connect() as conn:
            if pilot:
                rows = conn.execute(
                    "SELECT * FROM results WHERE pilot = ? ORDER BY timestamp DESC LIMIT ?",
                    (pilot, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM results ORDER BY timestamp DESC LIMIT ?", (limit,)
                ).fetchall()
        return [
            {
                "request_id": r["request_id"],
                "event_id": r["event_id"],
                "pilot": r["pilot"],
                "overall_success": bool(r["overall_success"]),
                "action_results": json.loads(r["action_results"]),
                "rego_rule": r["rego_rule"],
                "timestamp": r["timestamp"],
            }
            for r in rows
        ]

    # ── Audit records ─────────────────────────────────────────────────────────

    def upsert_audit_record(self, record: dict) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO audit_records
                  (audit_id, pilot_id, event_id, request_id,
                   timestamp_opened, timestamp_closed, verdict,
                   action_results, latencies_ms, closed)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    record["audit_id"],
                    record["pilot_id"],
                    record["event_id"],
                    record["request_id"],
                    record["timestamp_opened"],
                    record.get("timestamp_closed"),
                    record["verdict"],
                    json.dumps(record.get("action_results", [])),
                    json.dumps(record.get("latencies_ms", [])),
                    int(record.get("closed", False)),
                ),
            )

    def get_audit_record(self, audit_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM audit_records WHERE audit_id = ?", (audit_id,)
            ).fetchone()
        return _audit_row_to_dict(row) if row else None

    def list_audit_records(self, pilot: str | None = None, limit: int = 100) -> list[dict]:
        with self._connect() as conn:
            if pilot:
                rows = conn.execute(
                    "SELECT * FROM audit_records WHERE pilot_id = ? ORDER BY timestamp_opened DESC LIMIT ?",
                    (pilot, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM audit_records ORDER BY timestamp_opened DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [_audit_row_to_dict(r) for r in rows]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _audit_row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "audit_id": row["audit_id"],
        "pilot_id": row["pilot_id"],
        "event_id": row["event_id"],
        "request_id": row["request_id"],
        "timestamp_opened": row["timestamp_opened"],
        "timestamp_closed": row["timestamp_closed"],
        "verdict": row["verdict"],
        "action_results": json.loads(row["action_results"]),
        "latencies_ms": json.loads(row["latencies_ms"]),
        "closed": bool(row["closed"]),
    }
