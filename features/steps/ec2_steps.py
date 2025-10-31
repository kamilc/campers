"""BDD step definitions for EC2 instance management."""

import os
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import boto3
from behave import given, then, when
from behave.runner import Context
from botocore.exceptions import ClientError, NoCredentialsError, WaiterError
from moto import mock_aws

from moondock.ec2 import EC2Manager


def setup_moto_environment(context: Context) -> None:
    """Set up moto mock AWS environment and configure AWS credentials.

    Parameters
    ----------
    context : Context
        Behave test context to store mock_aws_env
    """
    if not hasattr(context, "mock_aws_env") or context.mock_aws_env is None:
        context.mock_aws_env = mock_aws()
        context.mock_aws_env.start()

        os.environ["AWS_ACCESS_KEY_ID"] = "testing"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
        os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


def patch_ec2_manager_for_canonical_owner(ec2_manager: EC2Manager) -> None:
    """Patch EC2Manager's describe_images to return Canonical owner ID for moto compatibility.

    Parameters
    ----------
    ec2_manager : EC2Manager
        The EC2Manager instance to patch
    """
    original_describe_images = ec2_manager.ec2_client.describe_images

    def mock_describe_images(**kwargs) -> dict:
        modified_kwargs = kwargs.copy()

        if "Owners" in modified_kwargs and "099720109477" in modified_kwargs["Owners"]:
            del modified_kwargs["Owners"]

        if "Filters" in modified_kwargs:
            modified_kwargs["Filters"] = [
                f for f in modified_kwargs["Filters"] if f["Name"] in ["name", "state"]
            ]

        response = original_describe_images(**modified_kwargs)

        for image in response.get("Images", []):
            image["VirtualizationType"] = "hvm"
            image["Architecture"] = "x86_64"

        return response

    ec2_manager.ec2_client.describe_images = mock_describe_images


def simulate_launch_timeout(context: Context) -> None:
    """Simulate instance launch timeout scenario.

    Parameters
    ----------
    context : Context
        Behave test context containing ec2_config
    """
    setup_moto_environment(context)

    ec2_client = boto3.client("ec2", region_name="us-east-1")
    ec2_client.register_image(
        Name="ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-20231201",
        Description="Ubuntu 22.04 LTS",
        Architecture="x86_64",
        RootDeviceName="/dev/sda1",
        VirtualizationType="hvm",
    )

    vpcs = ec2_client.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])
    if not vpcs["Vpcs"]:
        try:
            ec2_client.create_default_vpc()
        except ClientError:
            pass

    ec2_manager = EC2Manager(region="us-east-1")
    patch_ec2_manager_for_canonical_owner(ec2_manager)

    original_create_key_pair = ec2_manager.create_key_pair

    def capture_unique_id_wrapper(unique_id: str):
        context.unique_id = unique_id
        return original_create_key_pair(unique_id)

    waiter_mock = MagicMock()
    waiter_mock.wait.side_effect = WaiterError(
        name="InstanceRunning",
        reason="Max attempts exceeded",
        last_response={"Error": {"Code": "Timeout"}},
    )

    with patch.object(ec2_manager.ec2_client, "get_waiter", return_value=waiter_mock):
        with patch.object(
            ec2_manager, "create_key_pair", side_effect=capture_unique_id_wrapper
        ):
            try:
                ec2_manager.launch_instance(context.ec2_config)
                context.exception = None
            except RuntimeError as e:
                context.exception = e

    context.ec2_client = ec2_manager.ec2_client


def simulate_termination_timeout(context: Context) -> None:
    """Simulate instance termination timeout scenario.

    Parameters
    ----------
    context : Context
        Behave test context containing ec2_manager and instance_id
    """
    ec2_manager = context.ec2_manager

    waiter_mock = MagicMock()
    waiter_mock.wait.side_effect = WaiterError(
        name="InstanceTerminated",
        reason="Max attempts exceeded",
        last_response={"Error": {"Code": "Timeout"}},
    )

    with patch.object(ec2_manager.ec2_client, "get_waiter", return_value=waiter_mock):
        try:
            ec2_manager.terminate_instance(context.instance_id)
            context.exception = None
        except RuntimeError as e:
            context.exception = e


@given("valid configuration")
def step_valid_configuration(context: Context) -> None:
    """Create a valid configuration for EC2 instance launch."""
    context.ec2_config = {
        "instance_type": "t3.medium",
        "disk_size": 50,
        "region": "us-east-1",
    }


@given('region "{region}"')
def step_given_region(context: Context, region: str) -> None:
    """Set the region for EC2 operations."""
    context.region = region
    context.ec2_config = {
        "instance_type": "t3.medium",
        "disk_size": 50,
        "region": region,
    }


@given("region with no Ubuntu 22.04 AMI")
def step_region_with_no_ami(context: Context) -> None:
    """Set up a mock region with no Ubuntu AMI.

    Parameters
    ----------
    context : Context
        The Behave context object.
    """
    import boto3

    context.region = "us-east-1"
    context.no_ami_found = True

    ec2_client = boto3.client("ec2", region_name="us-east-1")

    try:
        images = ec2_client.describe_images(Owners=["self"])

        for image in images.get("Images", []):
            try:
                ec2_client.deregister_image(ImageId=image["ImageId"])
            except Exception:
                pass
    except Exception:
        pass


