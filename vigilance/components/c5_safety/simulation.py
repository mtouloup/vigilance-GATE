"""C5 Simulation Mode — dry-run and digital twin support."""
from __future__ import annotations


class SimulationMode:
    """Controls dry-run and digital twin simulation modes.

    - dry_run: C4 adapters log actions but don't execute (all results succeed with latency=0).
    - digital_twin: Accepts synthetic events from dt.events.synthetic broker topic.
    """

    def __init__(self, dry_run: bool = False, digital_twin: bool = False) -> None:
        self.dry_run = dry_run
        self.digital_twin = digital_twin

    def is_active(self) -> bool:
        """Return True if any simulation mode is active."""
        return self.dry_run or self.digital_twin

    def __repr__(self) -> str:
        return (
            f"SimulationMode(dry_run={self.dry_run}, digital_twin={self.digital_twin})"
        )
