"""Unit tests for DryRunHarness implementation."""

import os
from unittest.mock import MagicMock

import pytest

from behave.model import Scenario
from behave.runner import Context

from tests.harness.dry_run import DryRunHarness, ServiceContainer
from tests.harness.exceptions import HarnessTimeoutError
from tests.harness.services.event_bus import Event


class TestServiceContainerCreation:
    """Test ServiceContainer creation."""

    def test_create_service_container(self) -> None:
        """Test creating a service container."""
        from tests.harness.services.artifacts import ArtifactManager
        from tests.harness.services.configuration_env import ConfigurationEnv
        from tests.harness.services.diagnostics import DiagnosticsCollector
        from tests.harness.services.event_bus import EventBus
        from tests.harness.services.resource_registry import ResourceRegistry
        from tests.harness.services.signal_registry import SignalRegistry
        from tests.harness.services.timeout_manager import TimeoutManager
        from tests.harness.utils.port_allocator import PortAllocator

        container = ServiceContainer(
            configuration_env=ConfigurationEnv(),
            signal_registry=SignalRegistry(),
            resource_registry=ResourceRegistry(),
            timeout_manager=TimeoutManager(budget_seconds=180),
            event_bus=EventBus(),
            diagnostics=DiagnosticsCollector(),
            artifacts=ArtifactManager(),
            port_allocator=PortAllocator(),
        )

        assert container.configuration_env is not None
        assert container.signal_registry is not None
        assert container.resource_registry is not None
        assert container.timeout_manager is not None
        assert container.event_bus is not None
        assert container.diagnostics is not None
        assert container.artifacts is not None
        assert container.port_allocator is not None


class TestDryRunHarnessSetup:
    """Test DryRunHarness setup."""

    def test_setup_creates_service_container(self) -> None:
        """Test setup creates a service container."""
        context = MagicMock(spec=Context)
        scenario = MagicMock(spec=Scenario)
        scenario.name = "Test Scenario"

        harness = DryRunHarness(context, scenario)
        harness.setup()

        assert harness.services is not None

    def test_setup_initializes_all_services(self) -> None:
        """Test setup initializes all services."""
        context = MagicMock(spec=Context)
        scenario = MagicMock(spec=Scenario)
        scenario.name = "Test Scenario"

        harness = DryRunHarness(context, scenario)
        harness.setup()

        assert harness.services.configuration_env is not None
        assert harness.services.signal_registry is not None
        assert harness.services.resource_registry is not None
        assert harness.services.timeout_manager is not None
        assert harness.services.event_bus is not None
        assert harness.services.diagnostics is not None
        assert harness.services.artifacts is not None
        assert harness.services.port_allocator is not None

    def test_setup_configures_aws_credentials(self) -> None:
        """Test setup configures AWS credentials."""
        context = MagicMock(spec=Context)
        scenario = MagicMock(spec=Scenario)
        scenario.name = "Test Scenario"

        original_key_id = os.environ.get("AWS_ACCESS_KEY_ID")
        original_secret = os.environ.get("AWS_SECRET_ACCESS_KEY")
        original_region = os.environ.get("AWS_DEFAULT_REGION")

        try:
            harness = DryRunHarness(context, scenario)
            harness.setup()

            assert os.environ.get("AWS_ACCESS_KEY_ID") == "testing"
            assert os.environ.get("AWS_SECRET_ACCESS_KEY") == "testing"
            assert os.environ.get("AWS_DEFAULT_REGION") == "us-east-1"
        finally:
            if original_key_id:
                os.environ["AWS_ACCESS_KEY_ID"] = original_key_id
            elif "AWS_ACCESS_KEY_ID" in os.environ:
                del os.environ["AWS_ACCESS_KEY_ID"]

            if original_secret:
                os.environ["AWS_SECRET_ACCESS_KEY"] = original_secret
            elif "AWS_SECRET_ACCESS_KEY" in os.environ:
                del os.environ["AWS_SECRET_ACCESS_KEY"]

            if original_region:
                os.environ["AWS_DEFAULT_REGION"] = original_region
            elif "AWS_DEFAULT_REGION" in os.environ:
                del os.environ["AWS_DEFAULT_REGION"]

    def test_setup_creates_artifact_directory(self) -> None:
        """Test setup creates artifact directory."""
        context = MagicMock(spec=Context)
        scenario = MagicMock(spec=Scenario)
        scenario.name = "Test Scenario"

        harness = DryRunHarness(context, scenario)
        harness.setup()

        assert harness.services.artifacts.scenario_dir is not None