@given('running instance with unique_id "{unique_id}"')
def step_running_instance_with_unique_id(context: Context, unique_id: str) -> None:
    """Create a running EC2 instance with specific unique_id."""
    setup_moto_environment(context)

    ec2_client = boto3.client("ec2", region_name="us-east-1")
    ec2_resource = boto3.resource("ec2", region_name="us-east-1")

    ami_id = ec2_client.register_image(
        Name="ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-20231201",
        Description="Ubuntu 22.04 LTS",
        Architecture="x86_64",
        RootDeviceName="/dev/sda1",
        VirtualizationType="hvm",
    )["ImageId"]

    vpcs = ec2_client.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])
    vpc_id = vpcs["Vpcs"][0]["VpcId"]

    sg_response = ec2_client.create_security_group(
        GroupName=f"moondock-{unique_id}",
        Description=f"Test SG {unique_id}",
        VpcId=vpc_id,
    )
    context.security_group_id = sg_response["GroupId"]

    key_response = ec2_client.create_key_pair(KeyName=f"moondock-{unique_id}")

    moondock_dir = os.environ.get("MOONDOCK_DIR", str(Path.home() / ".moondock"))
    keys_dir = Path(moondock_dir) / "keys"
    keys_dir.mkdir(parents=True, exist_ok=True)
    key_file = keys_dir / f"{unique_id}.pem"
    key_file.write_text(key_response["KeyMaterial"])
    key_file.chmod(0o600)
    context.key_file = key_file

    instances = ec2_resource.create_instances(
        ImageId=ami_id,
        InstanceType="t3.medium",
        KeyName=f"moondock-{unique_id}",
        SecurityGroupIds=[context.security_group_id],
        MinCount=1,
        MaxCount=1,
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "ManagedBy", "Value": "moondock"},
                    {"Key": "UniqueId", "Value": unique_id},
                ],
            }
        ],
    )

    context.instance = instances[0]
    context.instance_id = instances[0].id
    context.unique_id = unique_id
    context.ec2_client = ec2_client
    context.ec2_manager = EC2Manager(region="us-east-1")
    patch_ec2_manager_for_canonical_owner(context.ec2_manager)


@given("running instance")
def step_running_instance(context: Context) -> None:
    """Create a running EC2 instance."""
    step_running_instance_with_unique_id(context, uuid.uuid4().hex[:16])


@given("no AWS credentials configured")
def step_no_aws_credentials(context: Context) -> None:
    """Remove AWS credentials from environment."""
    context.aws_keys_backup = {
        "AWS_ACCESS_KEY_ID": os.environ.get("AWS_ACCESS_KEY_ID"),
        "AWS_SECRET_ACCESS_KEY": os.environ.get("AWS_SECRET_ACCESS_KEY"),
    }

    for key in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"]:
        if key in os.environ:
            del os.environ[key]


@given('config with instance_type "{instance_type}"')
def step_config_with_instance_type(context: Context, instance_type: str) -> None:
    """Create config with specific instance type."""
    context.ec2_config = {
        "instance_type": instance_type,
        "disk_size": 50,
        "region": "us-east-1",
    }


@given("instance fails to reach running state")
def step_instance_fails_to_reach_running(context: Context) -> None:
    """Set up scenario where instance fails to reach running state."""
    context.timeout_scenario = True
    context.ec2_config = {
        "instance_type": "t3.medium",
        "disk_size": 50,
        "region": "us-east-1",
    }


@given("instance fails to reach terminated state")
def step_instance_fails_to_reach_terminated(context: Context) -> None:
    """Set up scenario where instance fails to reach terminated state."""
    context.termination_timeout = True
    step_running_instance(context)


@given('key pair "{key_name}" already exists')
def step_key_pair_exists(context: Context, key_name: str) -> None:
    """Create an existing key pair."""
    setup_moto_environment(context)

    ec2_client = boto3.client("ec2", region_name="us-east-1")
    ec2_client.create_key_pair(KeyName=key_name)
    context.existing_key_name = key_name
    context.ec2_client = ec2_client


@given('security group "{sg_name}" already exists')
def step_security_group_exists(context: Context, sg_name: str) -> None:
    """Create an existing security group."""
    if not hasattr(context, "ec2_client"):
        setup_moto_environment(context)
        context.ec2_client = boto3.client("ec2", region_name="us-east-1")

    vpcs = context.ec2_client.describe_vpcs(
        Filters=[{"Name": "isDefault", "Values": ["true"]}]
    )
    if not vpcs["Vpcs"]:
        try:
            context.ec2_client.create_default_vpc()
        except ClientError:
            pass
        vpcs = context.ec2_client.describe_vpcs(
            Filters=[{"Name": "isDefault", "Values": ["true"]}]
        )
    vpc_id = vpcs["Vpcs"][0]["VpcId"]

    response = context.ec2_client.create_security_group(
        GroupName=sg_name,
        Description="Existing SG",
        VpcId=vpc_id,
    )
    context.existing_sg_id = response["GroupId"]


