"""C3 Policy Translator — converts natural language policies to OPA/Rego stubs."""
from __future__ import annotations

from vigilance.llm.base import LLMProvider


class PolicyTranslator:
    """Translate natural language policy descriptions to OPA/Rego rules.

    Uses the LLM provider with a policy-focused system prompt.
    All actual Rego generation is stubbed for the framework prototype.
    """

    _SYSTEM_PROMPT = (
        "You are a security policy engineer. Convert the natural language policy "
        "description into a valid OPA/Rego rule. Output only valid Rego code."
    )

    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    def translate(self, nl_policy: str, llm: LLMProvider | None = None) -> str:
        """Translate a NL policy description to an OPA/Rego rule string.

        Args:
            nl_policy: Natural language description of the policy.
            llm: Optional LLM override (uses constructor LLM if not provided).

        Returns:
            A stub OPA/Rego rule string.
        """
        provider = llm or self._llm
        messages = [{"role": "user", "content": f"Convert to Rego: {nl_policy}"}]
        result = provider.complete(self._SYSTEM_PROMPT, messages)

        # If the LLM returned a JSON tool call or decision, extract the Rego stub
        if result.strip().startswith("{"):
            return self._fallback_rego(nl_policy)
        return result

    def _fallback_rego(self, nl_policy: str) -> str:
        """Generate a minimal fallback Rego rule."""
        safe_name = (
            nl_policy.lower()
            .replace(" ", "_")
            .replace("-", "_")[:40]
        )
        return (
            f"package vigilance.policy\n\n"
            f"# Policy: {nl_policy}\n"
            f"default {safe_name} = false\n\n"
            f"{safe_name} {{\n"
            f'    input.action != ""\n'
            f'    input.src_ip != ""\n'
            f"}}\n"
        )