class TestDryRunHarnessCleanup:
    """Test DryRunHarness cleanup."""

    def test_cleanup_without_services_safe(self) -> None:
        """Test cleanup without services doesn't raise."""
        context = MagicMock(spec=Context)
        scenario = MagicMock(spec=Scenario)

        harness = DryRunHarness(context, scenario)
        harness.services = None

        harness.cleanup()

    def test_cleanup_with_passed_scenario(self) -> None:
        """Test cleanup deletes artifacts for passed scenario."""
        context = MagicMock(spec=Context)
        scenario = MagicMock(spec=Scenario)
        scenario.name = "Test Scenario"
        scenario.status = "passed"

        harness = DryRunHarness(context, scenario)
        harness.setup()

        artifact_dir = harness.services.artifacts.scenario_dir
        assert artifact_dir.exists()

        harness.cleanup()

        assert not artifact_dir.exists()

    def test_cleanup_with_failed_scenario(self) -> None:
        """Test cleanup preserves artifacts for failed scenario."""
        context = MagicMock(spec=Context)
        scenario = MagicMock(spec=Scenario)
        scenario.name = "Test Scenario"
        scenario.status = "failed"

        harness = DryRunHarness(context, scenario)
        harness.setup()

        artifact_dir = harness.services.artifacts.scenario_dir

        harness.cleanup()

        assert artifact_dir.exists()

        if artifact_dir.exists():
            import shutil

            shutil.rmtree(artifact_dir)

    def test_cleanup_drains_signal_registry(self) -> None:
        """Test cleanup drains signal registry."""
        context = MagicMock(spec=Context)
        scenario = MagicMock(spec=Scenario)
        scenario.name = "Test Scenario"
        scenario.status = "passed"

        harness = DryRunHarness(context, scenario)
        harness.setup()

        harness.services.signal_registry.publish("test-signal", "data")

        harness.cleanup()

        with pytest.raises(HarnessTimeoutError):
            harness.services.signal_registry.wait_for("test-signal", timeout=0.1)

    def test_cleanup_drains_event_bus(self) -> None:
        """Test cleanup drains event bus."""
        context = MagicMock(spec=Context)
        scenario = MagicMock(spec=Scenario)
        scenario.name = "Test Scenario"
        scenario.status = "passed"

        harness = DryRunHarness(context, scenario)
        harness.setup()

        harness.services.event_bus.publish(
            Event(type="test-channel", instance_id=None, data={"payload": "event"})
        )

        harness.cleanup()

        assert harness.services.event_bus.drain_all() == {}

    def test_cleanup_continues_on_resource_registry_error(self) -> None:
        """Test cleanup continues even if resource registry cleanup fails."""
        context = MagicMock(spec=Context)
        scenario = MagicMock(spec=Scenario)
        scenario.name = "Error Test Scenario"
        scenario.status = "passed"

        harness = DryRunHarness(context, scenario)
        harness.setup()

        harness.services.resource_registry.cleanup_all = MagicMock(
            side_effect=RuntimeError("Resource cleanup failed")
        )

        harness.cleanup()

    def test_cleanup_continues_on_signal_registry_error(self) -> None:
        """Test cleanup continues even if signal registry drain fails."""
        context = MagicMock(spec=Context)
        scenario = MagicMock(spec=Scenario)
        scenario.name = "Signal Error Test Scenario"
        scenario.status = "passed"

        harness = DryRunHarness(context, scenario)
        harness.setup()

        harness.services.signal_registry.drain = MagicMock(
            side_effect=RuntimeError("Signal drain failed")
        )

        harness.cleanup()

    def test_cleanup_continues_on_event_bus_error(self) -> None:
        """Test cleanup continues even if event bus drain fails."""
        context = MagicMock(spec=Context)
        scenario = MagicMock(spec=Scenario)
        scenario.name = "Event Bus Error Test Scenario"
        scenario.status = "passed"

        harness = DryRunHarness(context, scenario)
        harness.setup()

        harness.services.event_bus.drain = MagicMock(
            side_effect=RuntimeError("Event bus drain failed")
        )

        harness.cleanup()

    def test_cleanup_continues_on_artifacts_error(self) -> None:
        """Test cleanup continues even if artifact cleanup fails."""
        context = MagicMock(spec=Context)
        scenario = MagicMock(spec=Scenario)
        scenario.name = "Artifacts Error Test Scenario"
        scenario.status = "passed"

        harness = DryRunHarness(context, scenario)
        harness.setup()

        harness.services.artifacts.cleanup = MagicMock(
            side_effect=RuntimeError("Artifact cleanup failed")
        )

        harness.cleanup()

    def test_cleanup_continues_on_configuration_env_error(self) -> None:
        """Test cleanup continues even if configuration env exit fails."""
        context = MagicMock(spec=Context)
        scenario = MagicMock(spec=Scenario)
        scenario.name = "Env Error Test Scenario"
        scenario.status = "passed"

        harness = DryRunHarness(context, scenario)
        harness.setup()

        harness.services.configuration_env.exit = MagicMock(
            side_effect=RuntimeError("Environment restoration failed")
        )

        harness.cleanup()

    def test_cleanup_continues_with_multiple_errors(self) -> None:
        """Test cleanup handles multiple simultaneous errors."""
        context = MagicMock(spec=Context)
        scenario = MagicMock(spec=Scenario)
        scenario.name = "Multiple Errors Test Scenario"
        scenario.status = "passed"

        harness = DryRunHarness(context, scenario)
        harness.setup()

        harness.services.resource_registry.cleanup_all = MagicMock(
            side_effect=RuntimeError("Resource cleanup failed")
        )
        harness.services.signal_registry.drain = MagicMock(
            side_effect=RuntimeError("Signal drain failed")
        )

        harness.cleanup()