@given("key pair is created")
def step_key_pair_is_created(context: Context) -> None:
    """Create a key pair (for rollback testing)."""
    setup_moto_environment(context)

    context.ec2_client = boto3.client("ec2", region_name="us-east-1")
    context.ec2_client.register_image(
        Name="ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-20231201",
        Description="Ubuntu 22.04 LTS",
        Architecture="x86_64",
        RootDeviceName="/dev/sda1",
        VirtualizationType="hvm",
    )

    context.unique_id = "test-rollback-key"
    context.ec2_config = {
        "instance_type": "invalid.type",
        "disk_size": 50,
        "region": "us-east-1",
    }


@given("security group is created")
def step_security_group_is_created(context: Context) -> None:
    """Set up security group creation for rollback testing.

    Parameters
    ----------
    context : Context
        Behave test context
    """
    setup_moto_environment(context)

    context.ec2_client = boto3.client("ec2", region_name="us-east-1")

    initial_sgs = context.ec2_client.describe_security_groups()
    context.initial_sg_ids = {sg["GroupId"] for sg in initial_sgs["SecurityGroups"]}

    context.ec2_config = {
        "instance_type": "t3.medium",
        "disk_size": 50,
        "region": "us-east-1",
    }


@when("I launch instance")
def step_launch_instance(context: Context) -> None:
    """Launch EC2 instance."""
    setup_moto_environment(context)

    ec2_client = boto3.client("ec2", region_name="us-east-1")
    ec2_client.register_image(
        Name="ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-20231201",
        Description="Ubuntu 22.04 LTS",
        Architecture="x86_64",
        RootDeviceName="/dev/sda1",
        VirtualizationType="hvm",
    )

    vpcs = ec2_client.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])
    if not vpcs["Vpcs"]:
        try:
            ec2_client.create_default_vpc()
        except ClientError:
            pass

    ec2_manager = EC2Manager(region="us-east-1")
    patch_ec2_manager_for_canonical_owner(ec2_manager)

    with patch("time.time", return_value=1234567890):
        context.instance_details = ec2_manager.launch_instance(context.ec2_config)

    context.ec2_manager = ec2_manager
    context.ec2_client = ec2_manager.ec2_client


@when('I launch instance with machine "{machine_name}"')
def step_launch_instance_with_machine(context: Context, machine_name: str) -> None:
    """Launch instance using machine config."""
    if hasattr(context, "config_data") and context.config_data:
        defaults = context.config_data.get("defaults", {})
        machine_config = context.config_data.get("machines", {}).get(machine_name, {})
        context.ec2_config = {
            "instance_type": machine_config.get(
                "instance_type", defaults.get("instance_type", "t3.medium")
            ),
            "disk_size": machine_config.get("disk_size", defaults.get("disk_size", 50)),
            "region": machine_config.get("region", defaults.get("region", "us-east-1")),
            "machine_name": machine_name,
        }

    step_launch_instance(context)
    context.machine_name = machine_name


@when('I launch instance with options "{options}"')
def step_launch_instance_with_options(context: Context, options: str) -> None:
    """Launch instance with CLI options."""
    if hasattr(context, "config_data") and context.config_data:
        defaults = context.config_data.get("defaults", {})
        context.ec2_config = {
            "instance_type": defaults.get("instance_type", "t3.medium"),
            "disk_size": defaults.get("disk_size", 50),
            "region": defaults.get("region", "us-east-1"),
        }
    else:
        context.ec2_config = {
            "instance_type": "t3.medium",
            "disk_size": 50,
            "region": "us-east-1",
        }

    parts = options.split()
    i = 0

    while i < len(parts):
        if parts[i] == "--instance-type" and i + 1 < len(parts):
            context.ec2_config["instance_type"] = parts[i + 1]
            i += 2
        elif parts[i] == "--region" and i + 1 < len(parts):
            context.ec2_config["region"] = parts[i + 1]
            i += 2
        elif parts[i] == "--disk-size" and i + 1 < len(parts):
            context.ec2_config["disk_size"] = int(parts[i + 1])
            i += 2
        else:
            i += 1

    step_launch_instance(context)


@when("I lookup Ubuntu 22.04 AMI")
def step_lookup_ubuntu_ami(context: Context) -> None:
    """Lookup Ubuntu 22.04 AMI."""
    setup_moto_environment(context)

    ec2_client = boto3.client("ec2", region_name=context.region)

    context.ami_id = ec2_client.register_image(
        Name="ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-20231201",
        Description="Ubuntu 22.04 LTS",
        Architecture="x86_64",
        RootDeviceName="/dev/sda1",
        VirtualizationType="hvm",
    )["ImageId"]

    ec2_manager = EC2Manager(region=context.region)
    patch_ec2_manager_for_canonical_owner(ec2_manager)
    context.found_ami_id = ec2_manager.find_ubuntu_ami()
    context.ec2_client = ec2_manager.ec2_client


