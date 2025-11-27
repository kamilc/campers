"""BDD step definitions for instance info output."""

import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
from behave import given, then
from behave.runner import Context
from botocore.exceptions import ClientError

from tests.integration.features.steps.ec2_steps import setup_moto_environment
from tests.integration.features.steps.ssh_steps import get_combined_log_output


@given('I have a running instance with camp "{camp_name}"')
def step_running_instance_with_camp(context: Context, camp_name: str) -> None:
    """Create a running instance with specified camp config.

    Parameters
    ----------
    context : Context
        Behave test context
    camp_name : str
        Camp name for the instance
    """
    setup_moto_environment(context)

    region = "us-east-1"
    ec2_client = boto3.client("ec2", region_name=region)
    ec2_resource = boto3.resource("ec2", region_name=region)

    ami_id = ec2_client.register_image(
        Name="ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-20231201",
        Description="Ubuntu 22.04 LTS",
        Architecture="x86_64",
        RootDeviceName="/dev/sda1",
        VirtualizationType="hvm",
    )["ImageId"]

    vpcs = ec2_client.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])
    if not vpcs["Vpcs"]:
        try:
            ec2_client.create_default_vpc()
        except ClientError:
            pass
        vpcs = ec2_client.describe_vpcs(
            Filters=[{"Name": "isDefault", "Values": ["true"]}]
        )
    vpc_id = vpcs["Vpcs"][0]["VpcId"]

    unique_id = str(uuid.uuid4()).replace("-", "")[:12]
    sg_response = ec2_client.create_security_group(
        GroupName=f"campers-{unique_id}",
        Description=f"Test SG {unique_id}",
        VpcId=vpc_id,
    )
    security_group_id = sg_response["GroupId"]

    key_response = ec2_client.create_key_pair(KeyName=f"campers-{unique_id}")

    instances = ec2_resource.create_instances(
        ImageId=ami_id,
        InstanceType="t3.medium",
        KeyName=f"campers-{unique_id}",
        SecurityGroupIds=[security_group_id],
        MinCount=1,
        MaxCount=1,
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "ManagedBy", "Value": "campers"},
                    {"Key": "MachineConfig", "Value": camp_name},
                    {"Key": "UniqueId", "Value": unique_id},
                    {"Key": "Name", "Value": f"campers-{unique_id}"},
                ],
            }
        ],
    )

    instance = instances[0]

    campers_dir = Path(os.environ.get("CAMPERS_DIR", "~/.campers")).expanduser()
    keys_dir = campers_dir / "keys"
    keys_dir.mkdir(parents=True, exist_ok=True)
    key_file = keys_dir / f"{unique_id}.pem"
    key_file.write_text(key_response["KeyMaterial"])
    key_file.chmod(0o600)

    context.instance = instance
    context.instance_id = instance.id
    context.unique_id = unique_id
    context.camp_name = camp_name
    context.region = region
    context.ec2_client = ec2_client
    context.key_file = str(key_file)

    if not hasattr(context, "instances") or context.instances is None:
        context.instances = []

    context.instances.append({
        "instance_id": instance.id,
        "name": f"campers-{unique_id}",
        "state": "running",
        "region": region,
        "instance_type": "t3.medium",
        "launch_time": instance.launch_time,
        "camp_config": camp_name,
        "unique_id": unique_id,
    })

    if context.config_data is None:
        context.config_data = {}

    if "camps" not in context.config_data:
        context.config_data["camps"] = {}

    context.config_data["camps"][camp_name] = {
        "instance_type": "t3.medium",
        "region": region,
    }


@given('I have a running instance launched {duration} ago')
def step_running_instance_launched_ago(context: Context, duration: str) -> None:
    """Create a running instance that was launched specified duration ago.

    Parameters
    ----------
    context : Context
        Behave test context
    duration : str
        Duration ago (e.g., "30 minutes", "2 hours")
    """
    step_running_instance_with_camp(context, "test-instance")

    minutes_ago = 0
    if "minute" in duration:
        minutes_ago = int(duration.split()[0])
    elif "hour" in duration:
        hours_ago = int(duration.split()[0])
        minutes_ago = hours_ago * 60

    context.expected_uptime_minutes = minutes_ago

    time_delta = timedelta(minutes=minutes_ago)
    launch_time_in_past = datetime.now(timezone.utc) - time_delta

    if context.instances and len(context.instances) > 0:
        context.instances[-1]["launch_time"] = launch_time_in_past


