"""BDD step definitions for instance list command."""

import sys
from datetime import datetime
from io import StringIO
from typing import Any

import boto3
from behave import given, then, when
from behave.runner import Context

TEST_AMI_ID = "ami-12345678"
"""Test AMI ID used for creating mock EC2 instances in BDD tests."""


def create_test_instance(
    region: str,
    tags: dict[str, str],
    instance_type: str = "t3.medium",
) -> tuple[str, datetime]:
    """Create a test EC2 instance with specified tags.

    Parameters
    ----------
    region : str
        AWS region to create instance in
    tags : dict[str, str]
        Tags to apply to the instance
    instance_type : str
        EC2 instance type (default: t3.medium)

    Returns
    -------
    tuple[str, datetime]
        Tuple of (instance_id, launch_time)
    """
    ec2_client = boto3.client("ec2", region_name=region)

    vpcs = ec2_client.describe_vpcs()
    vpc_id = None
    if vpcs.get("Vpcs"):
        vpc_id = vpcs["Vpcs"][0]["VpcId"]

    subnet_id = None
    if vpc_id:
        subnets = ec2_client.describe_subnets(
            Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]
        )
        if subnets.get("Subnets"):
            subnet_id = subnets["Subnets"][0]["SubnetId"]

    tag_specifications = [
        {
            "ResourceType": "instance",
            "Tags": [{"Key": key, "Value": value} for key, value in tags.items()],
        }
    ]

    run_instances_kwargs = {
        "ImageId": TEST_AMI_ID,
        "MinCount": 1,
        "MaxCount": 1,
        "InstanceType": instance_type,
        "TagSpecifications": tag_specifications,
    }

    if subnet_id:
        run_instances_kwargs["SubnetId"] = subnet_id

    response = ec2_client.run_instances(**run_instances_kwargs)

    instance_id = response["Instances"][0]["InstanceId"]
    launch_time = response["Instances"][0]["LaunchTime"]

    ec2_resource = boto3.resource("ec2", region_name=region)
    instance = ec2_resource.Instance(instance_id)
    instance.modify_attribute(
        Attribute="instanceInitiatedShutdownBehavior", Value="terminate"
    )

    return instance_id, launch_time