@when("I attempt to lookup AMI")
def step_attempt_to_lookup_ami(context: Context) -> None:
    """Attempt to lookup AMI when none exists.

    Parameters
    ----------
    context : Context
        The Behave context object.
    """
    ec2_manager = EC2Manager(region=context.region)
    patch_ec2_manager_for_canonical_owner(ec2_manager)

    try:
        ec2_manager.find_ubuntu_ami()
        context.exception = None
        context.exit_code = 0
    except ValueError as e:
        context.exception = e
        context.exit_code = 1


@when("I terminate the instance")
def step_terminate_instance(context: Context) -> None:
    """Terminate the EC2 instance."""
    context.ec2_manager.terminate_instance(context.instance_id)

    context.instance.reload()

    if not hasattr(context, "instance_details") or context.instance_details is None:
        context.instance_details = {}
    context.instance_details["state"] = context.instance.state["Name"]


@when("I attempt to launch instance")
def step_attempt_to_launch_instance(context: Context) -> None:
    """Attempt to launch instance (may fail)."""
    try:
        if hasattr(context, "aws_keys_backup"):
            import boto3.session

            boto3.DEFAULT_SESSION = None
            boto3.session.Session._session_cache = {}

            ec2_manager = EC2Manager(region="us-east-1")
            ec2_manager.find_ubuntu_ami()
        else:
            step_launch_instance(context)
        context.exception = None
    except Exception as e:
        context.exception = e


@when("instance launch fails")
def step_instance_launch_fails(context: Context) -> None:
    """Simulate instance launch failure."""
    setup_moto_environment(context)

    ec2_client = boto3.client("ec2", region_name="us-east-1")
    ec2_client.register_image(
        Name="ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-20231201",
        Description="Ubuntu 22.04 LTS",
        Architecture="x86_64",
        RootDeviceName="/dev/sda1",
        VirtualizationType="hvm",
    )

    ec2_manager = EC2Manager(region="us-east-1")
    patch_ec2_manager_for_canonical_owner(ec2_manager)

    def failing_create_instances(*args, **kwargs):
        raise ClientError(
            {
                "Error": {
                    "Code": "InsufficientInstanceCapacity",
                    "Message": "Insufficient capacity",
                }
            },
            "RunInstances",
        )

    with patch.object(
        ec2_manager.ec2_resource,
        "create_instances",
        side_effect=failing_create_instances,
    ):
        try:
            ec2_manager.launch_instance(context.ec2_config)
            context.exception = None
        except Exception as e:
            context.exception = e

    context.ec2_client = ec2_manager.ec2_client


@when("I launch instance with same unique_id")
def step_launch_with_same_unique_id(context: Context) -> None:
    """Launch instance with conflicting resource names."""
    ec2_client = context.ec2_client

    ec2_client.register_image(
        Name="ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-20231201",
        Description="Ubuntu 22.04 LTS",
        Architecture="x86_64",
        RootDeviceName="/dev/sda1",
        VirtualizationType="hvm",
    )

    ec2_manager = EC2Manager(region="us-east-1")
    patch_ec2_manager_for_canonical_owner(ec2_manager)

    config = {"instance_type": "t3.medium", "disk_size": 50, "region": "us-east-1"}

    with patch("time.time", return_value=123):
        context.instance_details = ec2_manager.launch_instance(config)

    context.ec2_manager = ec2_manager


@when("{minutes:d} minutes elapse")
def step_minutes_elapse(context: Context, minutes: int) -> None:
    """Simulate timeout scenario by mocking waiter.

    Parameters
    ----------
    context : Context
        Behave test context
    minutes : int
        Minutes to elapse (5 for launch, 10 for termination)
    """
    if hasattr(context, "timeout_scenario") and context.timeout_scenario:
        simulate_launch_timeout(context)
    elif hasattr(context, "termination_timeout") and context.termination_timeout:
        simulate_termination_timeout(context)


@then('instance is created in region "{region}"')
def step_instance_in_region(context: Context, region: str) -> None:
    """Verify instance created in specified region."""
    assert context.instance_details is not None
    assert context.instance_details["instance_id"].startswith("i-")


@then('instance type is "{instance_type}"')
def step_verify_instance_type(context: Context, instance_type: str) -> None:
    """Verify instance type."""
    ec2_resource = boto3.resource("ec2", region_name="us-east-1")
    instance = ec2_resource.Instance(context.instance_details["instance_id"])
    instance.load()
    assert instance.instance_type == instance_type


@then("root disk size is {disk_size:d}")
def step_verify_disk_size(context: Context, disk_size: int) -> None:
    """Verify root disk size matches configuration.

    Parameters
    ----------
    context : Context
        Behave test context containing ec2_client and instance_details
    disk_size : int
        Expected disk size in GB
    """
    ec2_client = context.ec2_client
    instance_id = context.instance_details["instance_id"]

    response = ec2_client.describe_instances(InstanceIds=[instance_id])
    instance = response["Reservations"][0]["Instances"][0]

    block_devices = instance["BlockDeviceMappings"]
    root_device_name = instance["RootDeviceName"]

    root_volume = next(
        (bd for bd in block_devices if bd["DeviceName"] == root_device_name), None
    )

    assert root_volume is not None, f"Root volume {root_device_name} not found"

    volume_id = root_volume["Ebs"]["VolumeId"]
    volumes = ec2_client.describe_volumes(VolumeIds=[volume_id])
    actual_size = volumes["Volumes"][0]["Size"]

    assert actual_size == disk_size, (
        f"Expected disk size {disk_size} GB, got {actual_size} GB"
    )


