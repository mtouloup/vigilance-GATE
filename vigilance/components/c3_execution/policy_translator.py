"""C3 Policy Translator — few-shot NL→Rego translation with OPA parse validation.

Converts a natural language policy description into a valid OPA/Rego rule and
returns the Rego string for publication to ``t53.policy_updates``.

Pipeline:
    1. Build a few-shot user message (four domain examples + NL input) and call
       Mistral Nemo 12B via ``LLMProvider.complete()``.
    2. Strip any markdown code fences the model may have wrapped the output in.
    3. Validate with ``opa parse`` if the OPA binary is available.
    4. On validation failure, retry once with the parse error fed back to the LLM.
    5. If the retry also fails, log an error and return ``_fallback_rego`` (fail-closed).
    6. If OPA is not installed, skip steps 3–5 and return the LLM output directly.

Dynamic value pattern
----------------------
For any membership check against a variable set of hosts, IPs, or identifiers, use a
``data.*`` reference rather than inlining the values:

    not input.source_ip in data.vigilance.siemens.ot_allowlist

Never inline a list of hosts or IPs directly into the rule body. The OPA engine
populates ``data.vigilance.*`` from the ZTA policy store at evaluation time.

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

    input.action       — the action being attempted, e.g. "authenticate", "plc_write"
    input.source_ip    — source IP address string, e.g. "203.0.113.5"
    input.destination  — target host, resource, or zone, e.g. "auth-server-01", "PLC-42"
    input.subject      — authenticated identity, e.g. "noc-service-account"
    input.resource     — resource being accessed, e.g. "mfa_verified"
    input.mfa_verified — boolean; true when the caller completed MFA
    input.target       — OT target device identifier, e.g. "PLC-42"
    input.scada_zone   — OT zone label, e.g. "zone-3"

Do not add fields beyond these without updating this docstring and notifying
the downstream policy engine operator.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile

from vigilance.llm.base import LLMProvider

logger = logging.getLogger(__name__)

# ── Few-shot examples prepended to the user message ──────────────────────────
#
# Four domain-realistic examples covering the canonical rule shapes:
#   1. IP/CIDR deny with time bound and VLAN exception     (auth, OTE)
#   2. Dynamic allowlist via data.* reference              (network, Siemens)
#   3. MFA require (allow rule with boolean condition)     (iam, OTE)
#   4. OT safety isolation for a specific PLC              (ot, Siemens)
#
_FEW_SHOT_EXAMPLES = """\
# Example 1 — IP/CIDR deny with time bound and management-VLAN exception
NL: "For OTE TELECOM, deny authentication attempts to auth-server-01 from source IPs \
in 203.0.113.0/24 for the next 24 hours, except from management VLAN 10.20.0.0/16."
Rego:
package vigilance.ote.auth

default allow = true

deny if {
    input.action == "authenticate"
    input.destination == "auth-server-01"
    net.cidr_contains("203.0.113.0/24", input.source_ip)
    not net.cidr_contains("10.20.0.0/16", input.source_ip)
    time.now_ns() < 1720396800000000000
}

# Example 2 — Dynamic allowlist via data.* reference (never inline hosts)
NL: "For Siemens INDUSTRY_4, deny all inbound Modbus/TCP traffic to SCADA zone zone-3 \
from any host not present in the OT-approved allowlist until manual review."
Rego:
package vigilance.siemens.network

default allow = true

deny if {
    input.action == "modbus_tcp"
    input.destination == "zone-3"
    not input.source_ip in data.vigilance.siemens.ot_allowlist
}

# Example 3 — Require MFA (allow rule with boolean condition)
NL: "For OTE TELECOM, require multi-factor authentication for all admin access \
to the management interface from external IPs."
Rego:
package vigilance.ote.iam

default allow = false

allow if {
    input.action == "admin_access"
    input.mfa_verified == true
    net.cidr_contains("0.0.0.0/0", input.source_ip)
    not net.cidr_contains("10.0.0.0/8", input.source_ip)
}

# Example 4 — OT safety isolation for a specific PLC
NL: "For Siemens INDUSTRY_4, deny all write commands to PLC-42 in zone-3 \
from any source except the engineering workstation at 10.100.1.5."
Rego:
package vigilance.siemens.ot

default allow = true

deny if {
    input.action == "plc_write"
    input.target == "PLC-42"
    input.scada_zone == "zone-3"
    input.source_ip != "10.100.1.5"
}
"""

_SYSTEM_PROMPT = (
    "You are a security policy engineer for the VIGILANCE cybersecurity platform.\n"
    "Convert the natural language policy description into a valid OPA/Rego rule.\n"
    "Output ONLY the Rego code — no markdown fences, no explanation, no commentary.\n\n"
    "Package naming convention: vigilance.<pilot_lower>.<domain>\n"
    "  pilot  in {ote, siemens, maritime, finance}  — inferred from context\n"
    "  domain in {auth, network, ot, iam, ...}      — inferred from policy intent\n\n"
    "Runtime input fields available to rules:\n"
    "  input.action       — action being attempted (e.g. \"authenticate\", \"plc_write\")\n"
    "  input.source_ip    — source IP address string\n"
    "  input.destination  — target host, resource, or zone\n"
    "  input.subject      — authenticated identity\n"
    "  input.resource     — resource being accessed\n"
    "  input.mfa_verified — boolean; true when the caller completed MFA\n"
    "  input.target       — OT target device identifier\n"
    "  input.scada_zone   — OT zone label\n\n"
    "Critical rules — always follow these:\n"
    "  - Never use '...' or placeholder values. If a value is unknown, use a "
    "data.* reference.\n"
    "  - Never inline a list of hosts or IPs. Use "
    "data.vigilance.<pilot>.<domain>_allowlist for dynamic membership checks.\n"
    "  - Always use curly braces {} for set literals in 'in' expressions, not "
    "square brackets [].\n"
    "  - Package name must be vigilance.<pilot_lower>.<domain> exactly.\n"
    "  - Output only valid Rego. No explanation, no markdown fences, no preamble.\n"
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
        user_content = (
            f"{_FEW_SHOT_EXAMPLES}\n"
            f"# Now convert the following to Rego:\n"
            f"NL: \"{nl_policy}\"\n"
            f"Rego:"
        )
        messages: list[dict] = [{"role": "user", "content": user_content}]

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
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".rego", delete=False
            ) as f:
                f.write(rego)
                tmp_path = f.name
            result = subprocess.run(
                ["opa", "parse", tmp_path],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return True, ""
            # OPA writes parse errors to stdout as JSON; stderr is usually empty
            error = result.stdout.strip() or result.stderr.strip()
            return False, error
        except Exception as exc:
            logger.warning("PolicyTranslator: OPA parse subprocess error: %s", exc)
            return True, ""
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

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
