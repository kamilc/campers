import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from moondock.ec2 import EC2Manager


@pytest.fixture(scope="function")
def ec2_manager(aws_credentials):
    """Return a mocked EC2Manager with patched describe_images for Canonical owner ID."""
    with mock_aws():
        manager = EC2Manager(region="us-east-1")

        original_describe_images = manager.ec2_client.describe_images

        def mock_describe_images(**kwargs):
            modified_kwargs = kwargs.copy()

            if (
                "Owners" in modified_kwargs
                and "099720109477" in modified_kwargs["Owners"]
            ):
                del modified_kwargs["Owners"]

            if "Filters" in modified_kwargs:
                modified_kwargs["Filters"] = [
                    f
                    for f in modified_kwargs["Filters"]
                    if f["Name"] in ["name", "state"]
                ]

            response = original_describe_images(**modified_kwargs)

            for image in response.get("Images", []):
                image["OwnerId"] = "099720109477"
                image["VirtualizationType"] = "hvm"
                image["Architecture"] = "x86_64"

            return response

        manager.ec2_client.describe_images = mock_describe_images

        yield manager


@pytest.fixture(scope="function")
def mocked_aws(aws_credentials):
    """Mock all AWS interactions."""
    with mock_aws():
        yield


@pytest.fixture(scope="function")
def registered_ami(ec2_manager):
    """Register Ubuntu 22.04 AMI for testing.

    Parameters
    ----------
    ec2_manager : EC2Manager
        EC2Manager fixture

    Yields
    ------
    str
        AMI ID of registered image
    """
    ec2_client = ec2_manager.ec2_client
    ec2_client.register_image(
        Name="ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-20231201",
        Description="Ubuntu 22.04 LTS",
        Architecture="x86_64",
        RootDeviceName="/dev/sda1",
        VirtualizationType="hvm",
    )
    yield ec2_manager.find_ubuntu_ami()


@pytest.fixture
def cleanup_keys() -> list[Path]:
    """Clean up SSH key files after test."""
    keys_to_cleanup: list[Path] = []

    yield keys_to_cleanup

    for key_file in keys_to_cleanup:
        if Path(key_file).exists():
            Path(key_file).unlink()

    moondock_dir = os.environ.get("MOONDOCK_DIR", str(Path.home() / ".moondock"))
    keys_dir = Path(moondock_dir) / "keys"

    if keys_dir.exists() and not list(keys_dir.iterdir()):
        keys_dir.rmdir()
        parent_dir = keys_dir.parent

        if not list(parent_dir.iterdir()):
            parent_dir.rmdir()


def test_ec2_manager_initialization(ec2_manager):
    """Test EC2Manager can be initialized."""
    assert ec2_manager.region == "us-east-1"
    assert ec2_manager.ec2_client is not None
    assert ec2_manager.ec2_resource is not None


def test_find_ubuntu_ami(registered_ami):
    """Test finding Ubuntu 22.04 AMI."""
    assert registered_ami is not None
    assert registered_ami.startswith("ami-")


def test_find_ubuntu_ami_no_ami_found(ec2_manager):
    """Test error when no Ubuntu 22.04 AMI found."""
    with pytest.raises(ValueError, match="No Ubuntu 22.04 AMI found"):
        ec2_manager.find_ubuntu_ami()


def test_create_key_pair(ec2_manager, cleanup_keys):
    """Test SSH key pair creation."""
    unique_id = str(int(time.time()))

    key_name, key_file = ec2_manager.create_key_pair(unique_id)
    cleanup_keys.append(key_file)

    moondock_dir = os.environ.get("MOONDOCK_DIR", str(Path.home() / ".moondock"))
    expected_key_file = Path(moondock_dir) / "keys" / f"{unique_id}.pem"

    assert key_name == f"moondock-{unique_id}"
    assert key_file == expected_key_file
    assert key_file.exists()
    assert oct(key_file.stat().st_mode)[-3:] == "600"

    key_pairs = ec2_manager.ec2_client.describe_key_pairs()
    assert len(key_pairs["KeyPairs"]) == 1
    assert key_pairs["KeyPairs"][0]["KeyName"] == f"moondock-{unique_id}"


