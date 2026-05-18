from __future__ import annotations
import os
from pathlib import Path
from dataclasses import dataclass, field

import yaml


@dataclass
class SectorProfile:
    """Loaded sector profile with all configuration."""
    sector: str
    pilot: str
    schema_extensions: list[dict] = field(default_factory=list)
    tool_plugins: list[str] = field(default_factory=list)
    policy_templates: list[str] = field(default_factory=list)
    llm_system_prompt: str = ""
    ot_safety_flag: bool = False
    confidence_threshold: float = 0.80
    protected_ranges: list[str] = field(default_factory=list)


class ProfileManager:
    """Loads and manages sector profiles from YAML files.

    Reads VIGILANCE_SECTOR env var (default: TELECOM) to determine
    which profile to load from the profiles/ directory.
    """

    # Locate profiles relative to this package
    _PROFILES_DIR = Path(__file__).parent.parent.parent.parent / "profiles"

    _SECTOR_MAP = {
        "TELECOM": "telecom.yaml",
        "INDUSTRY_4": "industry4.yaml",
        "MARITIME": "maritime.yaml",
        "FINANCE": "finance.yaml",
    }

    def __init__(self, sector: str | None = None) -> None:
        self._sector = (sector or os.getenv("VIGILANCE_SECTOR", "TELECOM")).upper()
        self._profile: SectorProfile | None = None

    @classmethod
    def load_all_profiles(cls) -> dict[str, "SectorProfile"]:
        """Load and return all four sector profiles keyed by sector name."""
        return {sector: cls(sector=sector).load() for sector in cls._SECTOR_MAP}

    def load(self) -> SectorProfile:
        """Load and return the sector profile."""
        if self._profile is not None:
            return self._profile

        filename = self._SECTOR_MAP.get(self._sector)
        if filename is None:
            raise ValueError(
                f"Unknown sector '{self._sector}'. "
                f"Valid options: {list(self._SECTOR_MAP.keys())}"
            )

        yaml_path = self._PROFILES_DIR / filename
        if not yaml_path.exists():
            raise FileNotFoundError(f"Profile file not found: {yaml_path}")

        with yaml_path.open() as f:
            data = yaml.safe_load(f)

        self._profile = SectorProfile(
            sector=data["sector"],
            pilot=data["pilot"],
            schema_extensions=data.get("schema_extensions", []),
            tool_plugins=data.get("tool_plugins", []),
            policy_templates=data.get("policy_templates", []),
            llm_system_prompt=data.get("llm_system_prompt", ""),
            ot_safety_flag=data.get("ot_safety_flag", False),
            confidence_threshold=data.get("confidence_threshold", 0.80),
            protected_ranges=data.get("protected_ranges", []),
        )
        return self._profile

    @property
    def sector(self) -> str:
        return self._sector