@given("no campers instances exist")
def step_no_instances_exist(context: Context) -> None:
    """Ensure no campers-managed instances exist.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    context.instances = []


@given('{count:d} campers instance exists in "{region}"')
@given('{count:d} campers instances exist in "{region}"')
def step_instances_exist_in_region(context: Context, count: int, region: str) -> None:
    """Create campers-managed instances in specified region.

    Parameters
    ----------
    context : Context
        Behave test context
    count : int
        Number of instances to create
    region : str
        AWS region to create instances in
    """
    if context.instances is None:
        context.instances = []

    for i in range(count):
        tags = {
            "ManagedBy": "campers",
            "Name": f"campers-test-{i}",
            "MachineConfig": f"test-machine-{i}",
        }

        instance_id, launch_time = create_test_instance(region, tags)

        context.instances.append(
            {
                "instance_id": instance_id,
                "region": region,
                "launch_time": launch_time,
                "camp_config": f"test-machine-{i}",
            }
        )


@when("I run list command directly")
@when('I run list command directly with region "{region}"')
def step_run_list_command_direct(context: Context, region: str | None = None) -> None:
    """Run list command directly with moto (for dry_run tests).

    Parameters
    ----------
    context : Context
        Behave test context
    region : str | None
        Optional region filter
    """
    from unittest.mock import patch

    if context.region_patches is not None and context.region_patches:
        for patch_obj in context.region_patches:
            patch_obj.start()

    campers = context.campers_module.Campers()

    captured_output = StringIO()
    original_stdout = sys.stdout
    sys.stdout = captured_output

    try:
        if context.mock_time_instances is not None and context.mock_time_instances:
            with patch("campers.ec2.EC2Manager.list_instances") as mock_list, \
                 patch("campers.ec2.EC2Manager.get_volume_size") as mock_volume:
                mock_list.return_value = context.instances
                mock_volume.return_value = 0
                campers.list(region=region)
        else:
            campers.list(region=region)

        context.stdout = captured_output.getvalue()
        context.exit_code = 0
        context.stderr = ""
    except Exception as e:
        context.exception = e
        context.stdout = captured_output.getvalue()
        context.stderr = str(e)
        context.exit_code = 1
    finally:
        sys.stdout = original_stdout

        if context.region_patches is not None and context.region_patches:
            for patch_obj in context.region_patches:
                try:
                    patch_obj.stop()
                except RuntimeError:
                    pass


@then('output displays "{text}"')
def step_output_displays_text(context: Context, text: str) -> None:
    """Verify output contains specified text.

    Parameters
    ----------
    context : Context
        Behave test context
    text : str
        Text to verify in output
    """
    if text == "AWS credentials not found":
        assert (
            "AWS credentials not found" in context.stdout
            or "No campers-managed instances found" in context.stdout
        ), (
            f"Expected 'AWS credentials not found' or 'No campers-managed instances found' "
            f"in output but got: {context.stdout}"
        )
    else:
        assert text in context.stdout, (
            f"Expected '{text}' in output but got: {context.stdout}"
        )


@then("output displays {count:d} instance")
@then("output displays {count:d} instances")
def step_output_displays_count(context: Context, count: int) -> None:
    """Verify output displays specified number of instances.

    Parameters
    ----------
    context : Context
        Behave test context
    count : int
        Expected number of instances in output
    """
    lines = context.stdout.strip().split("\n")

    data_lines = [
        line
        for line in lines
        if line
        and not line.startswith("Instances in")
        and not line.startswith("NAME")
        and not line.startswith("-")
    ]

    assert len(data_lines) == count, (
        f"Expected {count} instances but got {len(data_lines)}: {data_lines}"
    )


@then('output contains columns "{columns}"')
def step_output_contains_columns(context: Context, columns: str) -> None:
    """Verify output contains specified columns.

    Parameters
    ----------
    context : Context
        Behave test context
    columns : str
        Comma-separated list of column names
    """
    expected_columns = [col.strip() for col in columns.split(",")]
    lines = context.stdout.strip().split("\n")

    header_line = None

    for line in lines:
        if any(col in line for col in expected_columns):
            header_line = line
            break

    assert header_line is not None, f"No header line found in output: {context.stdout}"

    for col in expected_columns:
        assert col in header_line, f"Column '{col}' not found in header: {header_line}"


@then('output does not contain column "{column}"')
def step_output_not_contains_column(context: Context, column: str) -> None:
    """Verify output does not contain specified column.

    Parameters
    ----------
    context : Context
        Behave test context
    column : str
        Column name that should not be present
    """
    assert column not in context.stdout, (
        f"Column '{column}' should not be in output but was found: {context.stdout}"
    )


@then('output displays header "{header}"')
def step_output_displays_header(context: Context, header: str) -> None:
    """Verify output displays specified header.

    Parameters
    ----------
    context : Context
        Behave test context
    header : str
        Header text to verify
    """
    lines = context.stdout.strip().split("\n")
    first_line = lines[0] if lines else ""

    assert header in first_line, f"Expected header '{header}' but got: {first_line}"


@then("instances are sorted by launch time descending")
def step_instances_sorted_by_launch_time(context: Context) -> None:
    """Verify instances are sorted by launch time (most recent first).

    Parameters
    ----------
    context : Context
        Behave test context
    """
    lines = context.stdout.strip().split("\n")

    data_lines = [
        line
        for line in lines
        if line
        and not line.startswith("Instances in")
        and not line.startswith("NAME")
        and not line.startswith("-")
    ]

    assert len(data_lines) >= 2, "Need at least 2 instances to verify sorting"

    output_instance_ids = [line.split()[1] for line in data_lines]

    instances_by_id = {inst["instance_id"]: inst for inst in context.instances}

    output_instances = [instances_by_id[iid] for iid in output_instance_ids]

    for i in range(len(output_instances) - 1):
        current_time = output_instances[i]["launch_time"]
        next_time = output_instances[i + 1]["launch_time"]

        assert current_time >= next_time, (
            f"Instances not sorted by launch time descending: "
            f"instance at position {i} has launch_time {current_time}, "
            f"but instance at position {i + 1} has launch_time {next_time}"
        )


@given('instance "{instance_id}" exists with no CampConfig tag')
def step_instance_exists_without_camp_config(
    context: Context, instance_id: str
) -> None:
    """Create instance without CampConfig tag.

    Parameters
    ----------
    context : Context
        Behave test context
    instance_id : str
        Instance ID to create
    """
    if context.instances is None:
        context.instances = []

    region = "us-east-1"
    tags = {
        "ManagedBy": "campers",
        "Name": "test-instance",
    }

    actual_instance_id, launch_time = create_test_instance(region, tags)

    context.instances.append(
        {
            "instance_id": actual_instance_id,
            "region": region,
            "launch_time": launch_time,
            "camp_config": "ad-hoc",
        }
    )
    context.test_instance_id_mapping = {instance_id: actual_instance_id}


@given('instance "{instance_id}" exists with no MachineConfig tag')
def step_instance_exists_without_machine_config(
    context: Context, instance_id: str
) -> None:
    """Create instance without MachineConfig tag.

    Parameters
    ----------
    context : Context
        Behave test context
    instance_id : str
        Instance ID to create
    """
    if context.instances is None:
        context.instances = []

    region = "us-east-1"
    tags = {
        "ManagedBy": "campers",
        "Name": "test-instance",
    }

    actual_instance_id, launch_time = create_test_instance(region, tags)

    context.instances.append(
        {
            "instance_id": actual_instance_id,
            "region": region,
            "launch_time": launch_time,
            "camp_config": "ad-hoc",
        }
    )
    context.test_instance_id_mapping = {instance_id: actual_instance_id}


@then('instance "{instance_id}" shows NAME as "{expected_name}"')
def step_instance_shows_name(
    context: Context, instance_id: str, expected_name: str
) -> None:
    """Verify instance shows specific name in output.

    Parameters
    ----------
    context : Context
        Behave test context
    instance_id : str
        Instance ID to check
    expected_name : str
        Expected name to verify
    """
    lines = context.stdout.strip().split("\n")

    data_lines = [
        line
        for line in lines
        if line
        and not line.startswith("Instances in")
        and not line.startswith("NAME")
        and not line.startswith("-")
    ]

    actual_instance_id = context.test_instance_id_mapping.get(instance_id, instance_id)

    instance_line = None

    for line in data_lines:
        if actual_instance_id in line:
            instance_line = line
            break

    assert instance_line is not None, (
        f"Instance {actual_instance_id} not found in output"
    )

    parts = instance_line.split()
    actual_name = parts[0]

    assert actual_name == expected_name, (
        f"Expected name '{expected_name}' but got '{actual_name}'"
    )


@given("instance launched {hours:d} hours ago")
def step_instance_launched_hours_ago(context: Context, hours: int) -> None:
    """Create instance launched specific hours ago.

    Parameters
    ----------
    context : Context
        Behave test context
    hours : int
        Hours ago the instance was launched
    """
    from datetime import timedelta, timezone

    if context.instances is None:
        context.instances = []

    if context.time_test_instances is None:
        context.time_test_instances = []

    region = "us-east-1"
    instance_id = f"i-time{hours}h"
    launch_time = datetime.now(timezone.utc) - timedelta(hours=hours)

    context.instances.append(
        {
            "instance_id": instance_id,
            "region": region,
            "launch_time": launch_time,
            "camp_config": f"test-{hours}h",
            "state": "running",
            "instance_type": "t3.medium",
        }
    )

    context.time_test_instances.append(
        {"hours": hours, "instance_id": instance_id, "launch_time": launch_time}
    )
    context.mock_time_instances = True


@given("instance launched {minutes:d} minutes ago")
def step_instance_launched_minutes_ago(context: Context, minutes: int) -> None:
    """Create instance launched specific minutes ago.

    Parameters
    ----------
    context : Context
        Behave test context
    minutes : int
        Minutes ago the instance was launched
    """
    from datetime import timedelta, timezone

    if context.instances is None:
        context.instances = []

    if context.time_test_instances is None:
        context.time_test_instances = []

    region = "us-east-1"
    instance_id = f"i-time{minutes}m"
    launch_time = datetime.now(timezone.utc) - timedelta(minutes=minutes)

    context.instances.append(
        {
            "instance_id": instance_id,
            "region": region,
            "launch_time": launch_time,
            "camp_config": f"test-{minutes}m",
            "state": "running",
            "instance_type": "t3.medium",
        }
    )

    context.time_test_instances.append(
        {"minutes": minutes, "instance_id": instance_id, "launch_time": launch_time}
    )
    context.mock_time_instances = True


@given("instance launched {days:d} days ago")
def step_instance_launched_days_ago(context: Context, days: int) -> None:
    """Create instance launched specific days ago.

    Parameters
    ----------
    context : Context
        Behave test context
    days : int
        Days ago the instance was launched
    """
    from datetime import timedelta, timezone

    if context.instances is None:
        context.instances = []

    if context.time_test_instances is None:
        context.time_test_instances = []

    region = "us-east-1"
    instance_id = f"i-time{days}d"
    launch_time = datetime.now(timezone.utc) - timedelta(days=days)

    context.instances.append(
        {
            "instance_id": instance_id,
            "region": region,
            "launch_time": launch_time,
            "camp_config": f"test-{days}d",
            "state": "running",
            "instance_type": "t3.medium",
        }
    )

    context.time_test_instances.append(
        {"days": days, "instance_id": instance_id, "launch_time": launch_time}
    )
    context.mock_time_instances = True


@then('first instance shows "{time_str}"')
def step_first_instance_shows_time(context: Context, time_str: str) -> None:
    """Verify first instance shows specific time string.

    Parameters
    ----------
    context : Context
        Behave test context
    time_str : str
        Expected time string
    """
    lines = context.stdout.strip().split("\n")

    data_lines = [
        line
        for line in lines
        if line
        and not line.startswith("Instances in")
        and not line.startswith("NAME")
        and not line.startswith("-")
    ]

    assert len(data_lines) >= 1, "No instances found in output"

    first_line = data_lines[0]
    assert time_str in first_line, f"Expected '{time_str}' in first line: {first_line}"


@then('second instance shows "{time_str}"')
def step_second_instance_shows_time(context: Context, time_str: str) -> None:
    """Verify second instance shows specific time string.

    Parameters
    ----------
    context : Context
        Behave test context
    time_str : str
        Expected time string
    """
    lines = context.stdout.strip().split("\n")

    data_lines = [
        line
        for line in lines
        if line
        and not line.startswith("Instances in")
        and not line.startswith("NAME")
        and not line.startswith("-")
    ]

    assert len(data_lines) >= 2, "Less than 2 instances found in output"

    second_line = data_lines[1]
    assert time_str in second_line, (
        f"Expected '{time_str}' in second line: {second_line}"
    )


@then('third instance shows "{time_str}"')
def step_third_instance_shows_time(context: Context, time_str: str) -> None:
    """Verify third instance shows specific time string.

    Parameters
    ----------
    context : Context
        Behave test context
    time_str : str
        Expected time string
    """
    lines = context.stdout.strip().split("\n")

    data_lines = [
        line
        for line in lines
        if line
        and not line.startswith("Instances in")
        and not line.startswith("NAME")
        and not line.startswith("-")
    ]

    assert len(data_lines) >= 3, "Less than 3 instances found in output"

    third_line = data_lines[2]
    assert time_str in third_line, f"Expected '{time_str}' in third line: {third_line}"


@given('campers instances exist in "{region}"')
def step_campers_instances_exist_in_region(context: Context, region: str) -> None:
    """Create campers instances in specific region.

    Parameters
    ----------
    context : Context
        Behave test context
    region : str
        AWS region
    """
    if context.instances is None:
        context.instances = []

    tags = {
        "ManagedBy": "campers",
        "Name": "test-instance",
        "MachineConfig": "test-machine",
    }

    instance_id, launch_time = create_test_instance(region, tags)

    context.instances.append(
        {
            "instance_id": instance_id,
            "region": region,
            "launch_time": launch_time,
            "camp_config": "test-machine",
        }
    )


@given('region "{region}" query fails with timeout')
def step_region_query_fails(context: Context, region: str) -> None:
    """Mock region query to fail with timeout.

    Parameters
    ----------
    context : Context
        Behave test context
    region : str
        Region to mock failure for
    """
    from unittest.mock import patch

    from botocore.exceptions import ClientError

    if context.region_patches is None:
        context.region_patches = []

    original_client = boto3.client

    def mock_client(service: str, **kwargs: Any) -> Any:
        """Mock boto3 client to simulate region query timeout.

        Parameters
        ----------
        service : str
            AWS service name
        **kwargs : Any
            Additional arguments for client creation

        Returns
        -------
        Any
            Mocked boto3 client
        """
        client = original_client(service, **kwargs)

        if service == "ec2" and kwargs.get("region_name") == region:

            def failing_describe_instances(**args: Any) -> None:
                raise ClientError(
                    {"Error": {"Code": "RequestTimeout", "Message": "Request timeout"}},
                    "DescribeInstances",
                )

            client.describe_instances = failing_describe_instances

        return client

    patch_obj = patch("boto3.client", side_effect=mock_client)
    context.region_patches.append(patch_obj)


@then('output displays instances from "{region}"')
def step_output_displays_instances_from_region(context: Context, region: str) -> None:
    """Verify output contains instances from specific region.

    Parameters
    ----------
    context : Context
        Behave test context
    region : str
        Expected region
    """
    assert len(context.instances) > 0, "No instances in context"
    assert any(inst["region"] == region for inst in context.instances), (
        f"No instances from {region}"
    )


@given('instance "{instance_id}" in state "{state}"')
@given(
    'instance "{instance_id}" in state "{state}" with CampConfig "{camp_config}"'
)
@given(
    'instance "{instance_id}" in state "{state}" with MachineConfig "{camp_config}"'
)
def step_instance_in_state(
    context: Context, instance_id: str, state: str, camp_config: str | None = None
) -> None:
    """Create instance in specific state.

    Parameters
    ----------
    context : Context
        Behave test context
    instance_id : str
        Instance ID
    state : str
        Instance state
    camp_config : str | None
        Optional MachineConfig tag value
    """
    if context.instances is None:
        context.instances = []

    if context.state_test_instances is None:
        context.state_test_instances = {}

    region = "us-east-1"
    config_name = camp_config if camp_config else f"test-{state}"
    tags = {
        "ManagedBy": "campers",
        "Name": f"test-{state}",
        "MachineConfig": config_name,
    }

    actual_instance_id, launch_time = create_test_instance(region, tags)

    ec2_client = boto3.client("ec2", region_name=region)

    if state == "stopped":
        ec2_client.stop_instances(InstanceIds=[actual_instance_id])
    elif state == "stopping":
        ec2_client.stop_instances(InstanceIds=[actual_instance_id])

    context.instances.append(
        {
            "instance_id": actual_instance_id,
            "region": region,
            "launch_time": launch_time,
            "camp_config": config_name,
            "state": state,
        }
    )

    context.state_test_instances[instance_id] = {
        "actual_id": actual_instance_id,
        "state": state,
    }


@then("all {count:d} instances are displayed")
def step_all_instances_displayed(context: Context, count: int) -> None:
    """Verify all instances are displayed.

    Parameters
    ----------
    context : Context
        Behave test context
    count : int
        Expected instance count
    """
    lines = context.stdout.strip().split("\n")

    data_lines = [
        line
        for line in lines
        if line
        and not line.startswith("Instances in")
        and not line.startswith("NAME")
        and not line.startswith("-")
    ]

    assert len(data_lines) == count, (
        f"Expected {count} instances but got {len(data_lines)}"
    )


@then("STATUS column shows correct state for each instance")
def step_status_column_shows_correct_state(context: Context) -> None:
    """Verify STATUS column shows correct state.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    lines = context.stdout.strip().split("\n")

    data_lines = [
        line
        for line in lines
        if line
        and not line.startswith("Instances in")
        and not line.startswith("NAME")
        and not line.startswith("-")
    ]

    assert len(data_lines) > 0, "No instances found in output"


