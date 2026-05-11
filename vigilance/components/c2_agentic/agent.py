"""C2 Agentic Interaction Layer — multi-turn tool-calling loop."""
from __future__ import annotations
import json
import uuid

from vigilance.components.c2_agentic.tools import dispatch_tool
from vigilance.llm.base import LLMProvider
from vigilance.models.agent_decision import AgentDecision
from vigilance.models.canonical_event import CanonicalEvent

_MAX_TURNS = 5


class AgentLoop:
    """Multi-turn agentic reasoning loop with tool calling.

    The loop runs up to MAX_TURNS iterations:
    - Turns 1-2: LLM may request tool calls (query_siem_logs, query_iam_sessions, etc.)
    - Turn 3+: LLM returns a final decision JSON

    Expected stub decision format:
    {
        "decision": "<threat_type>",
        "actions": ["action1", "action2", ...],
        "confidence": 0.95
    }
    """

    def run(
        self,
        event: CanonicalEvent,
        profile,
        llm: LLMProvider,
    ) -> AgentDecision:
        """Run the agentic loop and return an AgentDecision.

        Args:
            event: Normalized CanonicalEvent to analyze.
            profile: SectorProfile with system prompt and configuration.
            llm: LLMProvider for reasoning.

        Returns:
            AgentDecision with threat type, recommended actions, and confidence.
        """
        system_prompt = profile.llm_system_prompt
        messages: list[dict] = [
            {
                "role": "user",
                "content": (
                    f"Analyze this security event and determine appropriate response actions.\n"
                    f"Event type: {event.type}\n"
                    f"Severity: {event.severity}\n"
                    f"Source IP: {event.src_ip}\n"
                    f"Target: {event.target}\n"
                    f"Count: {event.count}\n"
                    f"Pilot: {event.pilot}\n"
                    f"Raw payload: {json.dumps(event.raw_payload)[:200]}"
                ),
            }
        ]

        turns = 0
        final_decision: dict | None = None

        for turn in range(1, _MAX_TURNS + 1):
            turns = turn
            response = llm.complete(system_prompt, messages)

            # Try to parse as JSON
            try:
                parsed = json.loads(response)
            except (json.JSONDecodeError, ValueError):
                # Not JSON — treat as plain text, keep going
                messages.append({"role": "assistant", "content": response})
                continue

            # Check if it's a tool call
            if "tool_call" in parsed:
                tool_name = parsed["tool_call"]
                params = parsed.get("params", {})
                tool_result = dispatch_tool(tool_name, params)

                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "tool", "content": tool_result})
                continue

            # Check if it's a final decision
            if "decision" in parsed and "actions" in parsed:
                final_decision = parsed
                break

            # Unknown JSON — keep appending and iterating
            messages.append({"role": "assistant", "content": response})

        if final_decision is None:
            # Fallback decision if loop exhausted without a decision
            final_decision = {
                "decision": "UNKNOWN_THREAT",
                "actions": ["notify_soc"],
                "confidence": 0.5,
            }

        return AgentDecision(
            decision_id=str(uuid.uuid4()),
            event_id=event.event_id,
            threat_type=final_decision["decision"],
            recommended_actions=final_decision["actions"],
            confidence=float(final_decision.get("confidence", 0.5)),
            reasoning_turns=turns,
            pilot=event.pilot,
        )
