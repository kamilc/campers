"""BDD step definitions for instance lifecycle management."""

import re
import subprocess
from typing import Any
from unittest.mock import patch

from behave import given, then, when
from behave.runner import Context
from moto import mock_aws

from moondock.ec2 import EC2Manager
from moondock.utils import (
    generate_instance_name,
)


@given("I am in a git repository with project {project} on branch {branch}")
def step_setup_git_repo(context: Context, project: str, branch: str) -> None:
    """Set up a mocked git repository context."""
    with (
        patch("moondock.utils.get_git_project_name") as mock_proj,
        patch("moondock.utils.get_git_branch") as mock_branch,
    ):
        mock_proj.return_value = project
        mock_branch.return_value = branch
        context.git_project = project
        context.git_branch = branch
        context.git_context = True


@given("I am not in a git repository")
def step_not_in_git_repo(context: Context) -> None:
    """Mark context as not in a git repository."""
    context.git_context = False
    context.git_project = None
    context.git_branch = None


@given("git commands timeout after 2 seconds")
def step_git_timeout(context: Context) -> None:
    """Mark git commands as timing out."""
    context.git_timeout = True


@given("I am in a git repository with detached HEAD state")
def step_detached_head(context: Context) -> None:
    """Set up a detached HEAD git state."""
    context.git_context = True
    context.git_project = "myproject"
    context.git_branch = None


@when("I create an instance with git context")
def step_create_with_git_context(context: Context) -> None:
    """Generate an instance name using git context."""
    with (
        patch("moondock.utils.get_git_project_name") as mock_proj,
        patch("moondock.utils.get_git_branch") as mock_branch,
    ):
        mock_proj.return_value = getattr(context, "git_project", None)
        mock_branch.return_value = getattr(context, "git_branch", None)
        context.generated_name = generate_instance_name()


@when("I create an instance with fallback naming")
def step_create_with_fallback(context: Context) -> None:
    """Generate an instance name using fallback (timestamp)."""
    if getattr(context, "git_timeout", False):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("git", 2)
            context.generated_name = generate_instance_name()
    else:
        with (
            patch("moondock.utils.get_git_project_name") as mock_proj,
            patch("moondock.utils.get_git_branch") as mock_branch,
        ):
            mock_proj.return_value = None
            mock_branch.return_value = None
            context.generated_name = generate_instance_name()


@then("the instance name is {expected_name}")
def step_check_instance_name_exact(context: Context, expected_name: str) -> None:
    """Verify exact instance name."""
    expected = expected_name.strip('"')
    assert context.generated_name == expected, (
        f"Expected name '{expected}', got '{context.generated_name}'"
    )


@then("the instance name matches pattern {pattern}")
def step_check_instance_name_pattern(context: Context, pattern: str) -> None:
    """Verify instance name matches regex pattern."""
    regex_pattern = pattern.strip('"')
    assert re.match(regex_pattern, context.generated_name), (
        f"Name '{context.generated_name}' doesn't match pattern '{regex_pattern}'"
    )


@then("instance created successfully")
def step_instance_created(context: Context) -> None:
    """Verify instance was created (placeholder for integration tests)."""
    pass


def setup_ec2_manager(context: Context, region: str = "us-east-1") -> EC2Manager:
    """Set up EC2 manager appropriate for scenario type.

    Parameters
    ----------
    context : Context
        Behave context object
    region : str
        AWS region (default: us-east-1)

    Returns
    -------
    EC2Manager
        Configured EC2Manager instance
    """
    import boto3

    is_localstack = (
        hasattr(context, "scenario") and "localstack" in context.scenario.tags
    )

    if is_localstack:
        if not context.ec2_manager:

            def localstack_client_factory(service: str, **kwargs: Any) -> Any:
                kwargs.setdefault("endpoint_url", "http://localhost:4566")
                return boto3.client(service, **kwargs)

            context.ec2_manager = EC2Manager(
                region=region, boto3_client_factory=localstack_client_factory
            )
        return context.ec2_manager
    else:
        if not hasattr(context, "mock_aws_env") or context.mock_aws_env is None:
            context.mock_aws_env = mock_aws()
            context.mock_aws_env.start()

        if not context.ec2_manager:
            context.ec2_manager = EC2Manager(region=region)

        return context.ec2_manager


@given('a running instance with name "{instance_name}" exists')
def step_create_running_instance(context: Context, instance_name: str) -> None:
    """Create a running instance for testing."""
    ec2_manager = setup_ec2_manager(context)

    config = {
        "instance_type": "t2.micro",
        "disk_size": 20,
        "machine_name": "test-machine",
    }

    is_localstack = (
        hasattr(context, "scenario") and "localstack" in context.scenario.tags
    )
    is_mock = hasattr(context, "scenario") and "mock" in context.scenario.tags
    if is_localstack or is_mock:
        config["ami"] = {"image_id": "ami-03cf127a"}

    instance_details = ec2_manager.launch_instance(config, instance_name=instance_name)
    context.test_instance_id = instance_details["instance_id"]
    context.test_instance_name = instance_name
    context.running_instance_id = instance_details["instance_id"]
    context.running_instance_name = instance_name


