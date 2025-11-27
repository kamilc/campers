import os
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from campers.ec2 import EC2Manager


@pytest.fixture(scope="function")
def ec2_manager(aws_credentials):
    """Return mocked EC2Manager with patched describe_images for Canonical."""
    with mock_aws():
        manager = EC2Manager(region="us-east-1")

        original_describe_images = manager.ec2_client.describe_images

        def mock_describe_images(**kwargs):
            modified_kwargs = kwargs.copy()

            if "Owners" in modified_kwargs and (
                "099720109477" in modified_kwargs["Owners"]
                or "amazon" in modified_kwargs["Owners"]
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


@pytest.fixture
def registered_ami(ec2_manager):
    """Register an AMI for testing.

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
    response = ec2_client.register_image(
        Name="test-ami-image",
        Description="Test AMI",
        Architecture="x86_64",
        RootDeviceName="/dev/sda1",
        VirtualizationType="hvm",
    )
    yield response["ImageId"]


@pytest.fixture
def cleanup_keys() -> list[Path]:
    """Clean up SSH key files after test."""
    keys_to_cleanup: list[Path] = []

    yield keys_to_cleanup

    for key_file in keys_to_cleanup:
        if Path(key_file).exists():
            Path(key_file).unlink()

    campers_dir = os.environ.get("CAMPERS_DIR", str(Path.home() / ".campers"))
    keys_dir = Path(campers_dir) / "keys"

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


def test_create_key_pair(ec2_manager, cleanup_keys):
    """Test SSH key pair creation."""
    unique_id = str(int(time.time()))

    key_name, key_file = ec2_manager.create_key_pair(unique_id)
    cleanup_keys.append(key_file)

    campers_dir = os.environ.get("CAMPERS_DIR", str(Path.home() / ".campers"))
    expected_key_file = Path(campers_dir) / "keys" / f"{unique_id}.pem"

    assert key_name == f"campers-{unique_id}"
    assert key_file == expected_key_file
    assert key_file.exists()
    assert oct(key_file.stat().st_mode)[-3:] == "600"

    key_pairs = ec2_manager.ec2_client.describe_key_pairs()
    assert len(key_pairs["KeyPairs"]) == 1
    assert key_pairs["KeyPairs"][0]["KeyName"] == f"campers-{unique_id}"


def test_create_key_pair_deletes_existing(ec2_manager, cleanup_keys):
    """Test key pair creation deletes existing key with same name."""
    unique_id = str(int(time.time()))

    ec2_manager.ec2_client.create_key_pair(KeyName=f"campers-{unique_id}")

    key_name, key_file = ec2_manager.create_key_pair(unique_id)
    cleanup_keys.append(key_file)

    assert key_name == f"campers-{unique_id}"

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

    assert sg["GroupName"] == f"campers-{unique_id}"
    assert sg["Description"] == f"Campers security group {unique_id}"

    assert any(
        tag["Key"] == "ManagedBy" and tag["Value"] == "campers"
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
        GroupName=f"campers-{unique_id}",
        Description="Old SG",
        VpcId=vpc_id,
    )
    old_sg_id = response["GroupId"]

    sg_id = ec2_manager.create_security_group(unique_id)

    assert sg_id != old_sg_id

    sgs = ec2_manager.ec2_client.describe_security_groups()
    sg_names = [sg["GroupName"] for sg in sgs["SecurityGroups"]]
    assert sg_names.count(f"campers-{unique_id}") == 1


def test_launch_instance_success(ec2_manager, cleanup_keys, registered_ami):
    """Test successful EC2 instance launch."""
    config = {
        "instance_type": "t3.medium",
        "disk_size": 50,
        "region": "us-east-1",
        "camp_name": "jupyter-lab",
        "ami": {"image_id": registered_ami},
    }

    with patch("time.time", return_value=1234567890):
        result = ec2_manager.launch_instance(config)
        cleanup_keys.append(result["key_file"])

    campers_dir = os.environ.get("CAMPERS_DIR", str(Path.home() / ".campers"))
    expected_key_file = str(Path(campers_dir) / "keys" / "1234567890.pem")

    assert result["instance_id"].startswith("i-")
    assert result["state"] == "running"
    assert result["unique_id"] == "1234567890"
    assert result["key_file"] == expected_key_file
    assert result["security_group_id"].startswith("sg-")

    instance = ec2_manager.ec2_resource.Instance(result["instance_id"])
    instance.load()

    assert instance.instance_type == "t3.medium"

    tags = {tag["Key"]: tag["Value"] for tag in instance.tags}
    assert tags["ManagedBy"] == "campers"
    assert tags["Name"] == "campers-1234567890"
    assert tags["CampConfig"] == "jupyter-lab"
    assert tags["UniqueId"] == "1234567890"

    assert instance.key_name == "campers-1234567890"
    assert len(instance.security_groups) == 1


def test_launch_instance_ad_hoc(ec2_manager, cleanup_keys, registered_ami):
    """Test instance launch without machine name tags as ad-hoc."""
    config = {
        "instance_type": "t3.medium",
        "disk_size": 50,
        "region": "us-east-1",
        "ami": {"image_id": registered_ami},
    }

    result = ec2_manager.launch_instance(config)
    cleanup_keys.append(result["key_file"])

    instance = ec2_manager.ec2_resource.Instance(result["instance_id"])
    instance.load()

    tags = {tag["Key"]: tag["Value"] for tag in instance.tags}
    assert tags["CampConfig"] == "ad-hoc"


def test_launch_instance_rollback_on_failure(ec2_manager, cleanup_keys):
    """Test rollback when instance launch fails."""
    ec2_client = ec2_manager.ec2_client

    config = {
        "instance_type": "t3.medium",
        "disk_size": 50,
        "region": "us-east-1",
    }

    with patch("time.time", return_value=1234567890):
        with pytest.raises(ValueError, match="No AMI found"):
            ec2_manager.launch_instance(config)

    key_pairs = ec2_client.describe_key_pairs()
    assert len(key_pairs["KeyPairs"]) == 0

    campers_dir = os.environ.get("CAMPERS_DIR", str(Path.home() / ".campers"))
    key_file = Path(campers_dir) / "keys" / "1234567890.pem"
    assert not key_file.exists()


def test_terminate_instance(ec2_manager, cleanup_keys, registered_ami):
    """Test instance termination and cleanup."""
    ec2_client = ec2_manager.ec2_client
    config = {
        "instance_type": "t3.medium",
        "disk_size": 50,
        "region": "us-east-1",
        "ami": {"image_id": registered_ami},
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
                    {"Key": "ManagedBy", "Value": "campers"},
                    {"Key": "CampConfig", "Value": "test-machine"},
                ],
            }
        ],
    )

    for instance in instances:
        instance.wait_until_running()

    result = ec2_manager.list_instances()

    assert len(result) == 2
    assert all(inst["camp_config"] == "test-machine" for inst in result)
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
                    {"Key": "ManagedBy", "Value": "campers"},
                    {"Key": "CampConfig", "Value": "filtered-machine"},
                ],
            }
        ],
    )

    for instance in instances:
        instance.wait_until_running()

    result = ec2_manager.list_instances(region_filter="us-east-1")

    assert len(result) == 1
    assert result[0]["camp_config"] == "filtered-machine"
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
                        {"Key": "ManagedBy", "Value": "campers"},
                        {"Key": "CampConfig", "Value": f"machine-{i}"},
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
                    {"Key": "ManagedBy", "Value": "campers"},
                ],
            }
        ],
    )

    for instance in instances:
        instance.wait_until_running()

    result = ec2_manager.list_instances()

    assert len(result) == 1
    assert result[0]["camp_config"] == "ad-hoc"
    assert result[0]["name"] == "N/A"


def test_list_instances_no_credentials_error(ec2_manager) -> None:
    """Test that NoCredentialsError is raised when credentials missing."""
    from unittest.mock import MagicMock

    from botocore.exceptions import NoCredentialsError

    def mock_boto3_client(*args, **kwargs):
        mock_client = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.side_effect = NoCredentialsError()
        mock_client.get_paginator.return_value = mock_paginator
        return mock_client

    ec2_manager.boto3_client_factory = mock_boto3_client

    with pytest.raises(NoCredentialsError):
        ec2_manager.list_instances(region_filter="us-east-1")


def test_list_instances_region_query_failure(ec2_manager) -> None:
    """Test that region query failure falls back to default region."""
    from unittest.mock import MagicMock

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

    ec2_manager.boto3_client_factory = mock_client_factory
    result = ec2_manager.list_instances()
    assert isinstance(result, list)


def test_resolve_ami_direct_image_id(ec2_manager):
    """Test resolve_ami with direct image_id."""
    config = {"ami": {"image_id": "ami-0abc123def456"}}
    ami_id = ec2_manager.resolve_ami(config)
    assert ami_id == "ami-0abc123def456"


def test_resolve_ami_direct_image_id_invalid_format(ec2_manager):
    """Test resolve_ami with invalid AMI ID format."""
    config = {"ami": {"image_id": "invalid-ami-id"}}
    with pytest.raises(ValueError, match="Invalid AMI ID format"):
        ec2_manager.resolve_ami(config)


def test_resolve_ami_both_image_id_and_query(ec2_manager):
    """Test error when both image_id and query are specified."""
    config = {
        "ami": {
            "image_id": "ami-0abc123def456",
            "query": {
                "name": "ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"
            },
        }
    }
    with pytest.raises(ValueError, match="Cannot specify both"):
        ec2_manager.resolve_ami(config)


def test_resolve_ami_query_with_name_and_owner(ec2_manager):
    """Test resolve_ami with query using name and owner filters."""
    ec2_client = ec2_manager.ec2_client
    ec2_client.register_image(
        Name="ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-20231201",
        Description="Ubuntu 22.04 LTS",
        Architecture="x86_64",
        RootDeviceName="/dev/sda1",
        VirtualizationType="hvm",
    )
    ec2_client.register_image(
        Name="ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-20230801",
        Description="Ubuntu 22.04 LTS (older)",
        Architecture="x86_64",
        RootDeviceName="/dev/sda1",
        VirtualizationType="hvm",
    )

    config = {
        "ami": {
            "query": {
                "name": "ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*",
                "owner": "099720109477",
            }
        }
    }

    ami_id = ec2_manager.resolve_ami(config)
    assert ami_id.startswith("ami-")


def test_resolve_ami_query_with_architecture_filter(ec2_manager):
    """Test resolve_ami with query including architecture filter."""
    ec2_client = ec2_manager.ec2_client
    ec2_client.register_image(
        Name="test-ami-x86_64",
        Description="Test AMI x86_64",
        Architecture="x86_64",
        RootDeviceName="/dev/sda1",
        VirtualizationType="hvm",
    )

    config = {
        "ami": {
            "query": {
                "name": "test-ami-*",
                "architecture": "x86_64",
            }
        }
    }

    ami_id = ec2_manager.resolve_ami(config)
    assert ami_id.startswith("ami-")


def test_resolve_ami_query_invalid_architecture(ec2_manager):
    """Test error when invalid architecture is specified."""
    config = {
        "ami": {
            "query": {
                "name": "test-ami-*",
                "architecture": "amd64",
            }
        }
    }

    with pytest.raises(ValueError, match="Invalid architecture"):
        ec2_manager.resolve_ami(config)


def test_resolve_ami_query_missing_name(ec2_manager):
    """Test error when query.name is missing."""
    config = {"ami": {"query": {"owner": "099720109477"}}}

    with pytest.raises(ValueError, match="ami.query.name is required"):
        ec2_manager.resolve_ami(config)


def test_resolve_ami_query_no_results(ec2_manager):
    """Test error when query matches no AMIs."""
    config = {
        "ami": {
            "query": {
                "name": "nonexistent-ami-pattern-*",
            }
        }
    }

    with pytest.raises(ValueError, match="No AMI found"):
        ec2_manager.resolve_ami(config)


def test_resolve_ami_default_ubuntu(ec2_manager):
    """Test resolve_ami with default Amazon Ubuntu 24 when no ami section."""
    ec2_client = ec2_manager.ec2_client
    ec2_client.register_image(
        Name="Amazon Ubuntu 24 LTS x86_64 20240101",
        Description="Ubuntu 24 LTS",
        Architecture="x86_64",
        RootDeviceName="/dev/sda1",
        VirtualizationType="hvm",
    )

    config = {}

    ami_id = ec2_manager.resolve_ami(config)
    assert ami_id.startswith("ami-")


def test_find_ami_by_query_returns_newest(ec2_manager):
    """Test find_ami_by_query returns the newest AMI by CreationDate."""
    ec2_client = ec2_manager.ec2_client
    ami1_id = ec2_client.register_image(
        Name="test-ami-20230101",
        Description="Test AMI 2023-01-01",
        Architecture="x86_64",
        RootDeviceName="/dev/sda1",
        VirtualizationType="hvm",
    )["ImageId"]

    ami2_id = ec2_client.register_image(
        Name="test-ami-20231231",
        Description="Test AMI 2023-12-31 (newer)",
        Architecture="x86_64",
        RootDeviceName="/dev/sda1",
        VirtualizationType="hvm",
    )["ImageId"]

    result_ami_id = ec2_manager.find_ami_by_query(
        name_pattern="test-ami-*",
    )

    images = ec2_client.describe_images(ImageIds=[ami1_id, ami2_id])["Images"]
    ami1_creation = next(img for img in images if img["ImageId"] == ami1_id)[
        "CreationDate"
    ]
    ami2_creation = next(img for img in images if img["ImageId"] == ami2_id)[
        "CreationDate"
    ]

    if ami2_creation > ami1_creation:
        assert result_ami_id == ami2_id
    else:
        assert result_ami_id == ami1_id


def test_find_ami_by_query_with_owner(ec2_manager):
    """Test find_ami_by_query with owner filter."""
    ec2_client = ec2_manager.ec2_client
    ec2_client.register_image(
        Name="test-owned-ami",
        Description="Test owned AMI",
        Architecture="x86_64",
        RootDeviceName="/dev/sda1",
        VirtualizationType="hvm",
    )

    result_ami_id = ec2_manager.find_ami_by_query(
        name_pattern="test-owned-ami",
    )

    assert result_ami_id.startswith("ami-")


def test_find_ami_by_query_with_architecture(ec2_manager):
    """Test find_ami_by_query with architecture filter."""
    ec2_client = ec2_manager.ec2_client
    ec2_client.register_image(
        Name="test-arch-x86",
        Description="Test x86_64 AMI",
        Architecture="x86_64",
        RootDeviceName="/dev/sda1",
        VirtualizationType="hvm",
    )

    result_ami_id = ec2_manager.find_ami_by_query(
        name_pattern="test-arch-*",
        architecture="x86_64",
    )

    assert result_ami_id.startswith("ami-")


def test_find_ami_by_query_no_results(ec2_manager):
    """Test find_ami_by_query raises error when no AMIs match."""
    with pytest.raises(ValueError, match="No AMI found"):
        ec2_manager.find_ami_by_query(
            name_pattern="nonexistent-pattern-*",
        )


def test_stop_instance_success(ec2_manager, cleanup_keys, registered_ami):
    """Test successful instance stop with waiter and normalized dict return."""
    config = {
        "instance_type": "t3.medium",
        "disk_size": 50,
        "region": "us-east-1",
        "ami": {"image_id": registered_ami},
    }

    with patch("time.time", return_value=1234567890):
        result = ec2_manager.launch_instance(config)
        cleanup_keys.append(result["key_file"])

    instance_id = result["instance_id"]

    response = ec2_manager.stop_instance(instance_id)

    assert response["instance_id"] == instance_id
    assert response["state"] == "stopped"
    assert "public_ip" in response
    assert "private_ip" in response
    assert "instance_type" in response

    instance = ec2_manager.ec2_resource.Instance(instance_id)
    instance.load()
    assert instance.state["Name"] == "stopped"


def test_stop_instance_waiter_timeout(ec2_manager, cleanup_keys, registered_ami):
    """Test stop_instance raises RuntimeError on waiter timeout."""
    from botocore.exceptions import WaiterError

    config = {
        "instance_type": "t3.medium",
        "disk_size": 50,
        "region": "us-east-1",
        "ami": {"image_id": registered_ami},
    }

    with patch("time.time", return_value=1234567890):
        result = ec2_manager.launch_instance(config)
        cleanup_keys.append(result["key_file"])

    instance_id = result["instance_id"]

    with patch.object(ec2_manager.ec2_client, "get_waiter") as mock_waiter:
        mock_waiter_instance = mock_waiter.return_value
        mock_waiter_instance.wait.side_effect = WaiterError(
            name="instance_stopped",
            reason="Max attempts exceeded",
            last_response={"Instances": [{"State": {"Name": "running"}}]},
        )

        with pytest.raises(RuntimeError, match="Failed to stop instance"):
            ec2_manager.stop_instance(instance_id)


def test_stop_instance_api_error(ec2_manager, cleanup_keys, registered_ami):
    """Test stop_instance handles ClientError from API."""
    config = {
        "instance_type": "t3.medium",
        "disk_size": 50,
        "region": "us-east-1",
        "ami": {"image_id": registered_ami},
    }

    with patch("time.time", return_value=1234567890):
        result = ec2_manager.launch_instance(config)
        cleanup_keys.append(result["key_file"])

    instance_id = result["instance_id"]

    with patch.object(ec2_manager.ec2_client, "stop_instances") as mock_stop:
        mock_stop.side_effect = ClientError(
            {
                "Error": {
                    "Code": "InvalidInstanceID.NotFound",
                    "Message": "Instance not found",
                }
            },
            "StopInstances",
        )

        with pytest.raises(ClientError):
            ec2_manager.stop_instance(instance_id)


def test_stop_instance_returns_normalized_keys(
    ec2_manager, cleanup_keys, registered_ami
):
    """Test stop_instance returns dict with all expected keys."""
    config = {
        "instance_type": "t3.medium",
        "disk_size": 50,
        "region": "us-east-1",
        "ami": {"image_id": registered_ami},
    }

    with patch("time.time", return_value=1234567890):
        result = ec2_manager.launch_instance(config)
        cleanup_keys.append(result["key_file"])

    instance_id = result["instance_id"]
    response = ec2_manager.stop_instance(instance_id)

    expected_keys = {"instance_id", "public_ip", "private_ip", "state", "instance_type"}
    assert expected_keys.issubset(response.keys())


def test_start_instance_success(ec2_manager, cleanup_keys, registered_ami):
    """Test successful instance start with waiter and normalized dict return."""
    config = {
        "instance_type": "t3.medium",
        "disk_size": 50,
        "region": "us-east-1",
        "ami": {"image_id": registered_ami},
    }

    with patch("time.time", return_value=1234567890):
        result = ec2_manager.launch_instance(config)
        cleanup_keys.append(result["key_file"])

    instance_id = result["instance_id"]

    ec2_manager.stop_instance(instance_id)

    response = ec2_manager.start_instance(instance_id)

    assert response["instance_id"] == instance_id
    assert response["state"] == "running"
    assert "public_ip" in response
    assert "private_ip" in response
    assert "instance_type" in response

    instance = ec2_manager.ec2_resource.Instance(instance_id)
    instance.load()
    assert instance.state["Name"] == "running"


def test_start_instance_waiter_timeout(ec2_manager, cleanup_keys, registered_ami):
    """Test start_instance raises RuntimeError on waiter timeout."""
    from botocore.exceptions import WaiterError

    config = {
        "instance_type": "t3.medium",
        "disk_size": 50,
        "region": "us-east-1",
        "ami": {"image_id": registered_ami},
    }

    with patch("time.time", return_value=1234567890):
        result = ec2_manager.launch_instance(config)
        cleanup_keys.append(result["key_file"])

    instance_id = result["instance_id"]
    ec2_manager.stop_instance(instance_id)

    with patch.object(ec2_manager.ec2_client, "get_waiter") as mock_waiter:
        mock_waiter_instance = mock_waiter.return_value
        mock_waiter_instance.wait.side_effect = WaiterError(
            name="instance_running",
            reason="Max attempts exceeded",
            last_response={"Instances": [{"State": {"Name": "pending"}}]},
        )

        with pytest.raises(RuntimeError, match="Failed to start instance"):
            ec2_manager.start_instance(instance_id)


def test_start_instance_api_error(ec2_manager, cleanup_keys, registered_ami):
    """Test start_instance handles ClientError from API."""
    config = {
        "instance_type": "t3.medium",
        "disk_size": 50,
        "region": "us-east-1",
        "ami": {"image_id": registered_ami},
    }

    with patch("time.time", return_value=1234567890):
        result = ec2_manager.launch_instance(config)
        cleanup_keys.append(result["key_file"])

    instance_id = result["instance_id"]
    ec2_manager.stop_instance(instance_id)

    with patch.object(ec2_manager.ec2_client, "start_instances") as mock_start:
        mock_start.side_effect = ClientError(
            {
                "Error": {
                    "Code": "InvalidInstanceID.NotFound",
                    "Message": "Instance not found",
                }
            },
            "StartInstances",
        )

        with pytest.raises(ClientError):
            ec2_manager.start_instance(instance_id)


def test_start_instance_returns_normalized_keys(
    ec2_manager, cleanup_keys, registered_ami
):
    """Test start_instance returns dict with all expected keys."""
    config = {
        "instance_type": "t3.medium",
        "disk_size": 50,
        "region": "us-east-1",
        "ami": {"image_id": registered_ami},
    }

    with patch("time.time", return_value=1234567890):
        result = ec2_manager.launch_instance(config)
        cleanup_keys.append(result["key_file"])

    instance_id = result["instance_id"]
    ec2_manager.stop_instance(instance_id)

    response = ec2_manager.start_instance(instance_id)

    expected_keys = {"instance_id", "public_ip", "private_ip", "state", "instance_type"}
    assert expected_keys.issubset(response.keys())


def test_get_volume_size_success(ec2_manager, cleanup_keys, registered_ami):
    """Test successful volume size retrieval returns integer GB size."""
    config = {
        "instance_type": "t3.medium",
        "disk_size": 50,
        "region": "us-east-1",
        "ami": {"image_id": registered_ami},
    }

    with patch("time.time", return_value=1234567890):
        result = ec2_manager.launch_instance(config)
        cleanup_keys.append(result["key_file"])

    instance_id = result["instance_id"]

    size = ec2_manager.get_volume_size(instance_id)

    assert isinstance(size, int)
    assert size == 50


def test_get_volume_size_no_block_devices(ec2_manager, registered_ami):
    """Test get_volume_size returns None when no block devices."""
    instances = ec2_manager.ec2_resource.create_instances(
        ImageId=registered_ami,
        InstanceType="t3.medium",
        MinCount=1,
        MaxCount=1,
    )
    instance = instances[0]
    instance_id = instance.id

    with patch.object(ec2_manager.ec2_client, "describe_instances") as mock_describe:
        mock_describe.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": instance_id,
                            "BlockDeviceMappings": [],
                        }
                    ]
                }
            ]
        }

        result = ec2_manager.get_volume_size(instance_id)
        assert result is None


def test_get_volume_size_no_root_volume(ec2_manager, registered_ami):
    """Test get_volume_size raises RuntimeError when no root volume."""
    instances = ec2_manager.ec2_resource.create_instances(
        ImageId=registered_ami,
        InstanceType="t3.medium",
        MinCount=1,
        MaxCount=1,
    )
    instance = instances[0]
    instance_id = instance.id

    with patch.object(ec2_manager.ec2_client, "describe_instances") as mock_describe:
        mock_describe.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": instance_id,
                            "BlockDeviceMappings": [{"DeviceName": "/dev/sda1"}],
                        }
                    ]
                }
            ]
        }

        with pytest.raises(RuntimeError, match="has no root volume"):
            ec2_manager.get_volume_size(instance_id)


def test_get_volume_size_api_error(ec2_manager, registered_ami):
    """Test get_volume_size raises RuntimeError with proper error message on API error."""
    instances = ec2_manager.ec2_resource.create_instances(
        ImageId=registered_ami,
        InstanceType="t3.medium",
        MinCount=1,
        MaxCount=1,
    )
    instance = instances[0]
    instance_id = instance.id

    with patch.object(
        ec2_manager.ec2_client, "describe_volumes"
    ) as mock_describe_volumes:
        mock_describe_volumes.side_effect = ClientError(
            {
                "Error": {
                    "Code": "InvalidVolume.NotFound",
                    "Message": "Volume not found",
                }
            },
            "DescribeVolumes",
        )

        with pytest.raises(RuntimeError, match="Failed to get volume size"):
            ec2_manager.get_volume_size(instance_id)


def test_launch_instance_returns_launch_time(ec2_manager, cleanup_keys, registered_ami):
    """Verify launch_instance includes launch_time in return value."""
    config = {
        "instance_type": "t3.micro",
        "disk_size": 20,
        "region": "us-east-1",
        "camp_name": "test-launch-time",
        "ami": {"image_id": registered_ami},
    }

    result = ec2_manager.launch_instance(config)
    cleanup_keys.append(result["key_file"])

    assert "launch_time" in result
    assert isinstance(result["launch_time"], datetime)


def test_start_instance_returns_launch_time_when_already_running(
    ec2_manager, cleanup_keys, registered_ami
):
    """Verify start_instance includes launch_time when instance is running."""
    config = {
        "instance_type": "t3.micro",
        "disk_size": 20,
        "region": "us-east-1",
        "camp_name": "test-start-running",
        "ami": {"image_id": registered_ami},
    }

    launch_result = ec2_manager.launch_instance(config)
    cleanup_keys.append(launch_result["key_file"])
    instance_id = launch_result["instance_id"]

    info = ec2_manager.start_instance(instance_id)

    assert "launch_time" in info
    assert isinstance(info["launch_time"], datetime)


def test_list_instances_returns_launch_time(ec2_manager, cleanup_keys, registered_ami):
    """Verify list_instances includes launch_time for each instance."""
    config = {
        "instance_type": "t3.micro",
        "disk_size": 20,
        "region": "us-east-1",
        "camp_name": "test-list-time",
        "ami": {"image_id": registered_ami},
    }

    launch_result = ec2_manager.launch_instance(config)
    cleanup_keys.append(launch_result["key_file"])

    instances = ec2_manager.list_instances()

    assert len(instances) > 0

    for instance in instances:
        assert "launch_time" in instance
        assert isinstance(instance["launch_time"], datetime)


def test_start_instance_extracts_unique_id_from_tags(
    ec2_manager, cleanup_keys, registered_ami
):
    """Verify unique_id is extracted from instance tags when started."""
    config = {
        "instance_type": "t3.micro",
        "disk_size": 20,
        "region": "us-east-1",
        "camp_name": "test-extract-id",
        "ami": {"image_id": registered_ami},
    }

    launch_result = ec2_manager.launch_instance(config)
    cleanup_keys.append(launch_result["key_file"])
    instance_id = launch_result["instance_id"]
    original_unique_id = launch_result["unique_id"]

    ec2_manager.ec2_client.stop_instances(InstanceIds=[instance_id])

    result = ec2_manager.start_instance(instance_id)

    assert result["unique_id"] == original_unique_id


def test_start_instance_calculates_key_file_path(
    ec2_manager, cleanup_keys, registered_ami
):
    """Verify key_file path is calculated correctly using CAMPERS_DIR."""
    config = {
        "instance_type": "t3.micro",
        "disk_size": 20,
        "region": "us-east-1",
        "camp_name": "test-key-file",
        "ami": {"image_id": registered_ami},
    }

    launch_result = ec2_manager.launch_instance(config)
    cleanup_keys.append(launch_result["key_file"])
    instance_id = launch_result["instance_id"]
    unique_id = launch_result["unique_id"]

    ec2_manager.ec2_client.stop_instances(InstanceIds=[instance_id])

    result = ec2_manager.start_instance(instance_id)

    campers_dir = os.environ.get("CAMPERS_DIR", str(Path.home() / ".campers"))
    expected_key_file = str(Path(campers_dir) / "keys" / f"{unique_id}.pem")

    assert result["key_file"] == expected_key_file


def test_start_instance_returns_none_unique_id_when_tag_missing(
    ec2_manager, cleanup_keys, registered_ami
):
    """Verify unique_id is None when UniqueId tag is missing."""
    config = {
        "instance_type": "t3.micro",
        "disk_size": 20,
        "region": "us-east-1",
        "ami": {"image_id": registered_ami},
    }

    launch_result = ec2_manager.launch_instance(config)
    cleanup_keys.append(launch_result["key_file"])
    instance_id = launch_result["instance_id"]

    instance = ec2_manager.ec2_resource.Instance(instance_id)
    instance.delete_tags(Tags=[{"Key": "UniqueId"}])

    ec2_manager.ec2_client.stop_instances(InstanceIds=[instance_id])

    result = ec2_manager.start_instance(instance_id)

    assert result["unique_id"] is None


def test_start_instance_returns_none_key_file_when_unique_id_missing(
    ec2_manager, cleanup_keys, registered_ami
):
    """Verify key_file is None when unique_id is not found."""
    config = {
        "instance_type": "t3.micro",
        "disk_size": 20,
        "region": "us-east-1",
        "ami": {"image_id": registered_ami},
    }

    launch_result = ec2_manager.launch_instance(config)
    cleanup_keys.append(launch_result["key_file"])
    instance_id = launch_result["instance_id"]

    instance = ec2_manager.ec2_resource.Instance(instance_id)
    instance.delete_tags(Tags=[{"Key": "UniqueId"}])

    ec2_manager.ec2_client.stop_instances(InstanceIds=[instance_id])

    result = ec2_manager.start_instance(instance_id)

    assert result["key_file"] is None