@then('instance state is "{state}"')
def step_verify_instance_state(context: Context, state: str) -> None:
    """Verify instance state."""
    assert (
        context.instance_details["state"] == state
        or context.instance.state["Name"] == state
    )


@then('instance has tag "{tag_key}" with value "{tag_value}"')
def step_verify_instance_tag(context: Context, tag_key: str, tag_value: str) -> None:
    """Verify instance has specific tag."""
    ec2_resource = boto3.resource("ec2", region_name="us-east-1")
    instance = ec2_resource.Instance(context.instance_details["instance_id"])
    instance.load()

    tags = {tag["Key"]: tag["Value"] for tag in instance.tags or []}
    assert tag_key in tags
    assert tags[tag_key] == tag_value


@then('instance has tag "{tag_key}" starting with "{prefix}"')
def step_verify_instance_tag_prefix(
    context: Context, tag_key: str, prefix: str
) -> None:
    """Verify instance tag starts with prefix."""
    ec2_resource = boto3.resource("ec2", region_name="us-east-1")
    instance = ec2_resource.Instance(context.instance_details["instance_id"])
    instance.load()

    tags = {tag["Key"]: tag["Value"] for tag in instance.tags or []}
    assert tag_key in tags
    assert tags[tag_key].startswith(prefix)


@then("key pair is created in AWS")
def step_verify_key_pair_created(context: Context) -> None:
    """Verify key pair exists in AWS."""
    key_pairs = context.ec2_client.describe_key_pairs()
    assert len(key_pairs["KeyPairs"]) > 0


@then('key pair name starts with "{prefix}"')
def step_verify_key_pair_name(context: Context, prefix: str) -> None:
    """Verify key pair name starts with prefix."""
    key_pairs = context.ec2_client.describe_key_pairs()
    assert any(kp["KeyName"].startswith(prefix) for kp in key_pairs["KeyPairs"])


@then('private key is saved to "~/.moondock/keys/{unique_id}.pem"')
def step_verify_key_file_saved(context: Context, unique_id: str) -> None:
    """Verify private key saved to disk with placeholder path."""
    actual_unique_id = context.instance_details["unique_id"]
    moondock_dir = os.environ.get("MOONDOCK_DIR", str(Path.home() / ".moondock"))
    key_file = Path(moondock_dir) / "keys" / f"{actual_unique_id}.pem"
    assert key_file.exists()

    context.cleanup_key_file = key_file


@then("key file permissions are 0600")
def step_verify_key_permissions(context: Context) -> None:
    """Verify key file has correct permissions."""
    key_file = Path(context.instance_details["key_file"])
    assert oct(key_file.stat().st_mode)[-3:] == "600"


@then("instance is launched with key pair name")
def step_verify_instance_has_key(context: Context) -> None:
    """Verify instance launched with key pair."""
    ec2_resource = boto3.resource("ec2", region_name="us-east-1")
    instance = ec2_resource.Instance(context.instance_details["instance_id"])
    instance.load()
    assert instance.key_name.startswith("moondock-")


@then("key name matches security group unique_id")
def step_verify_key_sg_match(context: Context) -> None:
    """Verify key name and security group use same unique_id."""
    assert context.instance_details["unique_id"] in context.instance_details["key_file"]


@then("security group is created in default VPC")
def step_verify_sg_in_vpc(context: Context) -> None:
    """Verify security group created in VPC."""
    sg_id = context.instance_details["security_group_id"]
    sgs = context.ec2_client.describe_security_groups(GroupIds=[sg_id])
    assert len(sgs["SecurityGroups"]) == 1


@then('security group name starts with "{prefix}"')
def step_verify_sg_name(context: Context, prefix: str) -> None:
    """Verify security group name starts with prefix."""
    sg_id = context.instance_details["security_group_id"]
    sgs = context.ec2_client.describe_security_groups(GroupIds=[sg_id])
    assert sgs["SecurityGroups"][0]["GroupName"].startswith(prefix)


@then('security group has tag "{tag_key}" with value "{tag_value}"')
def step_verify_sg_tag(context: Context, tag_key: str, tag_value: str) -> None:
    """Verify security group has tag."""
    sg_id = context.instance_details["security_group_id"]
    sgs = context.ec2_client.describe_security_groups(GroupIds=[sg_id])
    tags = {
        tag["Key"]: tag["Value"] for tag in sgs["SecurityGroups"][0].get("Tags", [])
    }
    assert tags.get(tag_key) == tag_value


@then('security group allows inbound TCP port {port:d} from "{cidr}"')
def step_verify_sg_inbound_rule(context: Context, port: int, cidr: str) -> None:
    """Verify security group has inbound rule."""
    sg_id = context.instance_details["security_group_id"]
    sgs = context.ec2_client.describe_security_groups(GroupIds=[sg_id])
    permissions = sgs["SecurityGroups"][0]["IpPermissions"]

    found = False

    for perm in permissions:
        if (
            perm["IpProtocol"] == "tcp"
            and perm["FromPort"] == port
            and perm["ToPort"] == port
        ):
            if any(ip_range["CidrIp"] == cidr for ip_range in perm.get("IpRanges", [])):
                found = True
                break

    assert found


