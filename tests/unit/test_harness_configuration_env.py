"""Unit tests for ConfigurationEnv service."""

import os

import pytest

from tests.unit.harness.services.configuration_env import ConfigurationEnv


class TestConfigurationEnvSetUnset:
    """Test basic set/unset operations."""

    def test_set_environment_variable(self) -> None:
        """Test setting an environment variable."""
        env = ConfigurationEnv()

        with env:
            env.set("TEST_VAR", "test_value")
            assert os.environ["TEST_VAR"] == "test_value"

    def test_unset_environment_variable(self) -> None:
        """Test unsetting an environment variable."""
        env = ConfigurationEnv()

        with env:
            env.set("TEST_VAR", "test_value")
            assert "TEST_VAR" in os.environ

            env.unset("TEST_VAR")
            assert "TEST_VAR" not in os.environ

    def test_unset_nonexistent_variable_does_not_raise(self) -> None:
        """Test unsetting a non-existent variable doesn't raise."""
        env = ConfigurationEnv()

        with env:
            env.unset("NONEXISTENT_VAR")


class TestConfigurationEnvContextManager:
    """Test context manager behavior."""

    def test_restore_environment_on_context_exit(self) -> None:
        """Test environment is restored after context exit."""
        original_value = "original"
        os.environ["TEST_VAR"] = original_value

        try:
            env = ConfigurationEnv()

            with env:
                env.set("TEST_VAR", "modified")
                assert os.environ["TEST_VAR"] == "modified"

            assert os.environ["TEST_VAR"] == original_value
        finally:
            if "TEST_VAR" in os.environ:
                del os.environ["TEST_VAR"]

    def test_restore_on_exception(self) -> None:
        """Test environment is restored even if exception raised in context."""
        original_value = "original"
        os.environ["TEST_VAR"] = original_value

        try:
            env = ConfigurationEnv()

            with pytest.raises(ValueError):
                with env:
                    env.set("TEST_VAR", "modified")
                    raise ValueError("test error")

            assert os.environ["TEST_VAR"] == original_value
        finally:
            if "TEST_VAR" in os.environ:
                del os.environ["TEST_VAR"]

    def test_nested_context_managers(self) -> None:
        """Test nested context managers work correctly."""
        os.environ["TEST_VAR"] = "original"

        try:
            env1 = ConfigurationEnv()

            with env1:
                env1.set("TEST_VAR", "level1")
                assert os.environ["TEST_VAR"] == "level1"

                env2 = ConfigurationEnv()
                with env2:
                    env2.set("TEST_VAR", "level2")
                    assert os.environ["TEST_VAR"] == "level2"

                assert os.environ["TEST_VAR"] == "level1"

            assert os.environ["TEST_VAR"] == "original"
        finally:
            if "TEST_VAR" in os.environ:
                del os.environ["TEST_VAR"]

    def test_multiple_variables_in_context(self) -> None:
        """Test setting multiple variables in one context."""
        try:
            env = ConfigurationEnv()

            with env:
                env.set("VAR1", "value1")
                env.set("VAR2", "value2")
                env.set("VAR3", "value3")

                assert os.environ["VAR1"] == "value1"
                assert os.environ["VAR2"] == "value2"
                assert os.environ["VAR3"] == "value3"

            for var in ["VAR1", "VAR2", "VAR3"]:
                assert var not in os.environ
        finally:
            for var in ["VAR1", "VAR2", "VAR3"]:
                if var in os.environ:
                    del os.environ[var]


class TestConfigurationEnvManualEnterExit:
    """Test manual enter() and exit() methods."""

    def test_manual_enter_and_exit(self) -> None:
        """Test manually calling enter() and exit() methods."""
        try:
            original_value = "original"
            os.environ["TEST_VAR"] = original_value

            env = ConfigurationEnv()
            env.enter()
            env.set("TEST_VAR", "modified")
            assert os.environ["TEST_VAR"] == "modified"

            env.exit()
            assert os.environ["TEST_VAR"] == original_value
        finally:
            if "TEST_VAR" in os.environ:
                del os.environ["TEST_VAR"]

    def test_enter_exit_multiple_variables(self) -> None:
        """Test manual enter/exit with multiple variables."""
        try:
            os.environ["VAR1"] = "orig1"
            os.environ["VAR2"] = "orig2"

            env = ConfigurationEnv()
            env.enter()
            env.set("VAR1", "modified1")
            env.set("VAR2", "modified2")
            env.set("VAR3", "new3")

            assert os.environ["VAR1"] == "modified1"
            assert os.environ["VAR2"] == "modified2"
            assert os.environ["VAR3"] == "new3"

            env.exit()

            assert os.environ["VAR1"] == "orig1"
            assert os.environ["VAR2"] == "orig2"
            assert "VAR3" not in os.environ
        finally:
            for var in ["VAR1", "VAR2", "VAR3"]:
                if var in os.environ:
                    del os.environ[var]

    def test_nested_manual_enter_exit(self) -> None:
        """Test nested manual enter/exit calls."""
        try:
            os.environ["TEST_VAR"] = "original"

            env1 = ConfigurationEnv()
            env1.enter()
            env1.set("TEST_VAR", "level1")
            assert os.environ["TEST_VAR"] == "level1"

            env2 = ConfigurationEnv()
            env2.enter()
            env2.set("TEST_VAR", "level2")
            assert os.environ["TEST_VAR"] == "level2"

            env2.exit()
            assert os.environ["TEST_VAR"] == "level1"

            env1.exit()
            assert os.environ["TEST_VAR"] == "original"
        finally:
            if "TEST_VAR" in os.environ:
                del os.environ["TEST_VAR"]

    def test_exit_without_enter_is_safe(self) -> None:
        """Test calling exit() without prior enter() is safe."""
        env = ConfigurationEnv()
        env.exit()


class TestConfigurationEnvIsolation:
    """Test environment variable isolation across setup and cleanup."""

    def test_env_isolation_setup_cleanup_pattern(self) -> None:
        """Test environment variable isolation using setup/cleanup pattern."""
        try:
            original_value = "original"
            os.environ["MOONDOCK_DIR"] = original_value

            env = ConfigurationEnv()
            env.enter()
            env.set("MOONDOCK_DIR", "/tmp/test_scenario")
            env.set("AWS_ACCESS_KEY_ID", "testing")
            env.set("AWS_SECRET_ACCESS_KEY", "testing")

            assert os.environ["MOONDOCK_DIR"] == "/tmp/test_scenario"
            assert os.environ["AWS_ACCESS_KEY_ID"] == "testing"
            assert os.environ["AWS_SECRET_ACCESS_KEY"] == "testing"

            env.exit()

            assert os.environ["MOONDOCK_DIR"] == original_value
            assert "AWS_ACCESS_KEY_ID" not in os.environ
            assert "AWS_SECRET_ACCESS_KEY" not in os.environ
        finally:
            if "MOONDOCK_DIR" in os.environ:
                del os.environ["MOONDOCK_DIR"]