class TestDryRunHarnessIntegration:
    """Test DryRunHarness integration."""

    def test_full_lifecycle(self) -> None:
        """Test complete setup/cleanup lifecycle."""
        context = MagicMock(spec=Context)
        scenario = MagicMock(spec=Scenario)
        scenario.name = "Integration Test"
        scenario.status = "passed"

        harness = DryRunHarness(context, scenario)

        harness.setup()
        assert harness.services is not None

        harness.services.signal_registry.publish("test-signal", "test-data")
        harness.services.event_bus.publish(
            Event(type="test-channel", instance_id=None, data={"payload": "event"})
        )

        artifact_dir = harness.services.artifacts.scenario_dir
        assert artifact_dir.exists()

        harness.cleanup()

        assert not artifact_dir.exists()

    def test_configuration_env_isolation_across_setup_cleanup(self) -> None:
        """Test environment variable isolation across setup and cleanup."""
        context = MagicMock(spec=Context)
        scenario = MagicMock(spec=Scenario)
        scenario.name = "Isolation Test Scenario"
        scenario.status = "passed"

        original_aws_key = os.environ.get("AWS_ACCESS_KEY_ID")
        original_aws_secret = os.environ.get("AWS_SECRET_ACCESS_KEY")
        original_region = os.environ.get("AWS_DEFAULT_REGION")
        original_moondock_dir = os.environ.get("MOONDOCK_DIR")

        try:
            os.environ["CUSTOM_VAR"] = "before_harness"

            harness = DryRunHarness(context, scenario)
            harness.setup()

            assert os.environ.get("AWS_ACCESS_KEY_ID") == "testing"
            assert os.environ.get("AWS_SECRET_ACCESS_KEY") == "testing"
            assert os.environ.get("AWS_DEFAULT_REGION") == "us-east-1"
            assert "MOONDOCK_DIR" in os.environ
            assert os.environ.get("CUSTOM_VAR") == "before_harness"

            harness.services.configuration_env.set("CUSTOM_VAR", "modified_in_harness")
            assert os.environ.get("CUSTOM_VAR") == "modified_in_harness"

            harness.cleanup()

            assert os.environ.get("CUSTOM_VAR") == "before_harness"
            assert (
                "AWS_ACCESS_KEY_ID" not in os.environ
                or os.environ.get("AWS_ACCESS_KEY_ID") == original_aws_key
            )
            assert (
                "AWS_SECRET_ACCESS_KEY" not in os.environ
                or os.environ.get("AWS_SECRET_ACCESS_KEY") == original_aws_secret
            )
            assert (
                "AWS_DEFAULT_REGION" not in os.environ
                or os.environ.get("AWS_DEFAULT_REGION") == original_region
            )
            assert (
                "MOONDOCK_DIR" not in os.environ
                or os.environ.get("MOONDOCK_DIR") == original_moondock_dir
            )

        finally:
            if original_aws_key:
                os.environ["AWS_ACCESS_KEY_ID"] = original_aws_key
            elif "AWS_ACCESS_KEY_ID" in os.environ:
                del os.environ["AWS_ACCESS_KEY_ID"]

            if original_aws_secret:
                os.environ["AWS_SECRET_ACCESS_KEY"] = original_aws_secret
            elif "AWS_SECRET_ACCESS_KEY" in os.environ:
                del os.environ["AWS_SECRET_ACCESS_KEY"]

            if original_region:
                os.environ["AWS_DEFAULT_REGION"] = original_region
            elif "AWS_DEFAULT_REGION" in os.environ:
                del os.environ["AWS_DEFAULT_REGION"]

            if original_moondock_dir:
                os.environ["MOONDOCK_DIR"] = original_moondock_dir
            elif "MOONDOCK_DIR" in os.environ:
                del os.environ["MOONDOCK_DIR"]

            if "CUSTOM_VAR" in os.environ:
                del os.environ["CUSTOM_VAR"]

    def test_environment_vars_available_during_resource_cleanup(self) -> None:
        """Test that environment variables are available during resource cleanup.

        Verifies cleanup order: resources are cleaned up BEFORE environment
        is restored, ensuring cleanup operations can access environment vars.
        """
        context = MagicMock(spec=Context)
        scenario = MagicMock(spec=Scenario)
        scenario.name = "Cleanup Order Test"
        scenario.status = "passed"

        captured_env_during_cleanup = {}

        def capture_env_during_resource_cleanup():
            captured_env_during_cleanup["AWS_ACCESS_KEY_ID"] = os.environ.get(
                "AWS_ACCESS_KEY_ID"
            )
            captured_env_during_cleanup["AWS_SECRET_ACCESS_KEY"] = os.environ.get(
                "AWS_SECRET_ACCESS_KEY"
            )
            captured_env_during_cleanup["AWS_DEFAULT_REGION"] = os.environ.get(
                "AWS_DEFAULT_REGION"
            )
            captured_env_during_cleanup["MOONDOCK_DIR"] = os.environ.get("MOONDOCK_DIR")

        original_aws_key = os.environ.get("AWS_ACCESS_KEY_ID")
        original_aws_secret = os.environ.get("AWS_SECRET_ACCESS_KEY")
        original_region = os.environ.get("AWS_DEFAULT_REGION")
        original_moondock_dir = os.environ.get("MOONDOCK_DIR")

        try:
            harness = DryRunHarness(context, scenario)
            harness.setup()

            harness.services.resource_registry.cleanup_all = MagicMock(
                side_effect=capture_env_during_resource_cleanup
            )

            harness.cleanup()

            assert captured_env_during_cleanup["AWS_ACCESS_KEY_ID"] == "testing"
            assert captured_env_during_cleanup["AWS_SECRET_ACCESS_KEY"] == "testing"
            assert captured_env_during_cleanup["AWS_DEFAULT_REGION"] == "us-east-1"
            assert captured_env_during_cleanup["MOONDOCK_DIR"] is not None

        finally:
            if original_aws_key:
                os.environ["AWS_ACCESS_KEY_ID"] = original_aws_key
            elif "AWS_ACCESS_KEY_ID" in os.environ:
                del os.environ["AWS_ACCESS_KEY_ID"]

            if original_aws_secret:
                os.environ["AWS_SECRET_ACCESS_KEY"] = original_aws_secret
            elif "AWS_SECRET_ACCESS_KEY" in os.environ:
                del os.environ["AWS_SECRET_ACCESS_KEY"]

            if original_region:
                os.environ["AWS_DEFAULT_REGION"] = original_region
            elif "AWS_DEFAULT_REGION" in os.environ:
                del os.environ["AWS_DEFAULT_REGION"]

            if original_moondock_dir:
                os.environ["MOONDOCK_DIR"] = original_moondock_dir
            elif "MOONDOCK_DIR" in os.environ:
                del os.environ["MOONDOCK_DIR"]
