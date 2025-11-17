"""Unit tests for ScenarioHarness base class."""

from unittest.mock import MagicMock

import pytest

from behave.model import Scenario
from behave.runner import Context

from tests.unit.harness.base import ScenarioHarness


class ConcreteHarness(ScenarioHarness):
    """Concrete implementation for testing."""

    def __init__(self, context: Context, scenario: Scenario) -> None:
        super().__init__(context, scenario)
        self.setup_called = False
        self.cleanup_called = False

    def setup(self) -> None:
        self.setup_called = True

    def cleanup(self) -> None:
        self.cleanup_called = True


class TestScenarioHarnessInitialization:
    """Test harness initialization."""

    def test_initialize_with_context_and_scenario(self) -> None:
        """Test initializing harness with context and scenario."""
        context = MagicMock(spec=Context)
        scenario = MagicMock(spec=Scenario)

        harness = ConcreteHarness(context, scenario)

        assert harness.context is context
        assert harness.scenario is scenario
        assert harness.services is None

    def test_initialize_sets_empty_services(self) -> None:
        """Test services is initially None."""
        context = MagicMock(spec=Context)
        scenario = MagicMock(spec=Scenario)

        harness = ConcreteHarness(context, scenario)

        assert harness.services is None


class TestScenarioHarnessLifecycle:
    """Test harness lifecycle methods."""

    def test_setup_can_be_called(self) -> None:
        """Test setup method can be called."""
        context = MagicMock(spec=Context)
        scenario = MagicMock(spec=Scenario)

        harness = ConcreteHarness(context, scenario)
        harness.setup()

        assert harness.setup_called is True

    def test_cleanup_can_be_called(self) -> None:
        """Test cleanup method can be called."""
        context = MagicMock(spec=Context)
        scenario = MagicMock(spec=Scenario)

        harness = ConcreteHarness(context, scenario)
        harness.cleanup()

        assert harness.cleanup_called is True

    def test_setup_and_cleanup_sequence(self) -> None:
        """Test setup followed by cleanup."""
        context = MagicMock(spec=Context)
        scenario = MagicMock(spec=Scenario)

        harness = ConcreteHarness(context, scenario)

        harness.setup()
        assert harness.setup_called is True
        assert harness.cleanup_called is False

        harness.cleanup()
        assert harness.cleanup_called is True


class TestScenarioHarnessAbstraction:
    """Test abstract base class behavior."""

    def test_cannot_instantiate_abstract_class(self) -> None:
        """Test cannot instantiate ScenarioHarness directly."""
        context = MagicMock(spec=Context)
        scenario = MagicMock(spec=Scenario)

        with pytest.raises(TypeError):
            ScenarioHarness(context, scenario)

    def test_must_implement_setup(self) -> None:
        """Test subclass must implement setup."""
        context = MagicMock(spec=Context)
        scenario = MagicMock(spec=Scenario)

        class IncompleteHarness(ScenarioHarness):
            def cleanup(self) -> None:
                pass

        with pytest.raises(TypeError):
            IncompleteHarness(context, scenario)

    def test_must_implement_cleanup(self) -> None:
        """Test subclass must implement cleanup."""
        context = MagicMock(spec=Context)
        scenario = MagicMock(spec=Scenario)

        class IncompleteHarness(ScenarioHarness):
            def setup(self) -> None:
                pass

        with pytest.raises(TypeError):
            IncompleteHarness(context, scenario)
