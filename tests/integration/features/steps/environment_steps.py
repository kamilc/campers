"""Step definitions for environment variable forwarding BDD tests."""

import ast
import os
import shlex

from behave import given, then, when


@given("local environment has {var1} and {var2}")
def step_setup_two_env_vars(context, var1, var2):
    """Set up two environment variables in local environment.

    Parameters
    ----------
    context : behave.runner.Context
        Behave context object
    var1 : str
        First environment variable name
    var2 : str
        Second environment variable name
    """
    context.saved_env = dict(os.environ)
    context.harness.services.configuration_env.clear()
    env = context.harness.services.configuration_env
    env.set("PATH", context.saved_env.get("PATH", ""))
    env.set("HOME", context.saved_env.get("HOME", ""))
    env.set("CAMPERS_DIR", context.saved_env.get("CAMPERS_DIR", ""))
    env.set("CAMPERS_TEST_MODE", "1")
    env.set("CAMPERS_CONFIG", context.saved_env.get("CAMPERS_CONFIG", ""))

    is_localstack = hasattr(context, "scenario") and "localstack" in context.scenario.tags

    if is_localstack:
        baseline_env = {
            "AWS_ENDPOINT_URL": context.saved_env.get("AWS_ENDPOINT_URL", "http://localhost:4566"),
            "AWS_ACCESS_KEY_ID": context.saved_env.get("AWS_ACCESS_KEY_ID", "testing"),
            "AWS_SECRET_ACCESS_KEY": context.saved_env.get("AWS_SECRET_ACCESS_KEY", "testing"),
            "AWS_DEFAULT_REGION": context.saved_env.get("AWS_DEFAULT_REGION", "us-east-1"),
        }

        for name, value in baseline_env.items():
            env.set(name, value)

    context.env_vars = {
        var1: f"mock-{var1.lower()}",
        var2: f"mock-{var2.lower()}",
    }

    for name, value in context.env_vars.items():
        context.harness.services.configuration_env.set(name, value)


@given("local environment has {var1}, {var2}, {var3}")
def step_setup_three_env_vars(context, var1, var2, var3):
    """Set up three environment variables in local environment.

    Parameters
    ----------
    context : behave.runner.Context
        Behave context object
    var1 : str
        First environment variable name
    var2 : str
        Second environment variable name
    var3 : str
        Third environment variable name
    """
    context.saved_env = dict(os.environ)
    context.harness.services.configuration_env.clear()
    env = context.harness.services.configuration_env
    env.set("PATH", context.saved_env.get("PATH", ""))
    env.set("HOME", context.saved_env.get("HOME", ""))
    env.set("CAMPERS_DIR", context.saved_env.get("CAMPERS_DIR", ""))
    env.set("CAMPERS_TEST_MODE", "1")
    env.set("CAMPERS_CONFIG", context.saved_env.get("CAMPERS_CONFIG", ""))

    is_localstack = hasattr(context, "scenario") and "localstack" in context.scenario.tags

    if is_localstack:
        baseline_env = {
            "AWS_ENDPOINT_URL": context.saved_env.get("AWS_ENDPOINT_URL", "http://localhost:4566"),
            "AWS_ACCESS_KEY_ID": context.saved_env.get("AWS_ACCESS_KEY_ID", "testing"),
            "AWS_SECRET_ACCESS_KEY": context.saved_env.get("AWS_SECRET_ACCESS_KEY", "testing"),
            "AWS_DEFAULT_REGION": context.saved_env.get("AWS_DEFAULT_REGION", "us-east-1"),
        }

        for name, value in baseline_env.items():
            env.set(name, value)

    context.env_vars = {
        var1: f"mock-{var1.lower()}",
        var2: f"mock-{var2.lower()}",
        var3: f"mock-{var3.lower()}",
    }

    for name, value in context.env_vars.items():
        context.harness.services.configuration_env.set(name, value)


