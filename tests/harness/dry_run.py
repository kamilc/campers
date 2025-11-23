"""DryRunHarness for scenarios using moto AWS mocking."""

import logging
from dataclasses import dataclass


from tests.harness.base import ScenarioHarness
from tests.harness.services.artifacts import ArtifactManager
from tests.harness.services.configuration_env import ConfigurationEnv
from tests.harness.services.diagnostics import DiagnosticsCollector
from tests.harness.services.event_bus import EventBus
from tests.harness.services.resource_registry import ResourceRegistry
from tests.harness.services.signal_registry import SignalRegistry
from tests.harness.services.timeout_manager import TimeoutManager
from tests.harness.utils.port_allocator import PortAllocator


@dataclass
class ServiceContainer:
    """Container holding all harness services.

    Attributes
    ----------
    configuration_env : ConfigurationEnv
        Environment variable sandboxing
    signal_registry : SignalRegistry
        Short-lived event registry
    resource_registry : ResourceRegistry
        Resource lifecycle management
    timeout_manager : TimeoutManager
        Timeout budget tracking
    event_bus : EventBus
        Inter-component communication
    diagnostics : DiagnosticsCollector
        Diagnostic event collection
    artifacts : ArtifactManager
        Artifact directory management
    port_allocator : PortAllocator
        Thread-safe port allocation
    """

    configuration_env: ConfigurationEnv
    signal_registry: SignalRegistry
    resource_registry: ResourceRegistry
    timeout_manager: TimeoutManager
    event_bus: EventBus
    diagnostics: DiagnosticsCollector
    artifacts: ArtifactManager
    port_allocator: PortAllocator


class DryRunHarness(ScenarioHarness):
    """Harness for dry-run scenarios using moto AWS mocking.

    Provides isolated environment, mocked AWS services, and comprehensive
    resource lifecycle management for scenarios that don't require real
    AWS resources or LocalStack.
    """

    def setup(self) -> None:
        """Setup scenario-scoped resources and services."""
        scenario_timeout = getattr(self.context, "scenario_timeout", 180)

        self.services = ServiceContainer(
            configuration_env=ConfigurationEnv(),
            signal_registry=SignalRegistry(),
            resource_registry=ResourceRegistry(),
            timeout_manager=TimeoutManager(budget_seconds=scenario_timeout),
            event_bus=EventBus(),
            diagnostics=DiagnosticsCollector(verbose=False),
            artifacts=ArtifactManager(),
            port_allocator=PortAllocator(),
        )

        self.services.configuration_env.enter()
        self.services.configuration_env.unset("MOONDOCK_HARNESS_MANAGED")
        self.services.configuration_env.set("AWS_ACCESS_KEY_ID", "testing")
        self.services.configuration_env.set("AWS_SECRET_ACCESS_KEY", "testing")
        self.services.configuration_env.set("AWS_DEFAULT_REGION", "us-east-1")
        self.services.configuration_env.set("MOONDOCK_TEST_MODE", "1")

        scenario_dir = self.services.artifacts.create_scenario_dir(self.scenario.name)
        self.services.diagnostics.set_log_path(scenario_dir / "diagnostics.log")
        self.services.configuration_env.set("MOONDOCK_DIR", str(scenario_dir))
        self.services.diagnostics.record_system_snapshot(
            "setup-initial-state", include_thread_stacks=False
        )

    def cleanup(self) -> None:
        """Cleanup scenario-scoped resources and restore state.

        Ensures all cleanup operations complete even if individual operations fail.
        Restores environment variables last to ensure they're available during
        resource cleanup. Logs any errors but doesn't raise to prevent cleanup
        failures from affecting scenario status.
        """
        if self.services is None:
            return

        logger = logging.getLogger(__name__)
        errors = []

        self.services.diagnostics.record_system_snapshot(
            "cleanup-start", include_thread_stacks=False
        )

        try:
            self.services.resource_registry.cleanup_all()
        except Exception as e:
            errors.append(f"Resource cleanup failed: {e}")

        try:
            self.services.signal_registry.drain()
        except Exception as e:
            errors.append(f"Signal drain failed: {e}")

        try:
            self.services.event_bus.drain()
        except Exception as e:
            errors.append(f"Event bus drain failed: {e}")

        try:
            scenario_failed = self.scenario.status == "failed"
            if not scenario_failed:
                self.services.diagnostics.set_log_path(None)
            self.services.artifacts.cleanup(preserve_on_failure=scenario_failed)
        except Exception as e:
            errors.append(f"Artifact cleanup failed: {e}")

        try:
            self.services.configuration_env.exit()
        except Exception as e:
            errors.append(f"Environment restoration failed: {e}")

        if errors:
            logger.warning(
                f"Cleanup completed with {len(errors)} errors: {'; '.join(errors)}"
            )
        self.services.diagnostics.record_system_snapshot(
            "cleanup-complete", include_thread_stacks=False
        )