@then("output contains launch time information")
def step_output_contains_launch_time(context: Context) -> None:
    """Verify output contains launch time information.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    log_output = get_combined_log_output(context)
    combined_output = context.stdout + context.stderr + log_output

    assert (
        "launch" in combined_output.lower()
        or "time" in combined_output.lower()
    ), f"Expected launch time information in output:\n{combined_output}"


@then("output contains ISO timestamp")
def step_output_contains_iso_timestamp(context: Context) -> None:
    """Verify output contains an ISO-formatted timestamp.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    log_output = get_combined_log_output(context)
    combined_output = context.stdout + context.stderr + log_output

    iso_pattern = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    match = re.search(iso_pattern, combined_output)
    assert match is not None, (
        f"Expected ISO timestamp in output:\n{combined_output}"
    )
    context.found_iso_timestamp = match.group()


@then("timestamp is recent")
def step_timestamp_is_recent(context: Context) -> None:
    """Verify the found timestamp is recent.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    if not hasattr(context, "found_iso_timestamp"):
        raise AssertionError("No ISO timestamp found in previous step")

    timestamp_str = context.found_iso_timestamp
    found_time = datetime.fromisoformat(timestamp_str)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    time_diff = now - found_time
    assert (
        time_diff < timedelta(minutes=5)
    ), f"Timestamp {timestamp_str} is not recent (diff: {time_diff})"


@then("output contains unique identifier")
def step_output_contains_unique_id(context: Context) -> None:
    """Verify output contains unique identifier.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    log_output = get_combined_log_output(context)
    combined_output = context.stdout + context.stderr + log_output

    if hasattr(context, "unique_id"):
        assert context.unique_id in combined_output, (
            f"Expected unique_id '{context.unique_id}' in output:\n{combined_output}"
        )


@then("unique ID matches instance tag")
def step_unique_id_matches_tag(context: Context) -> None:
    """Verify unique ID in output matches instance tag.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    log_output = get_combined_log_output(context)
    combined_output = context.stdout + context.stderr + log_output

    if hasattr(context, "unique_id"):
        assert context.unique_id in combined_output, (
            f"Expected unique_id '{context.unique_id}' in output:\n{combined_output}"
        )


@then("output contains key file path")
def step_output_contains_key_file(context: Context) -> None:
    """Verify output contains key file path.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    log_output = get_combined_log_output(context)
    combined_output = context.stdout + context.stderr + log_output

    assert (
        ".pem" in combined_output or "key" in combined_output.lower()
    ), f"Expected key file path in output:\n{combined_output}"


@then("key file path matches expected format")
def step_key_file_path_format(context: Context) -> None:
    """Verify key file path follows expected pattern.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    log_output = get_combined_log_output(context)
    combined_output = context.stdout + context.stderr + log_output

    key_file_pattern = r"~?/?\.?campers/keys/[a-f0-9]{12}\.pem"
    assert re.search(
        key_file_pattern, combined_output
    ), f"Expected key file path matching pattern in output:\n{combined_output}"


@then("output contains uptime information")
def step_output_contains_uptime(context: Context) -> None:
    """Verify output contains uptime information.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    log_output = get_combined_log_output(context)
    combined_output = context.stdout + context.stderr + log_output

    assert (
        "uptime" in combined_output.lower()
        or "elapsed" in combined_output.lower()
        or re.search(r"\d+[hms]", combined_output)
    ), f"Expected uptime information in output:\n{combined_output}"


@then("uptime is approximately {duration}")
def step_uptime_is_approximate(context: Context, duration: str) -> None:
    """Verify uptime in output matches expected duration.

    Parameters
    ----------
    context : Context
        Behave test context
    duration : str
        Expected duration (e.g., "30 minutes", "2 hours")
    """
    if not hasattr(context, "expected_uptime_minutes"):
        raise AssertionError("Expected uptime minutes not set in context")

    log_output = get_combined_log_output(context)
    combined_output = context.stdout + context.stderr + log_output

    expected_minutes = context.expected_uptime_minutes

    uptime_pattern = r"(\d+)\s*m"
    match = re.search(uptime_pattern, combined_output)
    assert match is not None, (
        f"Expected uptime in format 'XXm' in output:\n{combined_output}"
    )

    actual_minutes = int(match.group(1))
    tolerance = max(2, expected_minutes // 5)

    assert (
        abs(actual_minutes - expected_minutes) <= tolerance
    ), f"Expected ~{expected_minutes}m uptime but got {actual_minutes}m"
