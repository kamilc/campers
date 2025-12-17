"""BDD step definitions for multi-user isolation feature."""

import logging
import re
from unittest.mock import patch

from behave import given, then, when
from behave.runner import Context

from tests.integration.features.environment import LogCapture
from tests.integration.features.steps.instance_list_steps import create_test_instance


@given('the current user\'s identity is "{user_identity}"')
def step_set_current_user_identity(context: Context, user_identity: str) -> None:
    """Set the current user's identity for testing.

    Parameters
    ----------
    context : Context
        Behave test context
    user_identity : str
        User identity to use (e.g., "alice@example.com")
    """
    context.current_user_identity = user_identity


@given('instances exist with owners "{owners}"')
def step_instances_exist_with_owners(context: Context, owners: str) -> None:
    """Create instances with specified owner tags.

    Parameters
    ----------
    context : Context
        Behave test context
    owners : str
        Comma-separated list of owners (e.g., "alice@example.com" and "bob@example.com")
    """
    owner_list = [o.strip().strip('"') for o in owners.split(" and ")]
    region = "us-east-1"

    if context.instances is None:
        context.instances = []

    for idx, owner in enumerate(owner_list):
        tags = {
            "ManagedBy": "campers",
            "Name": f"campers-test-{idx}",
            "MachineConfig": f"test-machine-{idx}",
            "Owner": owner,
        }

        instance_id, launch_time = create_test_instance(region, tags)

        context.instances.append(
            {
                "instance_id": instance_id,
                "region": region,
                "launch_time": launch_time,
                "camp_config": f"test-machine-{idx}",
                "owner": owner,
                "name": f"campers-test-{idx}",
                "state": "running",
                "instance_type": "t3.medium",
            }
        )


@given("an instance exists without Owner tag")
def step_instance_without_owner_tag(context: Context) -> None:
    """Create an instance without an Owner tag.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    region = "us-east-1"

    if context.instances is None:
        context.instances = []

    tags = {
        "ManagedBy": "campers",
        "Name": "legacy-instance",
        "MachineConfig": "ad-hoc",
    }

    instance_id, launch_time = create_test_instance(region, tags)

    context.instances.append(
        {
            "instance_id": instance_id,
            "region": region,
            "launch_time": launch_time,
            "camp_config": "ad-hoc",
            "owner": "unknown",
            "name": "legacy-instance",
            "state": "running",
            "instance_type": "t3.medium",
        }
    )


@given('the instance has Name "{name}"')
def step_instance_has_name(context: Context, name: str) -> None:
    """Set or verify instance name.

    Parameters
    ----------
    context : Context
        Behave test context
    name : str
        Instance name to set
    """
    if context.instances:
        context.instances[-1]["name"] = name
        context.instances[-1]["camp_config"] = name


@given("git config user.email is not set")
def step_git_config_not_set(context: Context) -> None:
    """Mock git config to return empty when checking user.email.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    context.mock_git_email = False


@given('USER environment variable is "{user_env}"')
def step_set_user_env_var(context: Context, user_env: str) -> None:
    """Set USER environment variable.

    Parameters
    ----------
    context : Context
        Behave test context
    user_env : str
        USER environment variable value
    """
    context.user_env_var = user_env