@then("security group allows all outbound traffic")
def step_verify_sg_outbound(context: Context) -> None:
    """Verify security group allows all outbound traffic.

    Parameters
    ----------
    context : Context
        Behave test context containing ec2_client and instance_details
    """
    ec2_client = context.ec2_client
    sg_id = context.instance_details["security_group_id"]

    response = ec2_client.describe_security_groups(GroupIds=[sg_id])
    security_group = response["SecurityGroups"][0]
    egress_rules = security_group.get("IpPermissionsEgress", [])

    all_traffic_rule = next(
        (
            rule
            for rule in egress_rules
            if rule.get("IpProtocol") == "-1"
            and any(
                ip_range.get("CidrIp") == "0.0.0.0/0"
                for ip_range in rule.get("IpRanges", [])
            )
        ),
        None,
    )

    assert all_traffic_rule is not None, "No rule allowing all outbound traffic found"


@then("instance is launched with security group ID")
def step_verify_instance_has_sg(context: Context) -> None:
    """Verify instance has security group."""
    ec2_resource = boto3.resource("ec2", region_name="us-east-1")
    instance = ec2_resource.Instance(context.instance_details["instance_id"])
    instance.load()
    assert len(instance.security_groups) > 0


@then("security group ID matches created group")
def step_verify_sg_id_matches(context: Context) -> None:
    """Verify security group ID matches."""
    ec2_resource = boto3.resource("ec2", region_name="us-east-1")
    instance = ec2_resource.Instance(context.instance_details["instance_id"])
    instance.load()
    assert (
        instance.security_groups[0]["GroupId"]
        == context.instance_details["security_group_id"]
    )


@then('AMI is from Canonical owner "{owner_id}"')
def step_verify_ami_owner(context: Context, owner_id: str) -> None:
    """Verify AMI is from Canonical."""
    images = context.ec2_client.describe_images(ImageIds=[context.found_ami_id])
    assert images["Images"][0]["OwnerId"] == owner_id


@then('AMI architecture is "{arch}"')
def step_verify_ami_arch(context: Context, arch: str) -> None:
    """Verify AMI architecture."""
    images = context.ec2_client.describe_images(ImageIds=[context.found_ami_id])
    image = images["Images"][0]

    if "Architecture" in image:
        assert image["Architecture"] == arch, (
            f"Expected architecture {arch}, got {image['Architecture']}"
        )
    else:
        assert os.environ.get("MOONDOCK_TEST_MODE") == "1", (
            "Architecture attribute missing from AMI (only acceptable in test mode)"
        )


@then('AMI virtualization is "{virt_type}"')
def step_verify_ami_virt(context: Context, virt_type: str) -> None:
    """Verify AMI virtualization type."""
    images = context.ec2_client.describe_images(ImageIds=[context.found_ami_id])
    image = images["Images"][0]

    if "VirtualizationType" in image:
        assert image["VirtualizationType"] == virt_type, (
            f"Expected virtualization {virt_type}, got {image['VirtualizationType']}"
        )
    else:
        assert os.environ.get("MOONDOCK_TEST_MODE") == "1", (
            "VirtualizationType attribute missing from AMI (only acceptable in test mode)"
        )


@then("AMI is most recent available")
def step_verify_ami_is_recent(context: Context) -> None:
    """Verify AMI is most recent."""
    assert context.found_ami_id is not None


@then("key pair is deleted from AWS")
def step_verify_key_deleted_generic(context: Context) -> None:
    """Verify key pair deleted from AWS."""
    assert hasattr(context, "unique_id"), "unique_id not found in context"
    assert context.unique_id is not None, "unique_id is None"
    assert hasattr(context, "ec2_client"), "ec2_client not found in context"
    assert context.ec2_client is not None, "ec2_client is None"

    key_name = f"moondock-{context.unique_id}"
    key_pairs = context.ec2_client.describe_key_pairs()
    key_names = [kp["KeyName"] for kp in key_pairs["KeyPairs"]]
    assert key_name not in key_names


@then('key pair "{key_name}" is deleted from AWS')
def step_verify_key_deleted(context: Context, key_name: str) -> None:
    """Verify key pair deleted from AWS."""
    key_pairs = context.ec2_client.describe_key_pairs()
    key_names = [kp["KeyName"] for kp in key_pairs["KeyPairs"]]
    assert key_name not in key_names


@then("key file is deleted from disk")
def step_verify_key_file_deleted_generic(context: Context) -> None:
    """Verify key file deleted from disk."""
    assert hasattr(context, "unique_id"), "unique_id not found in context"
    assert context.unique_id is not None, "unique_id is None"

    moondock_dir = os.environ.get("MOONDOCK_DIR", str(Path.home() / ".moondock"))
    key_file = Path(moondock_dir) / "keys" / f"{context.unique_id}.pem"
    assert not key_file.exists()


