"""Tests for C6 — Sector Profile Manager."""
from __future__ import annotations
import os
import pytest

from vigilance.components.c6_profiles.profile_manager import ProfileManager, SectorProfile


class TestProfileManager:
    def test_load_telecom_profile(self):
        manager = ProfileManager(sector="TELECOM")
        profile = manager.load()
        assert isinstance(profile, SectorProfile)
        assert profile.sector == "TELECOM"
        assert profile.pilot == "OTE_GR"
        assert profile.ot_safety_flag is False
        assert profile.confidence_threshold == 0.80
        assert "ote_siem" in profile.tool_plugins

    def test_load_industry4_profile(self):
        manager = ProfileManager(sector="INDUSTRY_4")
        profile = manager.load()
        assert isinstance(profile, SectorProfile)
        assert profile.sector == "INDUSTRY_4"
        assert profile.pilot == "Siemens_RO"
        assert profile.ot_safety_flag is True
        assert "scada_opcua" in profile.tool_plugins

    def test_telecom_llm_prompt(self):
        profile = ProfileManager(sector="TELECOM").load()
        assert "telecom" in profile.llm_system_prompt.lower()

    def test_industry4_llm_prompt(self):
        profile = ProfileManager(sector="INDUSTRY_4").load()
        # Should contain RAME or industrial/OT context
        prompt_lower = profile.llm_system_prompt.lower()
        assert "industrial" in prompt_lower or "ot" in prompt_lower or "rame" in prompt_lower

    def test_telecom_protected_ranges(self):
        profile = ProfileManager(sector="TELECOM").load()
        assert "10.0.0.0/8" in profile.protected_ranges
        assert "192.168.0.0/16" in profile.protected_ranges

    def test_industry4_protected_ranges(self):
        profile = ProfileManager(sector="INDUSTRY_4").load()
        assert "10.0.0.0/8" in profile.protected_ranges

    def test_profile_cached(self):
        manager = ProfileManager(sector="TELECOM")
        profile1 = manager.load()
        profile2 = manager.load()
        assert profile1 is profile2

    def test_unknown_sector_raises(self):
        manager = ProfileManager(sector="UNKNOWN_SECTOR")
        with pytest.raises(ValueError, match="Unknown sector"):
            manager.load()

    def test_env_var_default(self, monkeypatch):
        monkeypatch.delenv("VIGILANCE_SECTOR", raising=False)
        manager = ProfileManager()
        assert manager.sector == "TELECOM"