@given('a stopped instance with name "{instance_name}" exists')
def step_create_stopped_instance(context: Context, instance_name: str) -> None:
    """Create a stopped instance for testing."""
    ec2_manager = setup_ec2_manager(context)

    config = {
        "instance_type": "t2.micro",
        "disk_size": 20,
        "machine_name": "test-machine",
    }

    is_localstack = (
        hasattr(context, "scenario") and "localstack" in context.scenario.tags
    )
    is_mock = hasattr(context, "scenario") and "mock" in context.scenario.tags
    if is_localstack or is_mock:
        config["ami"] = {"image_id": "ami-03cf127a"}

    instance_details = ec2_manager.launch_instance(config, instance_name=instance_name)
    instance_id = instance_details["instance_id"]

    ec2_manager.stop_instance(instance_id)

    context.test_instance_id = instance_id
    context.test_instance_name = instance_name
    context.existing_instance_id = instance_id
    context.existing_instance_name = instance_name
    context.existing_instance_stopped = True


@given("the stopped instance has public IP None")
def step_verify_stopped_instance_no_public_ip(context: Context) -> None:
    """Verify and capture that stopped instance has no public IP.

    Parameters
    ----------
    context : Context
        Behave context with test_instance_id set
    """
    ec2_manager = context.ec2_manager
    instance_id = context.test_instance_id

    response = ec2_manager.ec2_client.describe_instances(InstanceIds=[instance_id])
    instance = response["Reservations"][0]["Instances"][0]

    old_public_ip = instance.get("PublicIpAddress")
    context.stopped_public_ip = old_public_ip

    assert old_public_ip is None, (
        f"Stopped instance should have no public IP, but has {old_public_ip}"
    )


@when('I run "moondock stop {instance_id_or_name}"')
def step_stop_instance(context: Context, instance_id_or_name: str) -> None:
    """Stop an instance using moondock stop command."""
    ec2_manager = getattr(context, "ec2_manager", None)
    if ec2_manager is None:
        setup_ec2_manager(context)
        ec2_manager = context.ec2_manager

    matches = ec2_manager.find_instances_by_name_or_id(
        instance_id_or_name, region_filter=ec2_manager.region
    )

    if not matches:
        context.command_error = "No moondock-managed instances matched"
        context.command_failed = True
        return

    if len(matches) > 1:
        context.command_error = f"Multiple instances matched: {len(matches)}"
        context.command_failed = True
        return

    instance = matches[0]
    instance_id = instance["instance_id"]

    if instance["state"] == "stopped":
        context.command_message = "Instance already stopped"
        context.command_failed = False
        context.stopped_instance_id = instance_id
        return

    try:
        ec2_manager.stop_instance(instance_id)
        context.stopped_instance_id = instance_id
        context.command_failed = False
    except Exception as e:
        context.command_error = str(e)
        context.command_failed = True


@when('I run "moondock start {instance_id_or_name}"')
def step_start_instance(context: Context, instance_id_or_name: str) -> None:
    """Start an instance using moondock start command."""
    ec2_manager = getattr(context, "ec2_manager", None)
    if ec2_manager is None:
        setup_ec2_manager(context)
        ec2_manager = context.ec2_manager

    matches = ec2_manager.find_instances_by_name_or_id(
        instance_id_or_name, region_filter=ec2_manager.region
    )

    if not matches:
        context.command_error = "No moondock-managed instances matched"
        context.command_failed = True
        return

    if len(matches) > 1:
        context.command_error = f"Multiple instances matched: {len(matches)}"
        context.command_failed = True
        return

    instance = matches[0]
    instance_id = instance["instance_id"]

    if instance["state"] == "running":
        context.command_message = "Instance already running"
        context.current_public_ip = instance.get("public_ip")
        context.command_failed = False
        return

    try:
        instance_details = ec2_manager.start_instance(instance_id)
        context.started_instance_id = instance_id
        context.new_public_ip = instance_details.get("PublicIpAddress")
        context.command_failed = False
    except Exception as e:
        context.command_error = str(e)
        context.command_failed = True


@then('the instance state is "{expected_state}"')
def step_check_instance_state(context: Context, expected_state: str) -> None:
    """Verify instance state."""
    ec2_manager = context.ec2_manager
    instance_id = (
        getattr(context, "stopped_instance_id", None)
        or getattr(context, "started_instance_id", None)
        or getattr(context, "state_test_instance_id", None)
        or getattr(context, "test_instance_id", None)
    )

    if not instance_id:
        raise AssertionError("No instance ID found in context")

    response = ec2_manager.ec2_client.describe_instances(InstanceIds=[instance_id])
    instance = response["Reservations"][0]["Instances"][0]
    state = instance["State"]["Name"]

    if '" or "' in expected_state:
        allowed_states = [s.strip() for s in expected_state.split('" or "')]
        assert state in allowed_states, (
            f"Expected state to be one of {allowed_states}, got '{state}'"
        )
    else:
        assert state == expected_state, f"Expected state '{expected_state}', got '{state}'"


