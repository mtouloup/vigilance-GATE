"""Tests for C3 — Action & Policy Execution."""
from __future__ import annotations
import pytest

from vigilance.components.c3_execution.executor import ActionExecutor
from vigilance.components.c3_execution.policy_translator import PolicyTranslator
from vigilance.components.c4_adapters.telecom.siem_plugin import SIEMPlugin
from vigilance.components.c4_adapters.telecom.iam_plugin import IAMPlugin
from vigilance.components.c4_adapters.telecom.ids_plugin import IDSPlugin
from vigilance.components.c6_profiles.profile_manager import ProfileManager
from vigilance.llm.base import StubLLMProvider
from vigilance.models.action_request import ActionRequest
from vigilance.models.execution_result import ExecutionResult


def make_telecom_request(actions=None):
    return ActionRequest(
        request_id="req-test-0001",
        event_id="evt-test-0001",
        pilot="OTE_GR",
        actions=actions or ["block_ip", "revoke_session", "notify_soc"],
        agent_confidence=0.96,
    )


def telecom_adapters():
    plugins = [SIEMPlugin(), IAMPlugin(), IDSPlugin()]
    return {p.plugin_name: p for p in plugins}


class TestPolicyTranslator:
    def test_translate_nl_policy(self):
        translator = PolicyTranslator(StubLLMProvider())
        rego = translator.translate("Block external IPs attempting brute force")
        assert isinstance(rego, str)
        assert len(rego) > 0

    def test_fallback_rego_generated(self):
        translator = PolicyTranslator(StubLLMProvider())
        # The stub LLM returns JSON, so fallback Rego should be generated
        result = translator.translate("block credential stuffing attacks")
        assert "package vigilance.policy" in result or len(result) > 10


class TestActionExecutor:
    def test_execute_telecom_actions(self):
        profile = ProfileManager(sector="TELECOM").load()
        adapters = telecom_adapters()
        executor = ActionExecutor()
        request = make_telecom_request()

        result = executor.execute(request, profile, adapters)

        assert isinstance(result, ExecutionResult)
        assert result.overall_success
        assert len(result.action_results) == 3
        assert result.event_id == "evt-test-0001"

    def test_block_ip_action(self):
        profile = ProfileManager(sector="TELECOM").load()
        adapters = telecom_adapters()
        executor = ActionExecutor()
        request = make_telecom_request(actions=["block_ip"])

        result = executor.execute(request, profile, adapters)
        assert result.overall_success
        block_result = result.action_results[0]
        assert block_result.action == "block_ip"
        assert block_result.plugin == "ote_siem"
        assert block_result.response_code == 200

    def test_unknown_action_fails(self):
        profile = ProfileManager(sector="TELECOM").load()
        adapters = telecom_adapters()
        executor = ActionExecutor()
        request = make_telecom_request(actions=["nonexistent_action"])

        result = executor.execute(request, profile, adapters)
        assert not result.overall_success
        assert result.action_results[0].response_code == 404

    def test_action_latencies_recorded(self):
        profile = ProfileManager(sector="TELECOM").load()
        adapters = telecom_adapters()
        executor = ActionExecutor()
        request = make_telecom_request()

        result = executor.execute(request, profile, adapters)
        for ar in result.action_results:
            assert ar.latency_ms >= 0

    def test_execute_with_policy_update(self):
        profile = ProfileManager(sector="TELECOM").load()
        adapters = telecom_adapters()
        translator = PolicyTranslator(StubLLMProvider())
        executor = ActionExecutor(translator)
        request = ActionRequest(
            request_id="req-test-0002",
            event_id="evt-test-0002",
            pilot="OTE_GR",
            actions=["block_ip"],
            policy_update="Block all traffic from credential stuffing IPs",
            agent_confidence=0.96,
        )

        result = executor.execute(request, profile, adapters)
        assert result.overall_success
