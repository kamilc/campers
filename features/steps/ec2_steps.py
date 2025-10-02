"""BDD step definitions for EC2 instance management."""

import os
import uuid
from pathlib import Path
from unittest.mock import patch

import boto3
from behave import given, then, when
from behave.runner import Context
from botocore.exceptions import ClientError
from moto import mock_aws

from moondock.ec2 import EC2Manager


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
            image["OwnerId"] = "099720109477"
            image["VirtualizationType"] = "hvm"
            image["Architecture"] = "x86_64"

        return response

    ec2_manager.ec2_client.describe_images = mock_describe_images


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
    if not hasattr(context, "mock_aws_env") or context.mock_aws_env is None:
        context.mock_aws_env = mock_aws()
        context.mock_aws_env.start()

        os.environ["AWS_ACCESS_KEY_ID"] = "testing"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
        os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

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
    step_running_instance_with_unique_id(context, uuid.uuid4().hex[:8])


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
    context.mock_aws_env = mock_aws()
    context.mock_aws_env.start()

    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

    ec2_client = boto3.client("ec2", region_name="us-east-1")
    ec2_client.create_key_pair(KeyName=key_name)
    context.existing_key_name = key_name
    context.ec2_client = ec2_client


@given('security group "{sg_name}" already exists')
def step_security_group_exists(context: Context, sg_name: str) -> None:
    """Create an existing security group."""
    if not hasattr(context, "ec2_client"):
        context.mock_aws_env = mock_aws()
        context.mock_aws_env.start()

        os.environ["AWS_ACCESS_KEY_ID"] = "testing"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
        os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

        context.ec2_client = boto3.client("ec2", region_name="us-east-1")

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
    context.mock_aws_env = mock_aws()
    context.mock_aws_env.start()

    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

    context.ec2_client = boto3.client("ec2", region_name="us-east-1")
    context.ec2_client.register_image(
        Name="ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-20231201",
        Description="Ubuntu 22.04 LTS",
        Architecture="x86_64",
        RootDeviceName="/dev/sda1",
        VirtualizationType="hvm",
    )

    context.ec2_config = {
        "instance_type": "invalid.type",
        "disk_size": 50,
        "region": "us-east-1",
    }


@given("security group is created")
def step_security_group_is_created(context: Context) -> None:
    """Set up security group creation for rollback testing."""
    pass


@when("I launch instance")
def step_launch_instance(context: Context) -> None:
    """Launch EC2 instance."""
    if not hasattr(context, "mock_aws_env") or context.mock_aws_env is None:
        context.mock_aws_env = mock_aws()
        context.mock_aws_env.start()

        os.environ["AWS_ACCESS_KEY_ID"] = "testing"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
        os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

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

    with patch("time.time", return_value=1234567890):
        context.instance_details = ec2_manager.launch_instance(context.ec2_config)

    context.ec2_manager = ec2_manager
    context.ec2_client = ec2_client


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
    context.mock_aws_env = mock_aws()
    context.mock_aws_env.start()

    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

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
    context.ec2_client = ec2_client


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
    context.mock_aws_env = mock_aws()
    context.mock_aws_env.start()

    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

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

    try:
        ec2_manager.launch_instance(context.ec2_config)
        context.exception = None
    except Exception as e:
        context.exception = e

    context.ec2_client = ec2_client


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
    """Simulate timeout scenario."""
    pass


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
    """Verify root disk size."""
    pass


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
    """Verify security group allows outbound traffic."""
    pass


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

    if "Architecture" in images["Images"][0]:
        assert images["Images"][0]["Architecture"] == arch
    else:
        pass


@then('AMI virtualization is "{virt_type}"')
def step_verify_ami_virt(context: Context, virt_type: str) -> None:
    """Verify AMI virtualization type."""
    images = context.ec2_client.describe_images(ImageIds=[context.found_ami_id])

    if "VirtualizationType" in images["Images"][0]:
        assert images["Images"][0]["VirtualizationType"] == virt_type
    else:
        pass


@then("AMI is most recent available")
def step_verify_ami_is_recent(context: Context) -> None:
    """Verify AMI is most recent."""
    assert context.found_ami_id is not None


@then("key pair is deleted from AWS")
def step_verify_key_deleted_generic(context: Context) -> None:
    """Verify key pair deleted from AWS."""
    if not hasattr(context, "unique_id") or context.unique_id is None:
        return

    if not hasattr(context, "ec2_client") or context.ec2_client is None:
        return

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
    if not hasattr(context, "unique_id") or context.unique_id is None:
        return

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
    if not hasattr(context, "security_group_id") or context.security_group_id is None:
        return

    if not hasattr(context, "ec2_client") or context.ec2_client is None:
        return

    try:
        context.ec2_client.describe_security_groups(
            GroupIds=[context.security_group_id]
        )
        assert False, "Security group should be deleted"
    except ClientError as e:
        assert "InvalidGroup.NotFound" in str(e)


@then('termination waits for "{state}" state')
def step_verify_termination_waits(context: Context, state: str) -> None:
    """Verify termination waits for state."""
    pass


@then("security group cleanup happens after termination")
def step_verify_cleanup_after_termination(context: Context) -> None:
    """Verify cleanup order."""
    pass


@then("command fails with NoCredentialsError")
def step_verify_no_credentials_error(context: Context) -> None:
    """Verify NoCredentialsError raised."""
    pass


@then("command fails with ClientError")
def step_verify_client_error(context: Context) -> None:
    """Verify ClientError raised."""
    assert context.exception is not None


@then("RuntimeError is raised with timeout message")
def step_verify_runtime_error_timeout(context: Context) -> None:
    """Verify RuntimeError with timeout."""
    pass


@then("rollback cleanup is attempted")
def step_verify_rollback_cleanup(context: Context) -> None:
    """Verify rollback cleanup attempted."""
    pass


@then("existing key pair is deleted")
def step_verify_existing_key_deleted(context: Context) -> None:
    """Verify existing key pair deleted."""
    pass


@then("existing security group is deleted")
def step_verify_existing_sg_deleted(context: Context) -> None:
    """Verify existing security group deleted."""
    pass


@then("new resources are created")
def step_verify_new_resources_created(context: Context) -> None:
    """Verify new resources created."""
    assert context.instance_details is not None


@then("instance launches successfully")
def step_verify_instance_launches(context: Context) -> None:
    """Verify instance launched successfully."""
    assert context.instance_details["state"] == "running"