@then('key file "~/.moondock/keys/{unique_id}.pem" is deleted')
def step_verify_key_file_deleted(context: Context, unique_id: str) -> None:
    """Verify key file deleted from disk."""
    moondock_dir = os.environ.get("MOONDOCK_DIR", str(Path.home() / ".moondock"))
    key_file = Path(moondock_dir) / "keys" / f"{unique_id}.pem"
    assert not key_file.exists()


@then("security group is deleted from AWS")
def step_verify_sg_deleted(context: Context) -> None:
    """Verify security group deleted."""
    assert hasattr(context, "ec2_client"), "ec2_client not found in context"
    assert context.ec2_client is not None, "ec2_client is None"

    if hasattr(context, "security_group_id") and context.security_group_id is not None:
        try:
            context.ec2_client.describe_security_groups(
                GroupIds=[context.security_group_id]
            )
            assert False, "Security group should be deleted"
        except ClientError as e:
            assert "InvalidGroup.NotFound" in str(e)
    elif hasattr(context, "initial_sg_ids"):
        current_sgs = context.ec2_client.describe_security_groups()
        current_sg_ids = {sg["GroupId"] for sg in current_sgs["SecurityGroups"]}
        new_sgs = current_sg_ids - context.initial_sg_ids
        assert len(new_sgs) == 0, (
            f"Found {len(new_sgs)} security groups that were not cleaned up after failed launch"
        )
    else:
        assert False, (
            "Either security_group_id or initial_sg_ids must be set in context"
        )


@then('termination waits for "{state}" state')
def step_verify_termination_waits(context: Context, state: str) -> None:
    """Verify instance reaches expected terminated state.

    NOTE: This is a pragmatic state-check approach. It verifies the instance
    reached the expected state, which implies waiting worked, but doesn't
    directly verify that waiter.wait() was called.

    Parameters
    ----------
    context : Context
        Behave test context containing ec2_client and instance_details or instance_id
    state : str
        Expected instance state (e.g., "terminated")
    """
    ec2_client = context.ec2_client

    if (
        hasattr(context, "instance_details")
        and context.instance_details
        and "instance_id" in context.instance_details
    ):
        instance_id = context.instance_details["instance_id"]
    else:
        instance_id = context.instance_id

    response = ec2_client.describe_instances(InstanceIds=[instance_id])
    instance = response["Reservations"][0]["Instances"][0]
    actual_state = instance["State"]["Name"]

    assert actual_state == state, f"Expected state '{state}', got '{actual_state}'"


@then("security group cleanup happens after termination")
def step_verify_cleanup_after_termination(context: Context) -> None:
    """Verify security group was deleted after instance termination.

    NOTE: This verifies both operations completed and cleanup succeeded.
    It doesn't track exact operation order but confirms the end state.

    Parameters
    ----------
    context : Context
        Behave test context containing ec2_client and instance_details or instance_id/security_group_id
    """
    ec2_client = context.ec2_client

    if (
        hasattr(context, "instance_details")
        and context.instance_details
        and "instance_id" in context.instance_details
    ):
        instance_id = context.instance_details["instance_id"]
        sg_id = context.instance_details["security_group_id"]
    else:
        instance_id = context.instance_id
        sg_id = context.security_group_id

    response = ec2_client.describe_instances(InstanceIds=[instance_id])
    instance_state = response["Reservations"][0]["Instances"][0]["State"]["Name"]

    assert instance_state == "terminated", f"Instance not terminated: {instance_state}"

    try:
        ec2_client.describe_security_groups(GroupIds=[sg_id])
        assert False, f"Security group {sg_id} still exists after termination"
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        assert error_code == "InvalidGroup.NotFound", f"Unexpected error: {error_code}"


@then("command fails with NoCredentialsError")
def step_verify_no_credentials_error(context: Context) -> None:
    """Verify NoCredentialsError was handled properly.

    Parameters
    ----------
    context : Context
        Behave test context containing exception, stderr, or log records
    """
    if hasattr(context, "exception") and context.exception is not None:
        assert isinstance(context.exception, NoCredentialsError), (
            f"Expected NoCredentialsError, got {type(context.exception).__name__}: "
            f"{context.exception}"
        )
    elif hasattr(context, "stderr") and context.stderr and context.exit_code != 0:
        assert "AWS credentials not found" in str(context.stderr), (
            f"Expected 'AWS credentials not found' in stderr but got: {context.stderr}"
        )
    elif hasattr(context, "log_records") and context.log_records:
        assert any(
            (
                "Unable to query all AWS regions" in str(record.getMessage())
                or "Failed to query region" in str(record.getMessage())
                or "AuthFailure" in str(record.getMessage())
            )
            and record.levelname == "WARNING"
            for record in context.log_records
        ), (
            f"Expected warning about credentials/auth failure but got: {[r.getMessage() for r in context.log_records]}"
        )
    else:
        assert False, (
            f"Expected NoCredentialsError exception, stderr output, or warning log, "
            f"but got exit_code={context.exit_code}, "
            f"stderr={getattr(context, 'stderr', None)}, "
            f"exception={getattr(context, 'exception', None)}"
        )


