"""Timeout budget management for scenario operations."""

import logging
import time
from contextlib import contextmanager
from typing import Iterator

from tests.harness.exceptions import HarnessTimeoutError

logger = logging.getLogger(__name__)


class TimeoutManager:
    """Manages timeout budgets for scenario operations.

    Tracks overall scenario deadline and allows allocating sub-budgets
    for nested operations. Provides checkpoint logging for elapsed/remaining time.

    Parameters
    ----------
    budget_seconds : float
        Total timeout budget in seconds
    """

    def __init__(self, budget_seconds: float) -> None:
        self.budget_seconds = budget_seconds
        self.start_time = time.monotonic()
        self.deadline = self.start_time + budget_seconds

    def elapsed_seconds(self) -> float:
        """Get elapsed time since start.

        Returns
        -------
        float
            Elapsed seconds
        """
        return time.monotonic() - self.start_time

    def remaining_seconds(self) -> float:
        """Get remaining time until deadline.

        Returns
        -------
        float
            Remaining seconds (may be negative if deadline passed)
        """
        return self.deadline - time.monotonic()

    def checkpoint(self, description: str) -> None:
        """Log elapsed and remaining time at a checkpoint.

        Parameters
        ----------
        description : str
            Description of checkpoint for logging
        """
        elapsed = self.elapsed_seconds()
        remaining = self.remaining_seconds()
        logger.debug(
            f"Timeout checkpoint '{description}': "
            f"elapsed={elapsed:.2f}s, remaining={remaining:.2f}s"
        )

    @contextmanager
    def sub_budget(self, name: str, max_seconds: float) -> Iterator[float]:
        """Create a sub-budget for a nested operation.

        Parameters
        ----------
        name : str
            Name of the operation (for logging)
        max_seconds : float
            Maximum time for this operation

        Yields
        ------
        float
            Actual available time (minimum of budget and operation timeout)

        Raises
        ------
        HarnessTimeoutError
            If scenario budget already exhausted
        """
        remaining = self.remaining_seconds()
        if remaining <= 0:
            raise HarnessTimeoutError(
                f"Scenario timeout budget exhausted (elapsed={self.elapsed_seconds():.2f}s)"
            )

        actual_budget = min(remaining, max_seconds)
        logger.debug(
            f"Sub-budget '{name}': requested={max_seconds}s, allocated={actual_budget:.2f}s"
        )

        try:
            yield actual_budget
        finally:
            self.checkpoint(f"End sub-budget '{name}'")