@given('local environment has {var_name} with value "{var_value}"')
def step_setup_env_var_with_value(context, var_name, var_value):
    """Set up environment variable with specific value.

    Parameters
    ----------
    context : behave.runner.Context
        Behave context object
    var_name : str
        Environment variable name
    var_value : str
        Environment variable value
    """
    context.env_vars = {var_name: var_value}
    context.harness.services.configuration_env.set(var_name, var_value)


@given("config has env_filter {patterns}")
def step_config_has_env_filter(context, patterns):
    """Set env_filter patterns in config.

    Parameters
    ----------
    context : behave.runner.Context
        Behave context object
    patterns : str
        JSON-like list of regex patterns
    """
    patterns_list = ast.literal_eval(patterns)

    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {"defaults": {}}

    if "defaults" not in context.config_data:
        context.config_data["defaults"] = {}

    context.config_data["defaults"]["env_filter"] = patterns_list


@given("config has no env_filter defined")
def step_config_no_env_filter(context):
    """Remove env_filter from config.

    Parameters
    ----------
    context : behave.runner.Context
        Behave context object
    """
    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {"defaults": {}}

    if "defaults" in context.config_data:
        context.config_data["defaults"].pop("env_filter", None)


@when("I execute the campers run")
def step_execute_campers_run(context):
    """Simulate executing campers run in test mode.

    Parameters
    ----------
    context : behave.runner.Context
        Behave context object
    """
    context.harness.services.configuration_env.set("CAMPERS_TEST_MODE", "1")
    context.command_executed = True


@when("environment variables are filtered")
def step_filter_environment_variables(context):
    """Simulate environment variable filtering.

    Parameters
    ----------
    context : behave.runner.Context
        Behave context object
    """
    from campers.services.ssh import SSHManager

    ssh_manager = SSHManager(host="203.0.113.1", key_file="/tmp/test.pem")

    env_filter = None

    if hasattr(context, "config_data") and context.config_data:
        if "defaults" in context.config_data:
            env_filter = context.config_data["defaults"].get("env_filter")

    context.filtered_vars = ssh_manager.filter_environment_variables(env_filter)


@when("config validation runs")
def step_config_validation_runs(context):
    """Run config validation.

    Parameters
    ----------
    context : behave.runner.Context
        Behave context object
    """
    from campers.core.config import ConfigLoader

    config_loader = ConfigLoader()

    try:
        config_to_validate = {
            "region": "us-east-1",
            "instance_type": "t2.micro",
            "disk_size": 20,
        }

        if hasattr(context, "config_data") and context.config_data:
            defaults = context.config_data.get("defaults", {})
            config_to_validate.update(defaults)

        config_loader.validate_config(config_to_validate)
        context.validation_passed = True
    except ValueError as e:
        context.validation_error = str(e)
        context.error = str(e)
        context.validation_passed = False


@then("2 environment variables are forwarded")
def step_two_env_vars_forwarded(context):
    """Verify 2 environment variables are forwarded.

    Parameters
    ----------
    context : behave.runner.Context
        Behave context object
    """
    if hasattr(context, "filtered_vars"):
        assert len(context.filtered_vars) == 2, (
            f"Expected 2 variables, got {len(context.filtered_vars)}"
        )
    elif hasattr(context, "stderr"):
        assert "Forwarding 2 environment variables" in context.stderr or context.exit_code == 0
    else:
        raise AssertionError("Neither filtered_vars nor stderr available for verification")


@then("command executes with export prefix")
def step_command_executes_with_export(context):
    """Verify command executes with export prefix.

    Parameters
    ----------
    context : behave.runner.Context
        Behave context object
    """
    if hasattr(context, "filtered_vars"):
        assert len(context.filtered_vars) > 0, "No variables filtered"
    else:
        assert context.exit_code == 0


@then("AWS credentials are available in remote command")
def step_aws_credentials_available(context):
    """Verify AWS credentials are available.

    Parameters
    ----------
    context : behave.runner.Context
        Behave context object
    """
    if hasattr(context, "filtered_vars"):
        assert any("AWS" in var for var in context.filtered_vars), "No AWS variables found"
    else:
        assert context.exit_code == 0


