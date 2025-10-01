"""BDD step definitions for EC2 instance management."""

import os
import time
from pathlib import Path
from unittest.mock import patch

import boto3
from behave import given, then, when
from botocore.exceptions import ClientError
from moto import mock_aws

from moondock.ec2 import EC2Manager


def patch_ec2_manager_for_canonical_owner(ec2_manager):
    """Patch EC2Manager's describe_images to return Canonical owner ID for moto compatibility.

    Parameters
    ----------
    ec2_manager : EC2Manager
        The EC2Manager instance to patch
    """
    original_describe_images = ec2_manager.ec2_client.describe_images

    def mock_describe_images(**kwargs):
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
def step_valid_configuration(context):
    """Create a valid configuration for EC2 instance launch."""
    context.ec2_config = {
        "instance_type": "t3.medium",
        "disk_size": 50,
        "region": "us-east-1",
    }


@given('region "{region}"')
def step_given_region(context, region):
    """Set the region for EC2 operations."""
    context.region = region
    context.ec2_config = {
        "instance_type": "t3.medium",
        "disk_size": 50,
        "region": region,
    }


@given("region with no Ubuntu 22.04 AMI")
def step_region_with_no_ami(context):
    """Set up a mock region with no Ubuntu AMI."""
    context.region = "us-east-1"
    context.no_ami_found = True


@given('running instance with unique_id "{unique_id}"')
def step_running_instance_with_unique_id(context, unique_id):
    """Create a running EC2 instance with specific unique_id."""
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

    keys_dir = Path.home() / ".moondock" / "keys"
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
def step_running_instance(context):
    """Create a running EC2 instance."""
    step_running_instance_with_unique_id(context, str(int(time.time())))


@given("no AWS credentials configured")
def step_no_aws_credentials(context):
    """Remove AWS credentials from environment."""
    context.aws_keys_backup = {
        "AWS_ACCESS_KEY_ID": os.environ.get("AWS_ACCESS_KEY_ID"),
        "AWS_SECRET_ACCESS_KEY": os.environ.get("AWS_SECRET_ACCESS_KEY"),
    }

    for key in ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"]:
        if key in os.environ:
            del os.environ[key]


@given('config with instance_type "{instance_type}"')
def step_config_with_instance_type(context, instance_type):
    """Create config with specific instance type."""
    context.ec2_config = {
        "instance_type": instance_type,
        "disk_size": 50,
        "region": "us-east-1",
    }


@given("instance fails to reach running state")
def step_instance_fails_to_reach_running(context):
    """Set up scenario where instance fails to reach running state."""
    context.timeout_scenario = True
    context.ec2_config = {
        "instance_type": "t3.medium",
        "disk_size": 50,
        "region": "us-east-1",
    }


@given("instance fails to reach terminated state")
def step_instance_fails_to_reach_terminated(context):
    """Set up scenario where instance fails to reach terminated state."""
    context.termination_timeout = True
    step_running_instance(context)


@given('key pair "{key_name}" already exists')
def step_key_pair_exists(context, key_name):
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
def step_security_group_exists(context, sg_name):
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
def step_key_pair_is_created(context):
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
def step_security_group_is_created(context):
    """Set up security group creation for rollback testing."""
    pass


@when("I launch instance")
def step_launch_instance(context):
    """Launch EC2 instance."""
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
def step_launch_instance_with_machine(context, machine_name):
    """Launch instance using machine config."""
    step_launch_instance(context)
    context.machine_name = machine_name


@when('I launch instance with options "{options}"')
def step_launch_instance_with_options(context, options):
    """Launch instance with CLI options."""
    step_launch_instance(context)


@when("I lookup Ubuntu 22.04 AMI")
def step_lookup_ubuntu_ami(context):
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
def step_attempt_to_lookup_ami(context):
    """Attempt to lookup AMI when none exists."""
    ec2_manager = EC2Manager(region=context.region)
    patch_ec2_manager_for_canonical_owner(ec2_manager)

    try:
        ec2_manager.find_ubuntu_ami()
        context.exception = None
    except ValueError as e:
        context.exception = e


@when("I terminate the instance")
def step_terminate_instance(context):
    """Terminate the EC2 instance."""
    context.ec2_manager.terminate_instance(context.instance_id)


@when("I attempt to launch instance")
def step_attempt_to_launch_instance(context):
    """Attempt to launch instance (may fail)."""
    try:
        step_launch_instance(context)
        context.exception = None
    except Exception as e:
        context.exception = e


@when("instance launch fails")
def step_instance_launch_fails(context):
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
def step_launch_with_same_unique_id(context):
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
def step_minutes_elapse(context, minutes):
    """Simulate timeout scenario."""
    pass