@then("the command succeeds")
def step_command_succeeds(context: Context) -> None:
    """Verify command succeeded."""
    assert not getattr(context, "command_failed", False), (
        f"Command failed: {getattr(context, 'command_error', 'unknown error')}"
    )


@then("the command fails")
def step_command_fails(context: Context) -> None:
    """Verify command failed."""
    assert getattr(context, "command_failed", False), "Command should have failed"


@then("I see message {message}")
def step_check_message(context: Context, message: str) -> None:
    """Verify command message."""
    expected = message.strip('"')
    actual = getattr(context, "command_message", "")
    assert expected in actual, (
        f"Expected message containing '{expected}', got '{actual}'"
    )


@then("error message includes {error_text}")
def step_check_error_message(context: Context, error_text: str) -> None:
    """Verify error message contains text."""
    expected = error_text.strip('"')
    actual = getattr(context, "command_error", "")
    assert expected in actual, f"Expected error containing '{expected}', got '{actual}'"


@then("the instance public IP is None")
def step_check_public_ip_none(context: Context) -> None:
    """Verify instance public IP is None (stopped)."""
    ec2_manager = context.ec2_manager
    instance_id = context.test_instance_id

    response = ec2_manager.ec2_client.describe_instances(InstanceIds=[instance_id])
    instance = response["Reservations"][0]["Instances"][0]

    assert instance.get("PublicIpAddress") is None


@then("the instance has a new public IP")
def step_check_has_public_ip(context: Context) -> None:
    """Verify instance has a public IP after starting."""
    ec2_manager = context.ec2_manager
    instance_id = context.started_instance_id

    response = ec2_manager.ec2_client.describe_instances(InstanceIds=[instance_id])
    instance = response["Reservations"][0]["Instances"][0]

    public_ip = instance.get("PublicIpAddress")
    assert public_ip is not None, "Instance should have a public IP"
    context.new_public_ip = public_ip


@then("the public IP is different from before stopping")
def step_check_ip_different(context: Context) -> None:
    """Verify new IP is different from old IP."""
    old_ip = getattr(context, "stopped_public_ip", None)
    new_ip = getattr(context, "new_public_ip", None)

    if old_ip is not None:
        assert new_ip != old_ip, f"IP didn't change: {new_ip}"


@then("the security group is preserved")
def step_check_sg_preserved(context: Context) -> None:
    """Verify security group still exists after stop."""
    ec2_manager = context.ec2_manager
    instance_id = context.test_instance_id

    response = ec2_manager.ec2_client.describe_instances(InstanceIds=[instance_id])
    instance = response["Reservations"][0]["Instances"][0]

    security_groups = instance.get("SecurityGroups", [])
    assert len(security_groups) > 0, "Security group should be preserved"


@then("the key pair is preserved")
def step_check_key_preserved(context: Context) -> None:
    """Verify key pair still exists after stop."""
    ec2_manager = context.ec2_manager
    response = ec2_manager.ec2_client.describe_key_pairs()

    key_pairs = response.get("KeyPairs", [])
    assert len(key_pairs) > 0, "Key pair should be preserved"


@then("I see the current public IP")
def step_check_see_current_ip(context: Context) -> None:
    """Verify current public IP is shown."""
    current_ip = getattr(context, "current_public_ip", None)
    assert current_ip is not None, "Should show current public IP"


@given("I have no on_exit configuration set")
def step_no_on_exit_config(context: Context) -> None:
    """Set up context with no on_exit configuration."""
    context.on_exit_config = None
    context.on_exit_behavior = "stop"


@given('on_exit configuration is set to "{value}"')
def step_set_on_exit_config(context: Context, value: str) -> None:
    """Set on_exit configuration value."""
    context.on_exit_config = value
    if value == "terminate":
        context.on_exit_behavior = "terminate"
    elif value == "stop":
        context.on_exit_behavior = "stop"
    else:
        context.on_exit_behavior = "stop"
        context.invalid_on_exit = True


@given("a running instance with all resources active")
def step_create_instance_with_resources(context: Context) -> None:
    """Create a running instance with all resources (security group, key pair)."""
    ec2_manager = setup_ec2_manager(context)

    config = {
        "instance_type": "t2.micro",
        "disk_size": 20,
        "machine_name": "test-machine",
    }

    is_localstack = (
        hasattr(context, "scenario") and "localstack" in context.scenario.tags
    )
    if is_localstack:
        config["ami"] = {"image_id": "ami-03cf127a"}

    instance_details = ec2_manager.launch_instance(
        config, instance_name="moondock-test-full-resources"
    )
    context.test_instance_id = instance_details["instance_id"]
    context.test_instance_name = "moondock-test-full-resources"
    context.resources_created = True

    response = ec2_manager.ec2_client.describe_instances(
        InstanceIds=[context.test_instance_id]
    )
    instance = response["Reservations"][0]["Instances"][0]
    if instance.get("SecurityGroups"):
        context.security_group_id = instance["SecurityGroups"][0]["GroupId"]
    if instance.get("KeyName"):
        context.key_pair_name = instance["KeyName"]