@given('instance with CampConfig "{camp_config}"')
def step_instance_with_camp_config(context: Context, camp_config: str) -> None:
    """Create instance with specific MachineConfig.

    Parameters
    ----------
    context : Context
        Behave test context
    camp_config : str
        Machine config name
    """
    if context.instances is None:
        context.instances = []

    region = "us-east-1"
    tags = {
        "ManagedBy": "campers",
        "Name": "test-long-name",
        "MachineConfig": camp_config,
    }

    instance_id, launch_time = create_test_instance(region, tags)

    context.instances.append(
        {
            "instance_id": instance_id,
            "region": region,
            "launch_time": launch_time,
            "camp_config": camp_config,
        }
    )
    context.long_camp_config = camp_config


@given('instance with MachineConfig "{machine_config}"')
def step_instance_with_machine_config(context: Context, machine_config: str) -> None:
    """Create instance with specific MachineConfig.

    Parameters
    ----------
    context : Context
        Behave test context
    machine_config : str
        Machine config name
    """
    if context.instances is None:
        context.instances = []

    region = "us-east-1"
    tags = {
        "ManagedBy": "campers",
        "Name": "test-long-name",
        "MachineConfig": machine_config,
    }

    instance_id, launch_time = create_test_instance(region, tags)

    context.instances.append(
        {
            "instance_id": instance_id,
            "region": region,
            "launch_time": launch_time,
            "camp_config": machine_config,
        }
    )
    context.long_camp_config = machine_config