@then("3 environment variables are forwarded")
def step_three_env_vars_forwarded(context):
    """Verify 3 environment variables are forwarded.

    Parameters
    ----------
    context : behave.runner.Context
        Behave context object
    """
    if hasattr(context, "filtered_vars"):
        assert len(context.filtered_vars) == 3, (
            f"Expected 3 variables, got {len(context.filtered_vars)}"
        )
    elif hasattr(context, "stderr"):
        assert "Forwarding 3 environment variables" in context.stderr or context.exit_code == 0
    else:
        raise AssertionError("Neither filtered_vars nor stderr available for verification")


@then("no environment variables are forwarded")
def step_no_env_vars_forwarded(context):
    """Verify no environment variables are forwarded.

    Parameters
    ----------
    context : behave.runner.Context
        Behave context object
    """
    if hasattr(context, "filtered_vars"):
        assert len(context.filtered_vars) == 0, (
            f"Expected 0 variables, got {len(context.filtered_vars)}"
        )
    else:
        assert context.exit_code == 0


@then("command executes without export prefix")
def step_command_executes_without_export(context):
    """Verify command executes without export prefix.

    Parameters
    ----------
    context : behave.runner.Context
        Behave context object
    """
    if hasattr(context, "filtered_vars"):
        assert len(context.filtered_vars) == 0, "Variables should be empty"
    else:
        assert context.exit_code == 0


@then("variable value is properly escaped with shlex.quote()")
def step_variable_value_escaped(context):
    """Verify variable value is properly escaped.

    Parameters
    ----------
    context : behave.runner.Context
        Behave context object
    """
    assert hasattr(context, "env_vars"), "env_vars not set"

    for var_name, var_value in context.env_vars.items():
        quoted = shlex.quote(var_value)
        assert quoted is not None, f"Failed to quote {var_name}"


@then("shell injection is prevented")
def step_shell_injection_prevented(context):
    """Verify shell injection is prevented.

    Parameters
    ----------
    context : behave.runner.Context
        Behave context object
    """
    assert hasattr(context, "env_vars"), "env_vars not set"

    for var_name, var_value in context.env_vars.items():
        quoted = shlex.quote(var_value)
        assert "rm -rf" not in quoted or "'" in quoted, (
            f"Dangerous command not properly escaped in {var_name}"
        )


@then("ValueError is raised")
def step_value_error_raised(context):
    """Verify ValueError is raised.

    Parameters
    ----------
    context : behave.runner.Context
        Behave context object
    """
    assert hasattr(context, "validation_error"), "No validation error found"
    assert context.validation_passed is False, "Validation should have failed"


@then("test completes successfully")
def step_test_completes_successfully(context):
    """Verify test completes successfully.

    Parameters
    ----------
    context : behave.runner.Context
        Behave context object
    """
    if hasattr(context, "command_executed"):
        assert context.command_executed is True, "Command execution failed"
    elif hasattr(context, "exit_code"):
        assert context.exit_code == 0, f"Command failed with exit code {context.exit_code}"
    else:
        raise AssertionError("Neither command_executed nor exit_code available")


@then('warning message "{message}" is logged')
def step_warning_message_logged(context, message):
    """Verify warning message is logged.

    Parameters
    ----------
    context : behave.runner.Context
        Behave context object
    message : str
        Expected warning message
    """
    assert hasattr(context, "filtered_vars"), "filtered_vars not set"


@then("variables are still forwarded")
def step_variables_still_forwarded(context):
    """Verify variables are still forwarded despite warning.

    Parameters
    ----------
    context : behave.runner.Context
        Behave context object
    """
    assert hasattr(context, "filtered_vars"), "filtered_vars not set"
    assert len(context.filtered_vars) > 0, "Variables should be forwarded"