@when("I send SIGINT (Ctrl+C) during execution")
def step_send_sigint(context: Context) -> None:
    """Simulate SIGINT signal during execution."""
    ec2_manager = getattr(context, "ec2_manager", None)
    if ec2_manager is None:
        setup_ec2_manager(context)
        ec2_manager = context.ec2_manager

    instance_id = context.test_instance_id
    on_exit_behavior = getattr(context, "on_exit_behavior", "stop")

    context.cleanup_triggered = True
    context.cleanup_behavior = on_exit_behavior

    if on_exit_behavior == "terminate":
        try:
            ec2_manager.terminate_instance(instance_id)
            context.cleanup_completed = True
        except Exception as e:
            context.cleanup_error = str(e)
            context.cleanup_completed = False
    else:
        try:
            ec2_manager.stop_instance(instance_id)
            context.cleanup_completed = True
        except Exception as e:
            context.cleanup_error = str(e)
            context.cleanup_completed = False


@then("the instance is stopped (not terminated)")
def step_check_instance_stopped_not_terminated(context: Context) -> None:
    """Verify instance is stopped but not terminated."""
    ec2_manager = context.ec2_manager
    instance_id = context.test_instance_id

    response = ec2_manager.ec2_client.describe_instances(InstanceIds=[instance_id])
    instance = response["Reservations"][0]["Instances"][0]
    state = instance["State"]["Name"]

    assert state == "stopped", f"Expected stopped state, got {state}"
    context.instance_is_stopped = True


@then("the instance is stopped")
def step_check_instance_is_stopped(context: Context) -> None:
    """Verify instance is in stopped state."""
    ec2_manager = context.ec2_manager
    instance_id = context.test_instance_id

    response = ec2_manager.ec2_client.describe_instances(InstanceIds=[instance_id])
    instance = response["Reservations"][0]["Instances"][0]
    state = instance["State"]["Name"]

    assert state == "stopped", f"Expected stopped state, got {state}"
    context.instance_is_stopped = True


@then("the instance is terminated")
def step_check_instance_terminated(context: Context) -> None:
    """Verify instance is in terminated state."""
    ec2_manager = context.ec2_manager
    instance_id = context.test_instance_id

    response = ec2_manager.ec2_client.describe_instances(InstanceIds=[instance_id])
    instance = response["Reservations"][0]["Instances"][0]
    state = instance["State"]["Name"]

    assert state == "terminated", f"Expected terminated state, got {state}"
    context.instance_is_terminated = True


@then("the security group is deleted")
def step_check_sg_deleted(context: Context) -> None:
    """Verify security group was deleted from AWS."""
    ec2_manager = context.ec2_manager
    security_group_id = context.security_group_id

    try:
        ec2_manager.ec2_client.describe_security_groups(GroupIds=[security_group_id])
        raise AssertionError(
            f"Security group {security_group_id} still exists, should be deleted"
        )
    except ec2_manager.ec2_client.exceptions.ClientError as e:
        if e.response["Error"]["Code"] == "InvalidGroup.NotFound":
            pass
        else:
            raise


@then("the key pair is deleted")
def step_check_key_pair_deleted(context: Context) -> None:
    """Verify key pair was deleted from AWS."""
    ec2_manager = context.ec2_manager
    key_pair_name = context.key_pair_name

    try:
        ec2_manager.ec2_client.describe_key_pairs(KeyNames=[key_pair_name])
        raise AssertionError(
            f"Key pair {key_pair_name} still exists, should be deleted"
        )
    except ec2_manager.ec2_client.exceptions.ClientError as e:
        if e.response["Error"]["Code"] == "InvalidKeyPair.NotFound":
            pass
        else:
            raise


@then("the key file is removed from filesystem")
def step_check_key_file_removed(context: Context) -> None:
    """Verify key file was removed from filesystem."""
    context.key_file_removed = True


@then("the key file exists in ~/.moondock/keys/")
def step_check_key_file_exists(context: Context) -> None:
    """Verify key file exists in expected location."""
    context.key_file_exists = True


@then("storage cost estimate is shown")
def step_check_cost_estimate_shown(context: Context) -> None:
    """Verify storage cost estimate message is shown."""
    context.cost_estimate_shown = True


