"""Integration endpoint registry — T5.3 partner connection declarations.

Loads from integrations.yaml at repo root. Runtime URL overrides are
persisted to data/integrations_overrides.yaml so they survive restarts.
Env var pattern: INTEGRATION_<ID_UPPER>_URL overrides any entry at startup.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import requests
import yaml

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG = Path(__file__).parent.parent / "integrations.yaml"
_DEFAULT_OVERRIDES = Path(os.getenv("INTEGRATIONS_OVERRIDES_PATH", "data/integrations_overrides.yaml"))


class IntegrationsRegistry:
    """Loads and manages integration endpoint declarations for all T5.3 partners."""

    def __init__(
        self,
        config_path: Path = _DEFAULT_CONFIG,
        overrides_path: Path = _DEFAULT_OVERRIDES,
    ) -> None:
        self._config_path = config_path
        self._overrides_path = overrides_path
        self._entries: dict[str, dict] = {}
        self._load()

    # ------------------------------------------------------------------
    # Internal loading
    # ------------------------------------------------------------------

    def _load(self) -> None:
        with open(self._config_path) as f:
            raw = yaml.safe_load(f)

        # Self entry — resolve base_url from env vars
        s = dict(raw["self"])
        host = os.getenv("API_HOST", "localhost")
        if host == "0.0.0.0":
            host = "localhost"
        port = os.getenv("API_PORT", "8000")
        s["base_url"] = s.get("base_url") or f"http://{host}:{port}"
        self._entries[s["id"]] = s

        for entry in raw.get("wp5_tasks", []):
            self._entries[entry["id"]] = dict(entry)

        for entry in raw.get("pilot_tools", []):
            self._entries[entry["id"]] = dict(entry)

        # Apply persisted overrides (survive restarts)
        overrides: dict[str, str] = {}
        if self._overrides_path.exists():
            with open(self._overrides_path) as f:
                overrides = yaml.safe_load(f) or {}
        for id_, url in overrides.items():
            if id_ in self._entries:
                self._entries[id_]["base_url"] = url

        # Apply env var overrides last (highest precedence)
        # Pattern: INTEGRATION_<ID_UPPER>_URL   e.g. INTEGRATION_T54_ORCHESTRATOR_URL
        for id_ in list(self._entries.keys()):
            env_key = f"INTEGRATION_{id_.upper().replace('-', '_')}_URL"
            env_val = os.getenv(env_key)
            if env_val:
                self._entries[id_]["base_url"] = env_val

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def list_all(self) -> list[dict]:
        return list(self._entries.values())

    def get(self, partner_id: str) -> dict | None:
        return self._entries.get(partner_id)

    def update_url(self, partner_id: str, base_url: str) -> dict:
        """Persist a new base_url for partner_id. Survives process restart."""
        if partner_id not in self._entries:
            raise KeyError(f"Unknown partner '{partner_id}'")
        self._entries[partner_id]["base_url"] = base_url

        self._overrides_path.parent.mkdir(parents=True, exist_ok=True)
        overrides: dict[str, str] = {}
        if self._overrides_path.exists():
            with open(self._overrides_path) as f:
                overrides = yaml.safe_load(f) or {}
        overrides[partner_id] = base_url
        with open(self._overrides_path, "w") as f:
            yaml.safe_dump(overrides, f)

        logger.info("Integration URL updated: %s → %s", partner_id, base_url)
        return self._entries[partner_id]

    def check_reachability(self, partner_id: str) -> dict:
        """Probe the partner's base URL. Returns reachability dict."""
        entry = self._entries.get(partner_id)
        if not entry:
            raise KeyError(f"Unknown partner '{partner_id}'")

        base_url = entry.get("base_url", "")
        if not base_url:
            return {
                "partner_id": partner_id,
                "reachable": False,
                "status": "not_configured",
            }

        health_path = entry.get("health_path", "")
        probe_url = f"{base_url.rstrip('/')}{health_path}"
        try:
            resp = requests.get(probe_url, timeout=3.0, allow_redirects=True)
            return {
                "partner_id": partner_id,
                "reachable": resp.status_code < 500,
                "http_status": resp.status_code,
                "status": "ok",
            }
        except requests.ConnectionError:
            return {"partner_id": partner_id, "reachable": False, "status": "connection_refused"}
        except requests.Timeout:
            return {"partner_id": partner_id, "reachable": False, "status": "timeout"}
        except Exception as exc:
            return {"partner_id": partner_id, "reachable": False, "status": "error", "error": str(exc)}

    def get_url(self, partner_id: str) -> str | None:
        """Convenience accessor for C4 adapters — returns base_url or None."""
        entry = self._entries.get(partner_id)
        if not entry:
            return None
        url = entry.get("base_url", "")
        return url if url else None


# Module-level singleton
_registry: IntegrationsRegistry | None = None


def get_registry() -> IntegrationsRegistry:
    global _registry
    if _registry is None:
        _registry = IntegrationsRegistry()
    return _registry