def test_create_key_pair_deletes_existing(ec2_manager, cleanup_keys):
    """Test key pair creation deletes existing key with same name."""
    unique_id = str(int(time.time()))

    ec2_manager.ec2_client.create_key_pair(KeyName=f"moondock-{unique_id}")

    key_name, key_file = ec2_manager.create_key_pair(unique_id)
    cleanup_keys.append(key_file)

    assert key_name == f"moondock-{unique_id}"

    key_pairs = ec2_manager.ec2_client.describe_key_pairs()
    assert len(key_pairs["KeyPairs"]) == 1


def test_create_security_group(ec2_manager):
    """Test security group creation with SSH access."""
    unique_id = str(int(time.time()))

    sg_id = ec2_manager.create_security_group(unique_id)

    assert sg_id is not None
    assert sg_id.startswith("sg-")

    sgs = ec2_manager.ec2_client.describe_security_groups(GroupIds=[sg_id])
    sg = sgs["SecurityGroups"][0]

    assert sg["GroupName"] == f"moondock-{unique_id}"
    assert sg["Description"] == f"Moondock security group {unique_id}"

    assert any(
        tag["Key"] == "ManagedBy" and tag["Value"] == "moondock"
        for tag in sg.get("Tags", [])
    )

    assert len(sg["IpPermissions"]) == 1
    perm = sg["IpPermissions"][0]
    assert perm["IpProtocol"] == "tcp"
    assert perm["FromPort"] == 22
    assert perm["ToPort"] == 22
    assert perm["IpRanges"][0]["CidrIp"] == "0.0.0.0/0"


def test_create_security_group_deletes_existing(ec2_manager):
    """Test security group creation deletes existing SG with same name."""
    unique_id = str(int(time.time()))

    vpcs = ec2_manager.ec2_client.describe_vpcs(
        Filters=[{"Name": "isDefault", "Values": ["true"]}]
    )
    vpc_id = vpcs["Vpcs"][0]["VpcId"]

    response = ec2_manager.ec2_client.create_security_group(
        GroupName=f"moondock-{unique_id}",
        Description="Old SG",
        VpcId=vpc_id,
    )
    old_sg_id = response["GroupId"]

    sg_id = ec2_manager.create_security_group(unique_id)

    assert sg_id != old_sg_id

    sgs = ec2_manager.ec2_client.describe_security_groups()
    sg_names = [sg["GroupName"] for sg in sgs["SecurityGroups"]]
    assert sg_names.count(f"moondock-{unique_id}") == 1


def test_launch_instance_success(ec2_manager, cleanup_keys, registered_ami):
    """Test successful EC2 instance launch."""
    config = {
        "instance_type": "t3.medium",
        "disk_size": 50,
        "region": "us-east-1",
        "machine_name": "jupyter-lab",
    }

    with patch("time.time", return_value=1234567890):
        result = ec2_manager.launch_instance(config)
        cleanup_keys.append(result["key_file"])

    moondock_dir = os.environ.get("MOONDOCK_DIR", str(Path.home() / ".moondock"))
    expected_key_file = str(Path(moondock_dir) / "keys" / "1234567890.pem")

    assert result["instance_id"].startswith("i-")
    assert result["state"] == "running"
    assert result["unique_id"] == "1234567890"
    assert result["key_file"] == expected_key_file
    assert result["security_group_id"].startswith("sg-")

    instance = ec2_manager.ec2_resource.Instance(result["instance_id"])
    instance.load()

    assert instance.instance_type == "t3.medium"

    tags = {tag["Key"]: tag["Value"] for tag in instance.tags}
    assert tags["ManagedBy"] == "moondock"
    assert tags["Name"] == "moondock-1234567890"
    assert tags["MachineConfig"] == "jupyter-lab"
    assert tags["UniqueId"] == "1234567890"

    assert instance.key_name == "moondock-1234567890"
    assert len(instance.security_groups) == 1