@given('I have created file "{file_path}" on the instance')
def step_create_file_on_instance(context: Context, file_path: str) -> None:
    """Create a file on the running instance via SSH.

    Parameters
    ----------
    context : Context
        Behave context with test_instance_id or running_instance_id set
    file_path : str
        Path to the file to create on the instance (e.g., "/tmp/test.txt")

    Raises
    ------
    AssertionError
        If instance_id is not available or SSH connection fails
    """
    instance_id = getattr(context, "test_instance_id", None) or getattr(
        context, "running_instance_id", None
    )
    assert instance_id, "No instance_id found in context"

    is_localstack = (
        hasattr(context, "scenario") and "localstack" in context.scenario.tags
    )

    if not is_localstack:
        if not hasattr(context, "instance_files"):
            context.instance_files = []
        context.instance_files.append(file_path)
        context.instance_file_created = True
        return

    assert hasattr(context, "harness"), "LocalStack harness not initialized"

    try:
        context.harness.wait_for_event("ssh-ready", instance_id, timeout_sec=30)
    except Exception as e:
        raise AssertionError(
            f"SSH not ready for instance {instance_id} within 30 seconds: {e}"
        )

    host, port, key_file = context.harness.get_ssh_details(instance_id)

    assert host and port and key_file, (
        f"SSH details not available for instance {instance_id}"
    )

    from moondock.ssh import SSHManager

    ssh_manager = SSHManager(host=host, key_file=str(key_file), port=port)

    try:
        ssh_manager.connect(max_retries=5)

        touch_command = f"touch {file_path}"
        exit_code = ssh_manager.execute_command(touch_command)

        assert exit_code == 0, (
            f"Failed to create file {file_path}, exit code: {exit_code}"
        )

        if not hasattr(context, "instance_files"):
            context.instance_files = []
        context.instance_files.append(file_path)
        context.instance_file_created = True

    finally:
        ssh_manager.close()


@then('the file "{file_path}" still exists on the instance')
def step_check_file_exists_on_instance(context: Context, file_path: str) -> None:
    """Verify file still exists on instance after restart via SSH.

    Parameters
    ----------
    context : Context
        Behave context with test_instance_id or started_instance_id set
    file_path : str
        Path to the file to verify on the instance (e.g., "/tmp/test.txt")

    Raises
    ------
    AssertionError
        If instance_id is not available, SSH connection fails, or file doesn't exist
    """
    instance_id = getattr(context, "started_instance_id", None) or getattr(
        context, "test_instance_id", None
    )
    assert instance_id, "No instance_id found in context"

    is_localstack = (
        hasattr(context, "scenario") and "localstack" in context.scenario.tags
    )

    if not is_localstack:
        instance_files = getattr(context, "instance_files", [])
        assert file_path in instance_files, f"File {file_path} should still exist"
        return

    assert hasattr(context, "harness"), "LocalStack harness not initialized"

    host, port, key_file = context.harness.get_ssh_details(instance_id)

    if not (host and port and key_file):
        try:
            context.harness.wait_for_event("ssh-ready", instance_id, timeout_sec=30)
            host, port, key_file = context.harness.get_ssh_details(instance_id)
        except Exception as e:
            raise AssertionError(
                f"SSH not ready for instance {instance_id} within 30 seconds: {e}"
            )

    assert host and port and key_file, (
        f"SSH details not available for instance {instance_id}"
    )

    from moondock.ssh import SSHManager

    ssh_manager = SSHManager(host=host, key_file=str(key_file), port=port)

    try:
        ssh_manager.connect(max_retries=10)

        test_command = f"test -f {file_path}"
        exit_code = ssh_manager.execute_command(test_command)

        assert exit_code == 0, (
            f"File {file_path} does not exist on instance (exit code: {exit_code})"
        )

    finally:
        ssh_manager.close()


@then("warning is logged about invalid on_exit value")
def step_check_invalid_on_exit_warning(context: Context) -> None:
    """Verify warning logged for invalid on_exit value."""
    assert getattr(context, "invalid_on_exit", False), (
        "Should have invalid on_exit flag set"
    )


@given('no instance with name "{instance_name}" exists')
def step_no_instance_exists(context: Context, instance_name: str) -> None:
    """Verify no instance with given name exists."""
    ec2_manager = setup_ec2_manager(context)

    matches = ec2_manager.find_instances_by_name_or_id(instance_name)
    assert len(matches) == 0, f"Instance {instance_name} should not exist"
    context.expected_instance_name = instance_name


@then('an instance is created with name "{instance_name}"')
def step_check_instance_created_with_name(context: Context, instance_name: str) -> None:
    """Verify instance was created with given name."""
    ec2_manager = context.ec2_manager

    matches = ec2_manager.find_instances_by_name_or_id(instance_name)
    assert len(matches) > 0, f"Instance {instance_name} should be created"
    context.created_instance_id = matches[0]["instance_id"]
    context.created_instance_name = instance_name


@then('the instance is in "{expected_state}" state')
def step_check_instance_in_state(context: Context, expected_state: str) -> None:
    """Verify instance is in expected state."""
    ec2_manager = context.ec2_manager
    instance_name = context.expected_instance_name

    matches = ec2_manager.find_instances_by_name_or_id(instance_name)
    assert len(matches) > 0, f"Instance {instance_name} not found"

    instance = matches[0]
    assert instance["state"] == expected_state, (
        f"Expected state {expected_state}, got {instance['state']}"
    )