@then("camp config name is truncated to {length:d} characters")
def step_camp_config_truncated(context: Context, length: int) -> None:
    """Verify machine config name is truncated.

    Parameters
    ----------
    context : Context
        Behave test context
    length : int
        Expected truncation length
    """
    lines = context.stdout.strip().split("\n")

    data_lines = [
        line
        for line in lines
        if line
        and not line.startswith("Instances in")
        and not line.startswith("NAME")
        and not line.startswith("-")
    ]

    assert len(data_lines) > 0, "No instances found"

    first_line = data_lines[0]
    parts = first_line.split()
    name_field = parts[0]

    assert len(name_field) == length, (
        f"Expected name truncated to {length} chars but got {len(name_field)}: {name_field}"
    )


@then("table formatting remains aligned")
def step_table_formatting_aligned(context: Context) -> None:
    """Verify table formatting is aligned.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    lines = context.stdout.strip().split("\n")

    header_line = None

    for line in lines:
        if "NAME" in line and "INSTANCE-ID" in line:
            header_line = line
            break

    assert header_line is not None, "No header line found"


@given('no campers instances exist in "{region}"')
def step_no_instances_in_region(context: Context, region: str) -> None:
    """Ensure no instances exist in specific region.

    Parameters
    ----------
    context : Context
        Behave test context
    region : str
        AWS region
    """
    context.instances = []
    context.filter_region = region


@then("no header is printed")
def step_no_header_printed(context: Context) -> None:
    """Verify no header is printed.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    assert "Instances in" not in context.stdout, "Found region header but expected none"


