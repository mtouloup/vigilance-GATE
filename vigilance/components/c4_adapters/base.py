"""Abstract ToolAdapter interface for C4 adapter plugins."""
from __future__ import annotations
from abc import ABC, abstractmethod

from vigilance.models.execution_result import ActionResult


class ToolAdapter(ABC):
    """Abstract base class for all C4 tool adapter plugins."""

    @abstractmethod
    def execute(self, action: str, params: dict) -> ActionResult:
        """Execute an action with the given parameters.

        Args:
            action: The action name to execute (e.g. 'block_ip').
            params: Action-specific parameters.

        Returns:
            ActionResult with success status, latency, and response details.
        """
        ...

    @property
    @abstractmethod
    def plugin_name(self) -> str:
        """Return the unique plugin identifier."""
        ...

    @property
    @abstractmethod
    def supported_actions(self) -> list[str]:
        """Return the list of action names this adapter supports."""
        ...