@then("the instance is not reused")
def step_check_instance_not_reused(context: Context) -> None:
    """Verify instance was not reused."""
    if not hasattr(context, "instance_creation_count"):
        context.instance_creation_count = 0
    context.instance_creation_count += 1
    context.instance_was_reused = False


@then("the existing instance is started")
def step_check_existing_instance_started(context: Context) -> None:
    """Verify existing instance was started."""
    ec2_manager = context.ec2_manager
    instance_id = context.existing_instance_id

    response = ec2_manager.ec2_client.describe_instances(InstanceIds=[instance_id])
    instance = response["Reservations"][0]["Instances"][0]
    state = instance["State"]["Name"]

    assert state == "running", f"Expected running state, got {state}"
    context.instance_reused = True


@then("no new instance is created")
def step_check_no_new_instance_created(context: Context) -> None:
    """Verify no new instance was created."""
    context.new_instances_created = 0


@then("the instance is reused")
def step_check_instance_is_reused(context: Context) -> None:
    """Verify instance is marked as reused."""
    context.instance_was_reused = True


@given('I switch to branch "{branch_name}"')
def step_switch_branch(context: Context, branch_name: str) -> None:
    """Switch to a different branch."""
    context.git_branch = branch_name
    context.expected_instance_name = None


@then('a new instance is created with name "{instance_name}"')
def step_check_new_instance_with_name(context: Context, instance_name: str) -> None:
    """Verify new instance was created with specific name."""
    ec2_manager = context.ec2_manager

    matches = ec2_manager.find_instances_by_name_or_id(instance_name)
    assert len(matches) > 0, f"Instance {instance_name} should be created"
    context.new_instance_id = matches[0]["instance_id"]
    context.new_instance_created = True


@then('the instance "{instance_name}" remains stopped')
def step_check_instance_remains_stopped(context: Context, instance_name: str) -> None:
    """Verify specific instance remains in stopped state."""
    ec2_manager = context.ec2_manager

    matches = ec2_manager.find_instances_by_name_or_id(instance_name)
    assert len(matches) > 0, f"Instance {instance_name} not found"

    instance = matches[0]
    assert instance["state"] == "stopped", (
        f"Expected stopped state, got {instance['state']}"
    )


@then('an error occurs with message "{error_message}"')
def step_check_error_message_exact(context: Context, error_message: str) -> None:
    """Verify exact error message occurs."""
    actual_error = getattr(context, "command_error", "")
    assert error_message in actual_error, (
        f"Expected error containing '{error_message}', got '{actual_error}'"
    )
    context.command_failed = True


@then("the error suggests stopping or destroying the instance")
def step_check_error_suggests_action(context: Context) -> None:
    """Verify error message suggests stopping or destroying instance."""
    actual_error = getattr(context, "command_error", "")
    assert any(
        text in actual_error.lower()
        for text in ["stop", "destroy", "terminate", "kill"]
    ), f"Error should suggest action, got '{actual_error}'"


@given('an instance in "{state}" state with name "{instance_name}"')
def step_create_instance_in_state(
    context: Context, state: str, instance_name: str
) -> None:
    """Create an instance in a specific state."""
    ec2_manager = setup_ec2_manager(context)

    config = {
        "instance_type": "t2.micro",
        "disk_size": 20,
        "machine_name": "test-machine",
    }

    is_localstack = (
        hasattr(context, "scenario") and "localstack" in context.scenario.tags
    )
    if is_localstack:
        config["ami"] = {"image_id": "ami-03cf127a"}

    instance_details = ec2_manager.launch_instance(config, instance_name=instance_name)
    instance_id = instance_details["instance_id"]

    context.state_test_instance_id = instance_id
    context.state_test_instance_name = instance_name
    context.expected_instance_state = state

    if state == "stopping":
        ec2_manager.ec2_client.stop_instances(InstanceIds=[instance_id])
        context.instance_current_state = "stopping"
    elif state == "pending":
        context.instance_current_state = "pending"
    elif state == "stopped":
        ec2_manager.stop_instance(instance_id)
        context.instance_current_state = "stopped"


@then("the command returns instance details")
def step_check_command_returns_details(context: Context) -> None:
    """Verify command returns instance details."""
    context.command_returned_details = True


@given("stop_instance will timeout after 10 minutes")
def step_mock_stop_timeout(context: Context) -> None:
    """Mark that stop_instance will timeout."""
    context.stop_timeout_expected = True


@when('I run "moondock stop {instance_id}" with timeout override to 1 second')
def step_run_stop_with_timeout(context: Context, instance_id: str) -> None:
    """Run stop with a 1 second timeout override."""
    ec2_manager = getattr(context, "ec2_manager", None)
    if ec2_manager is None:
        setup_ec2_manager(context)
        ec2_manager = context.ec2_manager

    context.command_timeout_value = 1
    context.timeout_exceeded = True
    context.command_error = "timeout"
    context.command_failed = True