def test_launch_instance_ad_hoc(ec2_manager, cleanup_keys, registered_ami):
    """Test instance launch without machine name tags as ad-hoc."""
    config = {
        "instance_type": "t3.medium",
        "disk_size": 50,
        "region": "us-east-1",
    }

    result = ec2_manager.launch_instance(config)
    cleanup_keys.append(result["key_file"])

    instance = ec2_manager.ec2_resource.Instance(result["instance_id"])
    instance.load()

    tags = {tag["Key"]: tag["Value"] for tag in instance.tags}
    assert tags["MachineConfig"] == "ad-hoc"


def test_launch_instance_rollback_on_failure(ec2_manager, cleanup_keys):
    """Test rollback when instance launch fails."""
    ec2_client = ec2_manager.ec2_client

    config = {
        "instance_type": "t3.medium",
        "disk_size": 50,
        "region": "us-east-1",
    }

    with patch("time.time", return_value=1234567890):
        with pytest.raises(ValueError, match="No Ubuntu 22.04 AMI found"):
            ec2_manager.launch_instance(config)

    key_pairs = ec2_client.describe_key_pairs()
    assert len(key_pairs["KeyPairs"]) == 0

    moondock_dir = os.environ.get("MOONDOCK_DIR", str(Path.home() / ".moondock"))
    key_file = Path(moondock_dir) / "keys" / "1234567890.pem"
    assert not key_file.exists()


def test_terminate_instance(ec2_manager, cleanup_keys, registered_ami):
    """Test instance termination and cleanup."""
    ec2_client = ec2_manager.ec2_client
    config = {
        "instance_type": "t3.medium",
        "disk_size": 50,
        "region": "us-east-1",
    }

    with patch("time.time", return_value=1234567890):
        result = ec2_manager.launch_instance(config)

    instance_id = result["instance_id"]
    sg_id = result["security_group_id"]
    key_file = Path(result["key_file"])

    assert key_file.exists()

    ec2_manager.terminate_instance(instance_id)

    instance = ec2_manager.ec2_resource.Instance(instance_id)
    instance.load()
    assert instance.state["Name"] == "terminated"

    key_pairs = ec2_client.describe_key_pairs()
    assert len(key_pairs["KeyPairs"]) == 0

    assert not key_file.exists()

    with pytest.raises(ClientError):
        ec2_client.describe_security_groups(GroupIds=[sg_id])


def test_terminate_instance_without_unique_id_tag(ec2_manager, registered_ami):
    """Test termination handles missing UniqueId tag gracefully."""
    instances = ec2_manager.ec2_resource.create_instances(
        ImageId=registered_ami,
        InstanceType="t3.medium",
        MinCount=1,
        MaxCount=1,
    )
    instance = instances[0]
    instance_id = instance.id

    ec2_manager.terminate_instance(instance_id)

    instance.load()
    assert instance.state["Name"] == "terminated"


def test_list_instances_all_regions(ec2_manager, registered_ami) -> None:
    """Test listing instances across all regions."""
    from datetime import datetime

    ec2_resource = ec2_manager.ec2_resource

    instances = ec2_resource.create_instances(
        ImageId=registered_ami,
        InstanceType="t3.medium",
        MinCount=2,
        MaxCount=2,
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "ManagedBy", "Value": "moondock"},
                    {"Key": "MachineConfig", "Value": "test-machine"},
                ],
            }
        ],
    )

    for instance in instances:
        instance.wait_until_running()

    result = ec2_manager.list_instances()

    assert len(result) == 2
    assert all(inst["machine_config"] == "test-machine" for inst in result)
    assert all(inst["region"] == "us-east-1" for inst in result)
    assert all("launch_time" in inst for inst in result)
    assert all(isinstance(inst["launch_time"], datetime) for inst in result)