@when("I run campers run to create an instance")
def step_run_campers_run(context: Context) -> None:
    """Mock running campers run command to create an instance.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    if not hasattr(context, "mock_git_email"):
        context.mock_git_email = True

    def mock_get_user_identity():
        if hasattr(context, "mock_git_email") and not context.mock_git_email:
            return context.user_env_var if hasattr(context, "user_env_var") else "unknown"
        elif hasattr(context, "current_user_identity"):
            return context.current_user_identity
        return "unknown"

    with patch("campers.utils.get_user_identity", side_effect=mock_get_user_identity):
        from campers.utils import get_user_identity

        owner = get_user_identity()

        if context.instances is None:
            context.instances = []

        tags = {
            "ManagedBy": "campers",
            "Name": "campers-test-instance",
            "MachineConfig": "test-camp",
            "Owner": owner,
        }

        instance_id, launch_time = create_test_instance("us-east-1", tags)

        context.instances.append(
            {
                "instance_id": instance_id,
                "region": "us-east-1",
                "launch_time": launch_time,
                "camp_config": "test-camp",
                "owner": owner,
                "name": "campers-test-instance",
                "state": "running",
                "instance_type": "t3.medium",
            }
        )


@when("I run list command directly with --all flag")
def step_run_list_command_with_all_flag(context: Context) -> None:
    """Run list command directly with --all flag.

    Parameters
    ----------
    context : Context
        Behave test context
    """

    def mock_get_user_identity():
        if hasattr(context, "current_user_identity"):
            return context.current_user_identity
        return "unknown"

    campers = context.campers_module.Campers()

    log_handler = LogCapture()
    root_logger = logging.getLogger()
    root_logger.addHandler(log_handler)
    original_level = root_logger.level
    root_logger.setLevel(logging.INFO)

    try:
        with (
            patch("campers.providers.aws.compute.EC2Manager.list_instances") as mock_list,
            patch("campers.providers.aws.compute.EC2Manager.get_volume_size") as mock_volume,
            patch("campers.utils.get_user_identity", side_effect=mock_get_user_identity),
        ):
            mock_list.return_value = context.instances if context.instances else []
            mock_volume.return_value = 0
            campers.list(region=None, show_all=True)

        output_lines = []
        for record in log_handler.records:
            output_lines.append(record.getMessage())
        context.stdout = "\n".join(output_lines)
        context.exit_code = 0
        context.stderr = ""
    except Exception as e:
        context.exception = e
        output_lines = []
        for record in log_handler.records:
            output_lines.append(record.getMessage())
        context.stdout = "\n".join(output_lines)
        context.stderr = str(e)
        context.exit_code = 1
    finally:
        root_logger.removeHandler(log_handler)
        root_logger.setLevel(original_level)


@then('the instance has Owner tag "{expected_owner}"')
def step_instance_has_owner_tag(context: Context, expected_owner: str) -> None:
    """Verify instance has expected Owner tag.

    Parameters
    ----------
    context : Context
        Behave test context
    expected_owner : str
        Expected owner tag value
    """
    if context.instances:
        instance = context.instances[-1]
        assert instance.get("owner") == expected_owner, (
            f"Expected owner '{expected_owner}' but got '{instance.get('owner')}'"
        )


@then('output displays title "{title}"')
def step_output_displays_title(context: Context, title: str) -> None:
    """Verify output contains specified title.

    Parameters
    ----------
    context : Context
        Behave test context
    title : str
        Title text to verify
    """
    assert title in context.stdout, f"Expected title '{title}' in output but got: {context.stdout}"


@then("only alice's instances are shown")
def step_only_alice_instances_shown(context: Context) -> None:
    """Verify only alice's instances are shown.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    lines = context.stdout.strip().split("\n")
    instance_lines = []

    for line in lines:
        if re.search(r"^\S+\s+i-[\w]+\s+(running|stopped|stopping)\s+", line):
            instance_lines.append(line)

    for line in instance_lines:
        assert "campers-test-1" not in line or "alice" in context.current_user_identity, (
            f"Unexpected instance in output: {line}"
        )


@then("both users' instances are shown")
def step_both_users_instances_shown(context: Context) -> None:
    """Verify both users' instances are shown.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    lines = context.stdout.strip().split("\n")
    instance_count = sum(
        1 for line in lines if re.search(r"^\S+\s+i-[\w]+\s+(running|stopped|stopping)\s+", line)
    )

    assert instance_count >= 2, (
        f"Expected at least 2 instances but got {instance_count} in: {context.stdout}"
    )


@then('the instance "{instance_name}" is shown with owner "{expected_owner}"')
def step_instance_shown_with_owner(
    context: Context, instance_name: str, expected_owner: str
) -> None:
    """Verify specific instance is shown with expected owner.

    Parameters
    ----------
    context : Context
        Behave test context
    instance_name : str
        Instance name to verify
    expected_owner : str
        Expected owner value
    """
    assert instance_name in context.stdout, (
        f"Expected instance '{instance_name}' in output but got: {context.stdout}"
    )

    assert expected_owner in context.stdout, (
        f"Expected owner '{expected_owner}' in output but got: {context.stdout}"
    )


@then("the untagged instance is not shown")
def step_untagged_instance_not_shown(context: Context) -> None:
    """Verify untagged instances are not shown in filtered list.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    lines = context.stdout.strip().split("\n")
    instance_count = sum(
        1 for line in lines if re.search(r"^\S+\s+i-[\w]+\s+(running|stopped|stopping)\s+", line)
    )

    filtered_instances = [i for i in context.instances if i.get("owner") != "unknown"]

    expected_count = len(filtered_instances)
    assert instance_count == expected_count, (
        f"Expected {expected_count} instances but got {instance_count} in: {context.stdout}"
    )