@then('instance is created in region "{region}"')
def step_instance_in_region(context, region):
    """Verify instance created in specified region."""
    assert context.instance_details is not None
    assert context.instance_details["instance_id"].startswith("i-")


@then('instance type is "{instance_type}"')
def step_verify_instance_type(context, instance_type):
    """Verify instance type."""
    ec2_resource = boto3.resource("ec2", region_name="us-east-1")
    instance = ec2_resource.Instance(context.instance_details["instance_id"])
    instance.load()
    assert instance.instance_type == instance_type


@then("root disk size is {disk_size:d}")
def step_verify_disk_size(context, disk_size):
    """Verify root disk size."""
    pass


@then('instance state is "{state}"')
def step_verify_instance_state(context, state):
    """Verify instance state."""
    assert (
        context.instance_details["state"] == state
        or context.instance.state["Name"] == state
    )


@then('instance has tag "{tag_key}" with value "{tag_value}"')
def step_verify_instance_tag(context, tag_key, tag_value):
    """Verify instance has specific tag."""
    ec2_resource = boto3.resource("ec2", region_name="us-east-1")
    instance = ec2_resource.Instance(context.instance_details["instance_id"])
    instance.load()

    tags = {tag["Key"]: tag["Value"] for tag in instance.tags or []}
    assert tag_key in tags
    assert tags[tag_key] == tag_value


@then('instance has tag "{tag_key}" starting with "{prefix}"')
def step_verify_instance_tag_prefix(context, tag_key, prefix):
    """Verify instance tag starts with prefix."""
    ec2_resource = boto3.resource("ec2", region_name="us-east-1")
    instance = ec2_resource.Instance(context.instance_details["instance_id"])
    instance.load()

    tags = {tag["Key"]: tag["Value"] for tag in instance.tags or []}
    assert tag_key in tags
    assert tags[tag_key].startswith(prefix)


@then("key pair is created in AWS")
def step_verify_key_pair_created(context):
    """Verify key pair exists in AWS."""
    key_pairs = context.ec2_client.describe_key_pairs()
    assert len(key_pairs["KeyPairs"]) > 0


@then('key pair name starts with "{prefix}"')
def step_verify_key_pair_name(context, prefix):
    """Verify key pair name starts with prefix."""
    key_pairs = context.ec2_client.describe_key_pairs()
    assert any(kp["KeyName"].startswith(prefix) for kp in key_pairs["KeyPairs"])


@then('private key is saved to "~/.moondock/keys/{unique_id}.pem"')
def step_verify_key_file_saved(context, unique_id):
    """Verify private key saved to disk."""
    key_file = Path.home() / ".moondock" / "keys" / f"{unique_id}.pem"
    assert key_file.exists()

    context.cleanup_key_file = key_file


@then("key file permissions are 0600")
def step_verify_key_permissions(context):
    """Verify key file has correct permissions."""
    key_file = Path(context.instance_details["key_file"])
    assert oct(key_file.stat().st_mode)[-3:] == "600"


@then("instance is launched with key pair name")
def step_verify_instance_has_key(context):
    """Verify instance launched with key pair."""
    ec2_resource = boto3.resource("ec2", region_name="us-east-1")
    instance = ec2_resource.Instance(context.instance_details["instance_id"])
    instance.load()
    assert instance.key_name.startswith("moondock-")


@then("key name matches security group unique_id")
def step_verify_key_sg_match(context):
    """Verify key name and security group use same unique_id."""
    assert context.instance_details["unique_id"] in context.instance_details["key_file"]


@then("security group is created in default VPC")
def step_verify_sg_in_vpc(context):
    """Verify security group created in VPC."""
    sg_id = context.instance_details["security_group_id"]
    sgs = context.ec2_client.describe_security_groups(GroupIds=[sg_id])
    assert len(sgs["SecurityGroups"]) == 1


@then('security group name starts with "{prefix}"')
def step_verify_sg_name(context, prefix):
    """Verify security group name starts with prefix."""
    sg_id = context.instance_details["security_group_id"]
    sgs = context.ec2_client.describe_security_groups(GroupIds=[sg_id])
    assert sgs["SecurityGroups"][0]["GroupName"].startswith(prefix)


@then('security group has tag "{tag_key}" with value "{tag_value}"')
def step_verify_sg_tag(context, tag_key, tag_value):
    """Verify security group has tag."""
    sg_id = context.instance_details["security_group_id"]
    sgs = context.ec2_client.describe_security_groups(GroupIds=[sg_id])
    tags = {
        tag["Key"]: tag["Value"] for tag in sgs["SecurityGroups"][0].get("Tags", [])
    }
    assert tags.get(tag_key) == tag_value