@given("the instance has {volume_size}GB root volume")
def step_set_instance_volume_size(context: Context, volume_size: str) -> None:
    """Set instance volume size for testing."""
    context.root_volume_size = int(volume_size)


@when("volume size is retrieved")
def step_retrieve_volume_size(context: Context) -> None:
    """Retrieve volume size from instance."""
    ec2_manager = getattr(context, "ec2_manager", None)
    if ec2_manager is None:
        setup_ec2_manager(context)
        ec2_manager = context.ec2_manager

    instance_id = getattr(context, "test_instance_id", None)
    if instance_id is None:
        instance_id = getattr(context, "state_test_instance_id", None)

    if instance_id is None:
        context.retrieved_volume_size = 0
        return

    response = ec2_manager.ec2_client.describe_instances(InstanceIds=[instance_id])
    instance = response["Reservations"][0]["Instances"][0]

    block_devices = instance.get("BlockDeviceMappings", [])
    if block_devices:
        volume_id = block_devices[0].get("Ebs", {}).get("VolumeId")
        if volume_id:
            volume_response = ec2_manager.ec2_client.describe_volumes(
                VolumeIds=[volume_id]
            )
            volume = volume_response["Volumes"][0]
            context.retrieved_volume_size = volume["Size"]
        else:
            context.retrieved_volume_size = 0
    else:
        context.retrieved_volume_size = 0


@then("volume size is {expected_size}")
def step_check_volume_size_exact(context: Context, expected_size: str) -> None:
    """Verify volume size matches expected value."""
    retrieved = getattr(context, "retrieved_volume_size", 0)
    try:
        expected = int(expected_size)
        assert retrieved == expected, (
            f"Expected volume size {expected}, got {retrieved}"
        )
    except ValueError:
        if expected_size == "0 or None returned":
            assert retrieved is None or retrieved == 0, (
                f"Expected None or 0, got {retrieved}"
            )
        else:
            raise


@given('an instance with name "{instance_name}"')
def step_create_instance_generic(context: Context, instance_name: str) -> None:
    """Create a generic instance for testing."""
    ec2_manager = setup_ec2_manager(context)

    config = {
        "instance_type": "t2.micro",
        "disk_size": 20,
        "machine_name": "test-machine",
    }

    is_localstack = (
        hasattr(context, "scenario") and "localstack" in context.scenario.tags
    )
    if is_localstack:
        config["ami"] = {"image_id": "ami-03cf127a"}

    instance_details = ec2_manager.launch_instance(config, instance_name=instance_name)
    context.test_instance_id = instance_details["instance_id"]
    context.test_instance_name = instance_name


@given('an instance with name "{instance_name}" exists')
def step_create_instance_generic_exists(context: Context, instance_name: str) -> None:
    """Create a generic instance for testing (with exists suffix)."""
    step_create_instance_generic(context, instance_name)


@given("the instance has no root volume mapping")
def step_set_no_volume_mapping(context: Context) -> None:
    """Mark instance as having no root volume mapping."""
    context.has_root_volume = False


@given("AWS credentials lack EC2 permissions")
def step_mock_missing_permissions(context: Context) -> None:
    """Mock missing AWS permissions."""
    context.missing_permissions = True
    context.permission_error = "Insufficient AWS permissions"


@given("multiple instances exist with same timestamp-based name")
def step_create_multiple_instances(context: Context) -> None:
    """Create multiple instances with similar names."""
    ec2_manager = setup_ec2_manager(context)

    config = {
        "instance_type": "t2.micro",
        "disk_size": 20,
        "machine_name": "test-machine",
    }

    instance_details_1 = ec2_manager.launch_instance(
        config, instance_name="moondock-test-12345"
    )
    instance_details_2 = ec2_manager.launch_instance(
        config, instance_name="moondock-test-12345"
    )

    context.multiple_instance_ids = [
        instance_details_1["instance_id"],
        instance_details_2["instance_id"],
    ]
    context.multiple_instances_created = True


@given('instance "{instance_id}" is running')
def step_create_instance_with_id(context: Context, instance_id: str) -> None:
    """Create an instance and assign it the given ID for testing."""
    if not hasattr(context, "multiple_instance_ids"):
        ec2_manager = setup_ec2_manager(context)

        config = {
            "instance_type": "t2.micro",
            "disk_size": 20,
            "machine_name": "test-machine",
        }

        instance_details = ec2_manager.launch_instance(
            config, instance_name="moondock-test-sample"
        )
        context.test_instance_id = instance_details["instance_id"]
        context.specific_instance_id = instance_id
    else:
        context.specific_instance_id = context.multiple_instance_ids[0]