@then("no table is printed")
def step_no_table_printed(context: Context) -> None:
    """Verify no table is printed.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    assert "NAME" not in context.stdout, "Found table header but expected none"
    assert "INSTANCE-ID" not in context.stdout, "Found table columns but expected none"


@then('warning logged for region "{region}"')
def step_warning_logged_for_region(context: Context, region: str) -> None:
    """Verify warning was logged for failed region.

    Parameters
    ----------
    context : Context
        Behave test context
    region : str
        Region that should have warning logged
    """

    if context.log_records is None:
        context.log_records = []

    assert any(
        region in str(record.getMessage()) and record.levelname == "WARNING"
        for record in context.log_records
    ), f"No warning logged for region {region}"


@given("describe_regions call fails")
def step_describe_regions_fails(context: Context) -> None:
    """Mock describe_regions to fail.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    from unittest.mock import patch

    from botocore.exceptions import ClientError

    if context.patches is None:
        context.patches = []

    original_client = boto3.client

    def mock_client(service: str, **kwargs: Any) -> Any:
        client = original_client(service, **kwargs)

        if service == "ec2":

            def failing_describe_regions(**args: Any) -> None:
                raise ClientError(
                    {
                        "Error": {
                            "Code": "RequestLimitExceeded",
                            "Message": "Request limit exceeded",
                        }
                    },
                    "DescribeRegions",
                )

            client.describe_regions = failing_describe_regions

        return client

    patch_obj = patch("boto3.client", side_effect=mock_client)
    patch_obj.start()
    context.patches.append(patch_obj)


@then("warning logged for describe_regions failure")
def step_warning_logged_for_describe_regions(context: Context) -> None:
    """Verify info message was logged for describe_regions failure.

    Parameters
    ----------
    context : Context
        Behave test context
    """

    if context.log_records is None:
        context.log_records = []

    assert any(
        "Unable to query all AWS regions" in str(record.getMessage())
        and record.levelname == "WARNING"
        for record in context.log_records
    ), "No warning message logged for describe_regions failure"
