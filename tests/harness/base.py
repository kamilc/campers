"""Abstract base class for scenario harness implementations."""

from abc import ABC, abstractmethod

from behave.model import Scenario
from behave.runner import Context


class ScenarioHarness(ABC):
    """Abstract base class providing lifecycle management for test scenarios.

    Harness implementations encapsulate scenario-scoped state and resource
    lifecycle management, eliminating global state and race conditions.

    Parameters
    ----------
    context : Context
        Behave context object for the current scenario
    scenario : Scenario
        Behave scenario object containing metadata and tags
    """

    def __init__(self, context: Context, scenario: Scenario) -> None:
        self.context = context
        self.scenario = scenario
        self.services = None

    @abstractmethod
    def setup(self) -> None:
        """Setup scenario-scoped resources and services.

        Called in before_scenario hook. Implementations should initialize
        all services, inject dependencies, and prepare test environment.
        """
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """Cleanup scenario-scoped resources and restore state.

        Called in after_scenario hook. Implementations should dispose
        all resources, restore environment variables, and preserve/delete
        artifacts based on scenario outcome.
        """
        pass