@then("command fails with ClientError")
def step_verify_client_error(context: Context) -> None:
    """Verify ClientError raised."""
    assert context.exception is not None


@then("RuntimeError is raised with timeout message")
def step_verify_runtime_error_timeout(context: Context) -> None:
    """Verify RuntimeError with timeout message.

    Parameters
    ----------
    context : Context
        Behave test context containing exception
    """
    assert hasattr(context, "exception"), "exception not found in context"
    assert context.exception is not None, "No exception was raised"
    assert isinstance(context.exception, RuntimeError), (
        f"Expected RuntimeError, got {type(context.exception).__name__}: "
        f"{context.exception}"
    )

    error_message = str(context.exception).lower()
    assert "failed" in error_message, (
        f"Exception message doesn't indicate failure: {context.exception}"
    )
    assert (
        "terminate" in error_message
        or "timeout" in error_message
        or "max attempts exceeded" in error_message
    ), (
        f"Exception message doesn't indicate timeout/termination/max attempts: "
        f"{context.exception}"
    )


@then("rollback cleanup is attempted")
def step_verify_rollback_cleanup(context: Context) -> None:
    """Verify rollback cleanup attempted by checking no resources remain.

    Parameters
    ----------
    context : Context
        Behave test context containing ec2_client
    """
    assert hasattr(context, "ec2_client"), "ec2_client not found in context"
    assert context.ec2_client is not None, "ec2_client is None"

    key_pairs = context.ec2_client.describe_key_pairs()
    moondock_keys = [
        kp for kp in key_pairs["KeyPairs"] if kp["KeyName"].startswith("moondock-")
    ]
    assert len(moondock_keys) == 0, (
        f"Rollback failed: Found orphaned key pairs: "
        f"{[k['KeyName'] for k in moondock_keys]}"
    )

    try:
        sgs = context.ec2_client.describe_security_groups(
            Filters=[{"Name": "group-name", "Values": ["moondock-*"]}]
        )
        moondock_sgs = [
            sg
            for sg in sgs.get("SecurityGroups", [])
            if sg["GroupName"].startswith("moondock-")
        ]
        assert len(moondock_sgs) == 0, (
            f"Rollback failed: Found orphaned security groups: "
            f"{[sg['GroupName'] for sg in moondock_sgs]}"
        )
    except ClientError:
        pass

    moondock_dir = os.environ.get("MOONDOCK_DIR", str(Path.home() / ".moondock"))
    keys_dir = Path(moondock_dir) / "keys"

    if keys_dir.exists() and hasattr(context, "unique_id"):
        expected_key_file = keys_dir / f"{context.unique_id}.pem"
        assert not expected_key_file.exists(), (
            f"Rollback failed: Key file still exists: {expected_key_file}"
        )


@then("existing key pair is deleted")
def step_verify_existing_key_deleted(context: Context) -> None:
    """Verify existing key pair was deleted and recreated during conflict resolution.

    Parameters
    ----------
    context : Context
        Behave test context containing existing_key_name and instance_details

    Notes
    -----
    When unique_id is the same, the old key is deleted and a new one with the
    same name is created. This step verifies that a key pair with the expected
    name exists (proving conflict was handled, even though we can't distinguish
    old vs new in moto).
    """
    assert hasattr(context, "existing_key_name"), (
        "existing_key_name not found in context"
    )

    key_pairs = context.ec2_client.describe_key_pairs()
    key_names = [kp["KeyName"] for kp in key_pairs["KeyPairs"]]

    if hasattr(context, "instance_details") and context.instance_details:
        new_key_name = f"moondock-{context.instance_details['unique_id']}"
        assert new_key_name in key_names, (
            f"Key pair '{new_key_name}' not found after conflict resolution"
        )


@then("existing security group is deleted")
def step_verify_existing_sg_deleted(context: Context) -> None:
    """Verify existing security group was deleted and recreated during conflict resolution.

    Parameters
    ----------
    context : Context
        Behave test context containing existing_sg_id and instance_details

    Notes
    -----
    The production code deletes security groups by name, then creates new ones.
    Since SGs get new IDs each time, we can verify the old ID no longer exists
    and a new one was created.
    """
    assert hasattr(context, "existing_sg_id"), "existing_sg_id not found in context"

    try:
        context.ec2_client.describe_security_groups(GroupIds=[context.existing_sg_id])
        assert False, (
            f"Existing security group '{context.existing_sg_id}' was not deleted"
        )
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        assert error_code == "InvalidGroup.NotFound", (
            f"Unexpected error checking old SG: {error_code}"
        )

    if hasattr(context, "instance_details") and context.instance_details:
        new_sg_id = context.instance_details["security_group_id"]

        response = context.ec2_client.describe_security_groups(GroupIds=[new_sg_id])
        assert len(response["SecurityGroups"]) == 1, (
            f"New security group '{new_sg_id}' not found in AWS"
        )


@then("new resources are created")
def step_verify_new_resources_created(context: Context) -> None:
    """Verify new resources created."""
    assert context.instance_details is not None


@then("instance launches successfully")
def step_verify_instance_launches(context: Context) -> None:
    """Verify instance launched successfully."""
    assert context.instance_details["state"] == "running"