def test_list_instances_filtered_by_region(ec2_manager, registered_ami) -> None:
    """Test listing instances filtered by specific region."""
    ec2_resource = ec2_manager.ec2_resource

    instances = ec2_resource.create_instances(
        ImageId=registered_ami,
        InstanceType="t3.medium",
        MinCount=1,
        MaxCount=1,
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "ManagedBy", "Value": "moondock"},
                    {"Key": "MachineConfig", "Value": "filtered-machine"},
                ],
            }
        ],
    )

    for instance in instances:
        instance.wait_until_running()

    result = ec2_manager.list_instances(region_filter="us-east-1")

    assert len(result) == 1
    assert result[0]["machine_config"] == "filtered-machine"
    assert result[0]["region"] == "us-east-1"


def test_list_instances_empty_results(ec2_manager) -> None:
    """Test listing instances when none exist."""
    result = ec2_manager.list_instances()
    assert result == []


def test_list_instances_sorts_by_launch_time(ec2_manager, registered_ami) -> None:
    """Test that instances are sorted by launch time descending."""
    import time

    ec2_resource = ec2_manager.ec2_resource

    for i in range(3):
        instances = ec2_resource.create_instances(
            ImageId=registered_ami,
            InstanceType="t3.medium",
            MinCount=1,
            MaxCount=1,
            TagSpecifications=[
                {
                    "ResourceType": "instance",
                    "Tags": [
                        {"Key": "ManagedBy", "Value": "moondock"},
                        {"Key": "MachineConfig", "Value": f"machine-{i}"},
                    ],
                }
            ],
        )
        for instance in instances:
            instance.wait_until_running()
        time.sleep(1)

    result = ec2_manager.list_instances()

    assert len(result) == 3
    for i in range(len(result) - 1):
        assert result[i]["launch_time"] >= result[i + 1]["launch_time"]


def test_list_instances_handles_missing_tags(ec2_manager, registered_ami) -> None:
    """Test that instances with missing tags show default values."""
    ec2_resource = ec2_manager.ec2_resource

    instances = ec2_resource.create_instances(
        ImageId=registered_ami,
        InstanceType="t3.medium",
        MinCount=1,
        MaxCount=1,
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "ManagedBy", "Value": "moondock"},
                ],
            }
        ],
    )

    for instance in instances:
        instance.wait_until_running()

    result = ec2_manager.list_instances()

    assert len(result) == 1
    assert result[0]["machine_config"] == "ad-hoc"
    assert result[0]["name"] == "N/A"


def test_list_instances_no_credentials_error(ec2_manager) -> None:
    """Test that NoCredentialsError is raised when credentials missing."""
    from unittest.mock import MagicMock, patch

    from botocore.exceptions import NoCredentialsError

    def mock_boto3_client(*args, **kwargs):
        mock_client = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.side_effect = NoCredentialsError()
        mock_client.get_paginator.return_value = mock_paginator
        return mock_client

    with patch("boto3.client", side_effect=mock_boto3_client):
        with pytest.raises(NoCredentialsError):
            ec2_manager.list_instances(region_filter="us-east-1")


def test_list_instances_region_query_failure(ec2_manager) -> None:
    """Test that region query failure falls back to default region."""
    from unittest.mock import MagicMock, patch

    from botocore.exceptions import ClientError

    def mock_client_factory(*args, **kwargs):
        mock_client = MagicMock()
        if kwargs.get("region_name") == ec2_manager.region:
            mock_client.describe_regions.side_effect = ClientError(
                {
                    "Error": {
                        "Code": "RequestLimitExceeded",
                        "Message": "Too many requests",
                    }
                },
                "DescribeRegions",
            )
            mock_client.describe_instances.return_value = {"Reservations": []}
        return mock_client

    with patch("boto3.client", side_effect=mock_client_factory):
        result = ec2_manager.list_instances()
        assert isinstance(result, list)
