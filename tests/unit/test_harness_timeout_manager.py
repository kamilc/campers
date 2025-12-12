"""Unit tests for TimeoutManager service."""

import time

import pytest

from tests.harness.exceptions import HarnessTimeoutError
from tests.harness.services.timeout_manager import TimeoutManager


class TestTimeoutManagerBasic:
    """Test basic timeout tracking."""

    def test_elapsed_seconds(self) -> None:
        """Test elapsed time calculation."""
        manager = TimeoutManager(budget_seconds=10.0)
        time.sleep(0.1)
        elapsed = manager.elapsed_seconds()
        assert elapsed >= 0.1

    def test_remaining_seconds(self) -> None:
        """Test remaining time calculation."""
        manager = TimeoutManager(budget_seconds=10.0)
        time.sleep(0.1)
        remaining = manager.remaining_seconds()
        assert remaining < 10.0
        assert remaining > 9.0

    def test_checkpoint_logging(self) -> None:
        """Test checkpoint method doesn't raise."""
        manager = TimeoutManager(budget_seconds=10.0)
        manager.checkpoint("test checkpoint")


class TestTimeoutManagerSubBudget:
    """Test sub-budget context manager."""

    def test_sub_budget_context_manager(self) -> None:
        """Test sub-budget allocation and yielding."""
        manager = TimeoutManager(budget_seconds=10.0)

        with manager.sub_budget("operation", 5.0) as budget:
            assert budget > 0
            assert budget <= 5.0

    def test_sub_budget_within_available_budget(self) -> None:
        """Test sub-budget respects scenario budget."""
        manager = TimeoutManager(budget_seconds=10.0)

        with manager.sub_budget("operation", 15.0) as budget:
            assert budget < 10.0

    def test_sub_budget_on_exhausted_budget_raises(self) -> None:
        """Test sub-budget raises HarnessTimeoutError when budget exhausted."""
        manager = TimeoutManager(budget_seconds=0.1)
        time.sleep(0.2)

        with pytest.raises(HarnessTimeoutError), manager.sub_budget("operation", 5.0):
            pass

    def test_multiple_sub_budgets(self) -> None:
        """Test multiple sub-budgets in sequence."""
        manager = TimeoutManager(budget_seconds=10.0)

        with manager.sub_budget("op1", 3.0) as budget1:
            assert budget1 > 0

        with manager.sub_budget("op2", 3.0) as budget2:
            assert budget2 > 0

    def test_checkpoint_after_sub_budget(self) -> None:
        """Test checkpoint can be called after sub-budget."""
        manager = TimeoutManager(budget_seconds=10.0)

        with manager.sub_budget("operation", 5.0):
            manager.checkpoint("inside sub-budget")

        manager.checkpoint("after sub-budget")


class TestTimeoutManagerEdgeCases:
    """Test edge cases."""

    def test_zero_budget(self) -> None:
        """Test manager with zero budget."""
        manager = TimeoutManager(budget_seconds=0.0)
        time.sleep(0.1)

        with pytest.raises(HarnessTimeoutError), manager.sub_budget("operation", 1.0):
            pass

    def test_very_small_budget(self) -> None:
        """Test manager with very small budget."""
        manager = TimeoutManager(budget_seconds=0.001)
        time.sleep(0.01)

        with pytest.raises(HarnessTimeoutError), manager.sub_budget("operation", 0.1):
            pass

    def test_large_budget(self) -> None:
        """Test manager with large budget."""
        manager = TimeoutManager(budget_seconds=3600.0)

        with manager.sub_budget("operation", 300.0) as budget:
            assert budget == 300.0

    def test_elapsed_negative_remaining(self) -> None:
        """Test elapsed time exceeds budget."""
        manager = TimeoutManager(budget_seconds=0.05)
        time.sleep(0.1)

        elapsed = manager.elapsed_seconds()
        remaining = manager.remaining_seconds()

        assert elapsed > 0.05
        assert remaining < 0