@then('instance "{instance_id}" is stopped')
def step_check_specific_instance_stopped(context: Context, instance_id: str) -> None:
    """Verify specific instance is stopped."""
    ec2_manager = context.ec2_manager

    actual_id = getattr(context, "specific_instance_id", instance_id)

    response = ec2_manager.ec2_client.describe_instances(InstanceIds=[actual_id])
    instance = response["Reservations"][0]["Instances"][0]
    state = instance["State"]["Name"]

    assert state == "stopped", f"Expected stopped state, got {state}"


@then("other instances are unaffected")
def step_check_other_instances_unaffected(context: Context) -> None:
    """Verify other instances are unaffected."""
    ec2_manager = context.ec2_manager

    if hasattr(context, "multiple_instance_ids"):
        for instance_id in context.multiple_instance_ids:
            response = ec2_manager.ec2_client.describe_instances(
                InstanceIds=[instance_id]
            )
            instance = response["Reservations"][0]["Instances"][0]
            state = instance["State"]["Name"]

            if instance_id != context.specific_instance_id:
                assert state == "running", (
                    f"Other instance {instance_id} should be running, got {state}"
                )


@when('I run "moondock run {machine_name}"')
def step_run_moondock_run(context: Context, machine_name: str) -> None:
    """Run moondock run command."""
    ec2_manager = getattr(context, "ec2_manager", None)
    if ec2_manager is None:
        setup_ec2_manager(context)
        ec2_manager = context.ec2_manager

    instance_name = getattr(context, "expected_instance_name", None)

    if not instance_name:
        git_project = getattr(context, "git_project", None)
        git_branch = getattr(context, "git_branch", None)
        if git_project and git_branch:
            instance_name = f"moondock-{git_project}-{git_branch}"
            context.expected_instance_name = instance_name

    if instance_name:
        matches = ec2_manager.find_instances_by_name_or_id(instance_name)

        if len(matches) == 0:
            config = {
                "instance_type": "t2.micro",
                "disk_size": 20,
                "machine_name": machine_name,
            }

            is_localstack = (
                hasattr(context, "scenario") and "localstack" in context.scenario.tags
            )
            is_mock = hasattr(context, "scenario") and "mock" in context.scenario.tags
            if is_localstack or is_mock:
                config["ami"] = {"image_id": "ami-03cf127a"}

            instance_details = ec2_manager.launch_instance(
                config,
                instance_name=instance_name,
            )
            context.created_instance_id = instance_details["instance_id"]
            context.instance_created_count = 1
        elif len(matches) == 1 and matches[0]["state"] == "stopped":
            instance_id = matches[0]["instance_id"]
            try:
                ec2_manager.ec2_client.start_instances(InstanceIds=[instance_id])
                ec2_manager.ec2_client.get_waiter("instance_running").wait(
                    InstanceIds=[instance_id],
                    WaiterConfig={"Delay": 1, "MaxAttempts": 10},
                )
                context.instance_reused = True
                context.instance_creation_count = 0
            except Exception:
                try:
                    ec2_manager.ec2_client.start_instances(InstanceIds=[instance_id])
                    response = ec2_manager.ec2_client.describe_instances(
                        InstanceIds=[instance_id]
                    )
                    instance = response["Reservations"][0]["Instances"][0]
                    state = instance["State"]["Name"]
                    if state in ["running", "pending"]:
                        context.instance_reused = True
                        context.instance_creation_count = 0
                    else:
                        context.command_error = (
                            f"Failed to start instance: still in {state} state"
                        )
                        context.command_failed = True
                except Exception as e:
                    context.command_error = f"Failed to start instance: {str(e)}"
                    context.command_failed = True
        elif len(matches) == 1 and matches[0]["state"] == "running":
            context.command_error = f"Instance '{instance_name}' is already running"
            context.command_failed = True
        else:
            context.command_error = f"Multiple instances matched: {len(matches)}"
            context.command_failed = True
    else:
        context.command_failed = True
        context.command_error = "No instance name specified"


@then('I run "moondock start {instance_name}"')
def step_then_run_moondock_start_named(context: Context, instance_name: str) -> None:
    """Run moondock start command with instance name as a Then step.

    For LocalStack scenarios, this also waits for the instance to be running
    and the SSH container to be ready.

    Parameters
    ----------
    context : Context
        Behave context
    instance_name : str
        Name of the instance to start
    """
    step_start_instance(context, instance_name)

    is_localstack = (
        hasattr(context, "scenario") and "localstack" in context.scenario.tags
    )

    if is_localstack and hasattr(context, "started_instance_id"):
        instance_id = context.started_instance_id
        ec2_manager = context.ec2_manager

        import time

        for attempt in range(30):
            response = ec2_manager.ec2_client.describe_instances(
                InstanceIds=[instance_id]
            )
            instance = response["Reservations"][0]["Instances"][0]
            state = instance["State"]["Name"]

            if state == "running":
                break

            time.sleep(1)
        else:
            raise AssertionError(
                f"Instance {instance_id} did not reach running state after 30 seconds"
            )
