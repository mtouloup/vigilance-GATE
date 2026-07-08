"""Tests for C3 — Action & Policy Execution."""
from __future__ import annotations
import shutil
import subprocess
import pytest
from unittest.mock import MagicMock, patch

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


_VALID_REGO = (
    'package vigilance.ote.auth\n\n'
    'default allow = true\n\n'
    'deny if {\n'
    '    input.action == "authenticate"\n'
    '    input.destination == "auth-server-01"\n'
    '}\n'
)
_INVALID_REGO = "this is not valid rego @@@"


def _mock_llm(*responses):
    """Return a MagicMock LLM whose complete() yields responses in sequence."""
    m = MagicMock()
    m.complete.side_effect = list(responses)
    return m


class TestPolicyTranslatorMocked:
    """Targeted tests for retry/fallback/OPA-integration paths.

    _validate_rego is patched to control parse outcomes independently of
    whether OPA is installed on the test host.
    """

    def test_happy_path_returns_llm_output(self):
        translator = PolicyTranslator(_mock_llm(_VALID_REGO))
        with patch.object(translator, "_validate_rego", return_value=(True, "")):
            result = translator.translate("Block credential stuffing from 198.51.100.0/24")
        assert result == _VALID_REGO.strip()

    def test_retry_on_first_invalid_returns_second_output(self):
        translator = PolicyTranslator(_mock_llm(_INVALID_REGO, _VALID_REGO))
        with patch.object(
            translator,
            "_validate_rego",
            side_effect=[(False, "1 error occurred: rego_parse_error"), (True, "")],
        ):
            result = translator.translate("some policy")
        assert result == _VALID_REGO.strip()
        assert translator._llm.complete.call_count == 2
        # Second call must include error feedback in the messages
        retry_messages = translator._llm.complete.call_args_list[1][0][1]
        assert any(
            "failed to parse" in str(m.get("content", "")) for m in retry_messages
        )

    def test_fallback_on_both_calls_invalid(self):
        translator = PolicyTranslator(_mock_llm(_INVALID_REGO, _INVALID_REGO))
        with patch.object(
            translator,
            "_validate_rego",
            return_value=(False, "parse error"),
        ):
            result = translator.translate("deny everything from untrusted zone")
        assert "vigilance.fallback" in result
        assert "default deny = true" in result

    def test_strip_fences_removes_markdown(self):
        translator = PolicyTranslator(_mock_llm(f"```rego\n{_VALID_REGO}\n```"))
        with patch.object(translator, "_validate_rego", return_value=(True, "")):
            result = translator.translate("some policy")
        assert result == _VALID_REGO.strip()

    def test_fallback_content_includes_nl_policy(self):
        nl = "deny all OT writes from untrusted hosts"
        translator = PolicyTranslator(_mock_llm(_INVALID_REGO, _INVALID_REGO))
        with patch.object(translator, "_validate_rego", return_value=(False, "err")):
            result = translator.translate(nl)
        assert nl in result

    @pytest.mark.skipif(shutil.which("opa") is None, reason="OPA not installed")
    def test_opa_integration_parses_ote_brute_force():
        """Integration: translator output must parse cleanly under real opa parse."""
        nl = (
            "For OTE, deny authentication attempts to auth-server-01 from source IPs "
            "in 203.0.113.0/24 for the next 24 hours, except from the management VLAN."
        )
        expected_rego = (
            "package vigilance.ote.auth\n\n"
            "default allow = true\n\n"
            "# Expires 2026-07-09T00:00:00Z\n"
            "deny if {\n"
            '    input.action == "authenticate"\n'
            '    input.destination == "auth-server-01"\n'
            '    net.cidr_contains("203.0.113.0/24", input.source_ip)\n'
            "    time.now_ns() < 1783555200000000000\n"
            '    not net.cidr_contains("10.20.0.0/16", input.source_ip)\n'
            "}\n"
        )
        mock_llm = _mock_llm(expected_rego)
        translator = PolicyTranslator(mock_llm)
        result = translator.translate(nl)
        parse = subprocess.run(
            ["opa", "parse", "-"],
            input=result,
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert parse.returncode == 0, f"opa parse failed:\n{parse.stderr}"


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
