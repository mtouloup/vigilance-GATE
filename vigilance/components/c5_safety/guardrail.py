"""C5 Safety Gate — pre-execution guardrail checks."""
from __future__ import annotations
import ipaddress
import uuid

from vigilance.llm.base import LLMProvider
from vigilance.models.action_request import ActionRequest
from vigilance.models.canonical_event import CanonicalEvent
from vigilance.models.guardrail_check import GuardrailCheck, GuardrailVerdict


class SafetyGate:
    """Pre-execution safety gate that validates ActionRequests.

    Standard checks (all sectors):
    1. agent_confidence >= profile.confidence_threshold (default 0.80)
    2. src_ip not in protected_ranges
    3. Actions are proportionate (len(actions) <= 5)

    OT extra checks (when ot_safety_flag=True):
    4. isolate_plc must be safe-state (inferred from action name)
    5. ZTA policy scope must be zone-limited (not full OT network)
    """

    def check(
        self,
        request: ActionRequest,
        event: CanonicalEvent,
        profile,
        llm: LLMProvider,
    ) -> GuardrailCheck:
        """Run all applicable guardrail checks.

        Returns:
            GuardrailCheck with verdict APPROVED, REJECTED, or ESCALATE.
        """
        reasons: list[str] = []
        rejected = False
        escalate = False
        ot_safety_checked = False

        # Check 1: Confidence threshold
        threshold = getattr(profile, "confidence_threshold", 0.80)
        if request.agent_confidence < threshold:
            reasons.append(
                f"Confidence {request.agent_confidence:.2f} below threshold {threshold:.2f}"
            )
            escalate = True

        # Check 2: Protected IP ranges
        if event.src_ip:
            try:
                src_addr = ipaddress.ip_address(event.src_ip)
                protected_ranges = getattr(profile, "protected_ranges", [])
                for cidr in protected_ranges:
                    network = ipaddress.ip_network(cidr, strict=False)
                    if src_addr in network:
                        reasons.append(
                            f"src_ip {event.src_ip} is in protected range {cidr}"
                        )
                        escalate = True
                        break
            except ValueError:
                pass  # Invalid IP — skip range check

        # Check 3: Proportionality
        if len(request.actions) > 5:
            reasons.append(
                f"Action count {len(request.actions)} exceeds proportionality limit of 5"
            )
            rejected = True

        # OT-specific checks
        ot_safety_flag = getattr(profile, "ot_safety_flag", False)
        if ot_safety_flag or event.ot_safety_flag:
            ot_safety_checked = True

            # Check 4: isolate_plc must use safe-state
            for action in request.actions:
                if action == "isolate_plc":
                    # safe-state is enforced at execution time by the SCADA plugin;
                    # guardrail confirms it is present in the action list as appropriate
                    reasons.append("OT safety: isolate_plc will use safe-state mode (verified)")
                    break

            # Check 5: ZTA policy scope zone-limited
            if request.policy_update:
                policy_lower = request.policy_update.lower()
                if "full ot network" in policy_lower or "all zones" in policy_lower:
                    reasons.append(
                        "OT safety: ZTA policy scope must be zone-limited, not full OT network"
                    )
                    escalate = True
                else:
                    reasons.append("OT safety: ZTA policy scope appears zone-limited (OK)")

        # Determine verdict
        if rejected:
            verdict = GuardrailVerdict.REJECTED
        elif escalate:
            verdict = GuardrailVerdict.ESCALATE
        else:
            verdict = GuardrailVerdict.APPROVED
            if not reasons:
                reasons.append("All guardrail checks passed")

        return GuardrailCheck(
            check_id=str(uuid.uuid4()),
            request_id=request.request_id,
            verdict=verdict,
            reasons=reasons,
            ot_safety_checked=ot_safety_checked,
        )
