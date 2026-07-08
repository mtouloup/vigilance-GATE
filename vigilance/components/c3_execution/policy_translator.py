"""C3 Policy Translator — NL sentence → few-shot LLM prompt → OPA parse validation → Rego string.

Converts a natural language policy description into a valid OPA/Rego rule and
returns the Rego string for publication to ``t53.policy_updates``.

Pipeline:
    1. Build a few-shot prompt and call the LLM (Mistral Nemo 12B via ``complete()``).
    2. Strip any markdown code fences the model may have wrapped the output in.
    3. Validate with ``opa parse`` if the OPA binary is available.
    4. On validation failure, retry once with the parse error fed back to the LLM.
    5. If the retry also fails, log an error and return ``_fallback_rego`` (fail-closed).
    6. If OPA is not installed, skip steps 3–5 and return the LLM output directly.

Package naming convention
--------------------------
``vigilance.<pilot>.<domain>``

pilot  : ote | siemens | maritime | finance  (inferred from the NL context)
domain : auth | network | ot | iam | ...      (inferred from the policy intent)

Example: ``package vigilance.ote.auth``

Runtime input schema
---------------------
OPA evaluates rules against an ``input`` object supplied by the policy engine.
The fields this module's rules may reference are:

    input.action      — the action being attempted, e.g. "authenticate", "write_command"
    input.source_ip   — source IP address string, e.g. "203.0.113.5"
    input.destination — target host, resource, or zone, e.g. "auth-server-01", "PLC-07"
    input.subject     — authenticated identity, e.g. "noc-service-account"
    input.resource    — resource being accessed, e.g. "mfa_verified", "config_register"

Do not add fields beyond these five without updating this docstring and notifying
the downstream policy engine operator.
"""
from __future__ import annotations

import logging
import shutil
import subprocess

from vigilance.llm.base import LLMProvider

logger = logging.getLogger(__name__)

# ── Few-shot examples embedded in the system prompt ──────────────────────────
#
# Five domain-realistic examples covering the main rule shapes:
#   1. Deny with CIDR source condition               (network, OTE)
#   2. Time-bounded deny with exception clause       (auth, OTE)   ← mandated example
#   3. Allow for a specific authenticated subject    (iam, OTE)
#   4. Allow only when a prerequisite is satisfied   (iam, Siemens)
#   5. OT/industrial deny targeting a specific PLC   (ot, Siemens)
#
_FEW_SHOT_EXAMPLES = """\
### Example 1 — deny with CIDR source condition ###
NL: "Block all inbound traffic from 198.51.100.0/24 to the OTE core network."
REGO:
package vigilance.ote.network

default allow = true

deny if {
    net.cidr_contains("198.51.100.0/24", input.source_ip)
}

### Example 2 — time-bounded deny with management-VLAN exception ###
NL: "For OTE, deny authentication attempts to auth-server-01 from source IPs in \
203.0.113.0/24 for the next 24 hours, except from the management VLAN."
REGO:
package vigilance.ote.auth

default allow = true

# Expires 2026-07-09T00:00:00Z (compile-time: now + 24 h)
deny if {
    input.action == "authenticate"
    input.destination == "auth-server-01"
    net.cidr_contains("203.0.113.0/24", input.source_ip)
    time.now_ns() < 1783555200000000000
    not net.cidr_contains("10.20.0.0/16", input.source_ip)
}

### Example 3 — allow a specific authenticated subject ###
NL: "Allow the OTE NOC team service account to query SIEM logs on any destination."
REGO:
package vigilance.ote.iam

default allow = false

allow if {
    input.action == "query_logs"
    input.subject == "noc-service-account"
}

### Example 4 — require a prerequisite condition (MFA) ###
NL: "Require MFA for all admin access to the Siemens SCADA management interface."
REGO:
package vigilance.siemens.iam

default allow = false

allow if {
    input.action == "admin_access"
    input.destination == "scada-mgmt"
    input.resource == "mfa_verified"
}

### Example 5 — OT/industrial deny targeting a specific PLC ###
NL: "Deny all write commands to PLC-07 in Siemens SCADA Zone B unless the source \
is the engineering workstation at 10.30.1.5."
REGO:
package vigilance.siemens.ot

default allow = true

deny if {
    input.action == "write_command"
    input.destination == "PLC-07"
    not input.source_ip == "10.30.1.5"
}
"""