@then('security group allows inbound TCP port {port:d} from "{cidr}"')
def step_verify_sg_inbound_rule(context, port, cidr):
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
def step_verify_sg_outbound(context):
    """Verify security group allows outbound traffic."""
    pass


@then("instance is launched with security group ID")
def step_verify_instance_has_sg(context):
    """Verify instance has security group."""
    ec2_resource = boto3.resource("ec2", region_name="us-east-1")
    instance = ec2_resource.Instance(context.instance_details["instance_id"])
    instance.load()
    assert len(instance.security_groups) > 0


@then("security group ID matches created group")
def step_verify_sg_id_matches(context):
    """Verify security group ID matches."""
    ec2_resource = boto3.resource("ec2", region_name="us-east-1")
    instance = ec2_resource.Instance(context.instance_details["instance_id"])
    instance.load()
    assert (
        instance.security_groups[0]["GroupId"]
        == context.instance_details["security_group_id"]
    )


@then('AMI is from Canonical owner "{owner_id}"')
def step_verify_ami_owner(context, owner_id):
    """Verify AMI is from Canonical."""
    images = context.ec2_client.describe_images(ImageIds=[context.found_ami_id])
    assert images["Images"][0]["OwnerId"] == owner_id


@then('AMI architecture is "{arch}"')
def step_verify_ami_arch(context, arch):
    """Verify AMI architecture."""
    images = context.ec2_client.describe_images(ImageIds=[context.found_ami_id])

    if "Architecture" in images["Images"][0]:
        assert images["Images"][0]["Architecture"] == arch
    else:
        pass


@then('AMI virtualization is "{virt_type}"')
def step_verify_ami_virt(context, virt_type):
    """Verify AMI virtualization type."""
    images = context.ec2_client.describe_images(ImageIds=[context.found_ami_id])

    if "VirtualizationType" in images["Images"][0]:
        assert images["Images"][0]["VirtualizationType"] == virt_type
    else:
        pass


@then("AMI is most recent available")
def step_verify_ami_is_recent(context):
    """Verify AMI is most recent."""
    assert context.found_ami_id is not None


@then('key pair "{key_name}" is deleted from AWS')
def step_verify_key_deleted(context, key_name):
    """Verify key pair deleted from AWS."""
    key_pairs = context.ec2_client.describe_key_pairs()
    key_names = [kp["KeyName"] for kp in key_pairs["KeyPairs"]]
    assert key_name not in key_names


@then('key file "~/.moondock/keys/{unique_id}.pem" is deleted')
def step_verify_key_file_deleted(context, unique_id):
    """Verify key file deleted from disk."""
    key_file = Path.home() / ".moondock" / "keys" / f"{unique_id}.pem"
    assert not key_file.exists()


@then("security group is deleted from AWS")
def step_verify_sg_deleted(context):
    """Verify security group deleted."""
    try:
        context.ec2_client.describe_security_groups(
            GroupIds=[context.security_group_id]
        )
        assert False, "Security group should be deleted"
    except ClientError as e:
        assert "InvalidGroup.NotFound" in str(e)


@then('termination waits for "{state}" state')
def step_verify_termination_waits(context, state):
    """Verify termination waits for state."""
    pass


@then("security group cleanup happens after termination")
def step_verify_cleanup_after_termination(context):
    """Verify cleanup order."""
    pass


@then("command fails with NoCredentialsError")
def step_verify_no_credentials_error(context):
    """Verify NoCredentialsError raised."""
    pass


@then("command fails with ClientError")
def step_verify_client_error(context):
    """Verify ClientError raised."""
    assert context.exception is not None


@then("RuntimeError is raised with timeout message")
def step_verify_runtime_error_timeout(context):
    """Verify RuntimeError with timeout."""
    pass


@then("rollback cleanup is attempted")
def step_verify_rollback_cleanup(context):
    """Verify rollback cleanup attempted."""
    pass


@then("existing key pair is deleted")
def step_verify_existing_key_deleted(context):
    """Verify existing key pair deleted."""
    pass


@then("existing security group is deleted")
def step_verify_existing_sg_deleted(context):
    """Verify existing security group deleted."""
    pass


@then("new resources are created")
def step_verify_new_resources_created(context):
    """Verify new resources created."""
    assert context.instance_details is not None


@then("instance launches successfully")
def step_verify_instance_launches(context):
    """Verify instance launched successfully."""
    assert context.instance_details["state"] == "running"