_SYSTEM_PROMPT = (
    "You are a security policy engineer for the VIGILANCE cybersecurity platform.\n"
    "Convert the natural language policy description into a valid OPA/Rego rule.\n"
    "Output ONLY the Rego code — no markdown fences, no explanation, no commentary.\n\n"
    "Package naming convention: vigilance.<pilot>.<domain>\n"
    "  pilot  in {ote, siemens, maritime, finance}  — inferred from context\n"
    "  domain in {auth, network, ot, iam, ...}      — inferred from policy intent\n\n"
    "Runtime input fields (provided by the OPA engine at evaluation time):\n"
    "  input.action      — action being attempted\n"
    "  input.source_ip   — source IP address\n"
    "  input.destination — target host, resource, or zone\n"
    "  input.subject     — authenticated identity\n"
    "  input.resource    — resource being accessed\n\n"
    + _FEW_SHOT_EXAMPLES
)


class PolicyTranslator:
    """Translate natural language policy descriptions to OPA/Rego rules.

    Flow: NL sentence → few-shot LLM prompt → OPA parse validation → Rego string.

    Retry semantics: on a parse failure the error is fed back to the LLM for a
    single correction attempt. If the retry also fails, ``_fallback_rego`` is
    returned (``default deny = true``) so the published rule fails closed rather
    than open. If OPA is not installed, validation and the retry are skipped and
    the LLM output is returned directly.
    """

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm
        self._opa_available = shutil.which("opa") is not None
        if not self._opa_available:
            logger.warning(
                "PolicyTranslator: 'opa' binary not found — Rego parse validation "
                "will be skipped. Add OPA to the container to enable validation."
            )

    def translate(self, nl_policy: str, llm: LLMProvider | None = None) -> str:
        """Translate a NL policy description to an OPA/Rego rule string.

        Args:
            nl_policy: Natural language description of the policy to enforce.
            llm: Optional LLM override (uses the constructor LLM if not provided).

        Returns:
            A Rego string ready for publication to ``t53.policy_updates``.
            Falls back to a safe deny-all rule if the LLM produces unparseable
            output after one retry.
        """
        provider = llm or self._llm
        messages: list[dict] = [
            {"role": "user", "content": f"Convert to Rego:\n{nl_policy}"}
        ]

        rego_candidate = self._strip_fences(provider.complete(_SYSTEM_PROMPT, messages))

        valid, error = self._validate_rego(rego_candidate)
        if valid:
            return rego_candidate

        # Retry once — feed the parse error back to the LLM
        messages.append({"role": "assistant", "content": rego_candidate})
        messages.append({
            "role": "user",
            "content": (
                f"That output failed to parse with error: {error}. "
                "Please fix and re-emit only valid Rego."
            ),
        })
        rego_retry = self._strip_fences(provider.complete(_SYSTEM_PROMPT, messages))

        valid_retry, error_retry = self._validate_rego(rego_retry)
        if valid_retry:
            return rego_retry

        logger.error(
            "PolicyTranslator: Rego generation failed after retry "
            "(error: %r) — publishing fallback deny rule.",
            error_retry,
        )
        return self._fallback_rego(nl_policy)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _validate_rego(self, rego: str) -> tuple[bool, str]:
        """Parse-validate ``rego`` with OPA.  Returns ``(is_valid, error_msg)``.

        Returns ``(True, "")`` immediately when OPA is not available (skips
        validation) or if a subprocess error occurs (never block the pipeline).
        """
        if not self._opa_available:
            return True, ""
        try:
            result = subprocess.run(
                ["opa", "parse", "-"],
                input=rego,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return True, ""
            return False, result.stderr.strip()
        except Exception as exc:
            logger.warning("PolicyTranslator: OPA parse subprocess error: %s", exc)
            return True, ""

    def _strip_fences(self, text: str) -> str:
        """Remove markdown code fences that the LLM may have wrapped the output in."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            inner = lines[1:]
            if inner and inner[-1].strip() == "```":
                inner = inner[:-1]
            text = "\n".join(inner).strip()
        return text

    def _fallback_rego(self, nl_policy: str) -> str:
        """Return a minimal safe deny-all rule used when LLM translation fails.

        Fails closed: ``default deny = true`` ensures no unintended access is
        granted when the translator cannot produce valid Rego.
        """
        return (
            "package vigilance.fallback\n\n"
            f"# Translation failed for: {nl_policy}\n"
            "default deny = true\n"
        )
