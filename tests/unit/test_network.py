"""Tests for AWS network and security group management."""

import logging
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from campers.providers.aws.network import delete_security_group_with_retry


@pytest.fixture(scope="function")
def ec2_manager(aws_credentials):
    """Return mocked EC2Manager with patched describe_images for Canonical."""
    with mock_aws():
        from campers.providers.aws.compute import EC2Manager

        manager = EC2Manager(region="us-east-1")

        original_describe_images = manager.ec2_client.describe_images

        def mock_describe_images(**kwargs):
            modified_kwargs = kwargs.copy()

            if "Owners" in modified_kwargs and (
                "099720109477" in modified_kwargs["Owners"] or "amazon" in modified_kwargs["Owners"]
            ):
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

        manager.ec2_client.describe_images = mock_describe_images

        yield manager


def test_delete_security_group_with_retry_success_first_attempt(aws_credentials):
    """Test successful deletion on first attempt."""
    with mock_aws():
        from campers.providers.aws.compute import EC2Manager

        ec2_manager = EC2Manager(region="us-east-1")
        ec2_client = ec2_manager.ec2_client

        vpcs = ec2_client.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])
        vpc_id = vpcs["Vpcs"][0]["VpcId"]

        response = ec2_client.create_security_group(
            GroupName="test-sg", Description="Test SG", VpcId=vpc_id
        )
        sg_id = response["GroupId"]

        result = delete_security_group_with_retry(ec2_client, sg_id)

        assert result is True

        sgs = ec2_client.describe_security_groups()
        sg_ids = [sg["GroupId"] for sg in sgs["SecurityGroups"]]
        assert sg_id not in sg_ids


def test_delete_security_group_with_retry_invalid_group_not_found(aws_credentials):
    """Test idempotent handling of InvalidGroup.NotFound."""
    with mock_aws():
        from campers.providers.aws.compute import EC2Manager

        ec2_manager = EC2Manager(region="us-east-1")
        ec2_client = ec2_manager.ec2_client

        result = delete_security_group_with_retry(ec2_client, "sg-nonexistent")

        assert result is True


def test_delete_security_group_with_retry_dependency_violation_then_success(
    aws_credentials, caplog
):
    """Test successful deletion after DependencyViolation retry."""
    with mock_aws():
        from campers.providers.aws.compute import EC2Manager

        ec2_manager = EC2Manager(region="us-east-1")
        ec2_client = ec2_manager.ec2_client

        vpcs = ec2_client.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])
        vpc_id = vpcs["Vpcs"][0]["VpcId"]

        response = ec2_client.create_security_group(
            GroupName="test-sg-retry", Description="Test SG", VpcId=vpc_id
        )
        sg_id = response["GroupId"]

        call_count = {"count": 0}
        original_delete = ec2_client.delete_security_group

        def mock_delete_with_failure(**kwargs):
            call_count["count"] += 1
            if call_count["count"] < 3:
                error_response = {
                    "Error": {
                        "Code": "DependencyViolation",
                        "Message": "SG is in use",
                    }
                }
                raise ClientError(error_response, "DeleteSecurityGroup")
            return original_delete(**kwargs)

        ec2_client.delete_security_group = mock_delete_with_failure

        with caplog.at_level(logging.WARNING):
            result = delete_security_group_with_retry(ec2_client, sg_id)

        assert result is True
        assert call_count["count"] == 3
        assert "retrying in" in caplog.text


def test_delete_security_group_with_retry_max_retries_exceeded(aws_credentials, caplog):
    """Test failure after max retries exhausted."""
    with mock_aws():
        from campers.providers.aws.compute import EC2Manager

        ec2_manager = EC2Manager(region="us-east-1")
        ec2_client = ec2_manager.ec2_client

        vpcs = ec2_client.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])
        vpc_id = vpcs["Vpcs"][0]["VpcId"]

        response = ec2_client.create_security_group(
            GroupName="test-sg-max-retries", Description="Test SG", VpcId=vpc_id
        )
        sg_id = response["GroupId"]

        call_count = {"count": 0}

        def mock_delete_always_fails(**kwargs):
            call_count["count"] += 1
            error_response = {
                "Error": {
                    "Code": "DependencyViolation",
                    "Message": "SG is in use",
                }
            }
            raise ClientError(error_response, "DeleteSecurityGroup")

        ec2_client.delete_security_group = mock_delete_always_fails

        with caplog.at_level(logging.ERROR):
            result = delete_security_group_with_retry(ec2_client, sg_id, max_attempts=3)

        assert result is False
        assert call_count["count"] == 3
        assert "after 3 attempts" in caplog.text


def test_delete_security_group_with_retry_invalid_group_in_use(aws_credentials, caplog):
    """Test retry on InvalidGroup.InUse error."""
    with mock_aws():
        from campers.providers.aws.compute import EC2Manager

        ec2_manager = EC2Manager(region="us-east-1")
        ec2_client = ec2_manager.ec2_client

        vpcs = ec2_client.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])
        vpc_id = vpcs["Vpcs"][0]["VpcId"]

        response = ec2_client.create_security_group(
            GroupName="test-sg-in-use", Description="Test SG", VpcId=vpc_id
        )
        sg_id = response["GroupId"]

        call_count = {"count": 0}
        original_delete = ec2_client.delete_security_group

        def mock_delete_with_in_use(**kwargs):
            call_count["count"] += 1
            if call_count["count"] < 2:
                error_response = {
                    "Error": {
                        "Code": "InvalidGroup.InUse",
                        "Message": "SG is in use",
                    }
                }
                raise ClientError(error_response, "DeleteSecurityGroup")
            return original_delete(**kwargs)

        ec2_client.delete_security_group = mock_delete_with_in_use

        with caplog.at_level(logging.WARNING):
            result = delete_security_group_with_retry(ec2_client, sg_id)

        assert result is True
        assert call_count["count"] == 2
        assert "retrying in" in caplog.text


def test_delete_security_group_with_retry_fatal_error(aws_credentials, caplog):
    """Test fatal error stops retry immediately."""
    with mock_aws():
        from campers.providers.aws.compute import EC2Manager

        ec2_manager = EC2Manager(region="us-east-1")
        ec2_client = ec2_manager.ec2_client

        call_count = {"count": 0}

        def mock_delete_unauthorized(**kwargs):
            call_count["count"] += 1
            error_response = {
                "Error": {
                    "Code": "UnauthorizedOperation",
                    "Message": "Not authorized",
                }
            }
            raise ClientError(error_response, "DeleteSecurityGroup")

        ec2_client.delete_security_group = mock_delete_unauthorized

        with caplog.at_level(logging.ERROR):
            result = delete_security_group_with_retry(ec2_client, "sg-test-fatal")

        assert result is False
        assert call_count["count"] == 1
        assert "UnauthorizedOperation" in caplog.text


def test_delete_security_group_with_retry_exponential_backoff(aws_credentials):
    """Test exponential backoff timing."""
    with mock_aws():
        from campers.providers.aws.compute import EC2Manager

        ec2_manager = EC2Manager(region="us-east-1")
        ec2_client = ec2_manager.ec2_client

        vpcs = ec2_client.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])
        vpc_id = vpcs["Vpcs"][0]["VpcId"]

        response = ec2_client.create_security_group(
            GroupName="test-sg-backoff", Description="Test SG", VpcId=vpc_id
        )
        sg_id = response["GroupId"]

        call_count = {"count": 0}
        original_delete = ec2_client.delete_security_group

        def mock_delete_with_delay(**kwargs):
            call_count["count"] += 1

            if call_count["count"] <= 2:
                error_response = {
                    "Error": {
                        "Code": "DependencyViolation",
                        "Message": "SG is in use",
                    }
                }
                raise ClientError(error_response, "DeleteSecurityGroup")
            return original_delete(**kwargs)

        ec2_client.delete_security_group = mock_delete_with_delay

        with patch("campers.providers.aws.network.time.sleep") as mock_sleep:
            result = delete_security_group_with_retry(
                ec2_client, sg_id, base_delay=1.0, max_delay=30.0
            )

        assert result is True
        assert mock_sleep.call_count == 2

        call_args = [call_obj[0][0] for call_obj in mock_sleep.call_args_list]
        assert 0.9 <= call_args[0] <= 1.1
        assert 1.8 <= call_args[1] <= 2.2


def test_delete_security_group_with_retry_max_delay_cap(aws_credentials):
    """Test maximum delay cap is enforced."""
    mock_client = MagicMock()

    call_count = {"count": 0}

    def mock_delete(**kwargs):
        call_count["count"] += 1
        if call_count["count"] <= 4:
            error_response = {
                "Error": {
                    "Code": "DependencyViolation",
                    "Message": "SG is in use",
                }
            }
            raise ClientError(error_response, "DeleteSecurityGroup")

    mock_client.delete_security_group = mock_delete

    with patch("campers.providers.aws.network.time.sleep") as mock_sleep:
        result = delete_security_group_with_retry(
            mock_client, "sg-test", base_delay=1.0, max_delay=30.0, max_attempts=5
        )

    assert result is True
    assert mock_sleep.call_count == 4

    call_args = [call_obj[0][0] for call_obj in mock_sleep.call_args_list]
    expected_delays = [1.0, 2.0, 4.0, 8.0]
    for actual, expected in zip(call_args, expected_delays, strict=True):
        assert expected * 0.9 <= actual <= expected * 1.1


def test_create_security_group_with_new_naming_convention(ec2_manager):
    """Test security group creation with new naming convention."""
    unique_id = "test-unique-id-123"
    project_name = "simple1"
    branch = "main"
    camp_name = "jupyter"

    sg_id = ec2_manager.network_manager.create_security_group(
        unique_id=unique_id,
        project_name=project_name,
        branch=branch,
        camp_name=camp_name,
    )

    assert sg_id is not None
    assert sg_id.startswith("sg-")

    sgs = ec2_manager.ec2_client.describe_security_groups(GroupIds=[sg_id])
    sg = sgs["SecurityGroups"][0]

    assert sg["GroupName"] == "campers-simple1-main-jupyter"
    assert sg["Description"] == f"Campers security group {unique_id}"


def test_create_security_group_with_old_naming_convention(ec2_manager):
    """Test security group creation falls back to old naming convention."""
    unique_id = "test-unique-id-456"

    sg_id = ec2_manager.network_manager.create_security_group(unique_id=unique_id)

    assert sg_id is not None
    assert sg_id.startswith("sg-")

    sgs = ec2_manager.ec2_client.describe_security_groups(GroupIds=[sg_id])
    sg = sgs["SecurityGroups"][0]

    assert sg["GroupName"] == f"campers-{unique_id}"


def test_create_security_group_deletes_existing_with_retry(ec2_manager):
    """Test security group creation deletes existing SG using retry logic."""
    unique_id = "test-unique-id-789"
    project_name = "myproject"
    branch = "dev"
    camp_name = "test"

    vpcs = ec2_manager.ec2_client.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])
    vpc_id = vpcs["Vpcs"][0]["VpcId"]

    response = ec2_manager.ec2_client.create_security_group(
        GroupName="campers-myproject-dev-test",
        Description="Old SG",
        VpcId=vpc_id,
    )
    old_sg_id = response["GroupId"]

    sg_id = ec2_manager.network_manager.create_security_group(
        unique_id=unique_id,
        project_name=project_name,
        branch=branch,
        camp_name=camp_name,
    )

    assert sg_id != old_sg_id

    sgs = ec2_manager.ec2_client.describe_security_groups()
    sg_names = [sg["GroupName"] for sg in sgs["SecurityGroups"]]
    assert sg_names.count("campers-myproject-dev-test") == 1


def test_terminate_instance_calls_delete_security_group_with_retry(aws_credentials):
    """Test that terminate_instance uses delete_security_group_with_retry."""
    with mock_aws():
        from campers.providers.aws.compute import EC2Manager

        ec2_manager = EC2Manager(region="us-east-1")

        vpcs = ec2_manager.ec2_client.describe_vpcs(
            Filters=[{"Name": "isDefault", "Values": ["true"]}]
        )
        vpc_id = vpcs["Vpcs"][0]["VpcId"]

        response = ec2_manager.ec2_client.create_security_group(
            GroupName="test-sg-terminate", Description="Test SG", VpcId=vpc_id
        )
        sg_id = response["GroupId"]

        ec2_manager.ec2_client.create_tags(
            Resources=[sg_id], Tags=[{"Key": "ManagedBy", "Value": "campers"}]
        )

        response = ec2_manager.ec2_client.register_image(
            Name="test-ami",
            Description="Test AMI",
            Architecture="x86_64",
            RootDeviceName="/dev/sda1",
            VirtualizationType="hvm",
        )
        ami_id = response["ImageId"]

        instances = ec2_manager.ec2_client.run_instances(
            ImageId=ami_id, InstanceType="t3.medium", MinCount=1, MaxCount=1
        )
        instance_id = instances["Instances"][0]["InstanceId"]

        instance = ec2_manager.ec2_resource.Instance(instance_id)

        ec2_manager.ec2_client.create_tags(
            Resources=[instance_id],
            Tags=[
                {"Key": "ManagedBy", "Value": "campers"},
                {"Key": "UniqueId", "Value": "test-unique-id"},
            ],
        )

        ec2_manager.ec2_client.modify_instance_attribute(
            InstanceId=instance_id,
            Groups=[sg_id],
        )

        ec2_manager.terminate_instance(instance_id)

        instance.reload()
        assert instance.state["Name"] == "terminated"

        sgs = ec2_manager.ec2_client.describe_security_groups()
        sg_ids = [sg["GroupId"] for sg in sgs["SecurityGroups"]]
        assert sg_id not in sg_ids


def test_rollback_resources_calls_delete_security_group_with_retry(aws_credentials):
    """Test that _rollback_resources uses delete_security_group_with_retry."""
    with mock_aws():
        from campers.providers.aws.compute import EC2Manager

        ec2_manager = EC2Manager(region="us-east-1")

        vpcs = ec2_manager.ec2_client.describe_vpcs(
            Filters=[{"Name": "isDefault", "Values": ["true"]}]
        )
        vpc_id = vpcs["Vpcs"][0]["VpcId"]

        response = ec2_manager.ec2_client.create_security_group(
            GroupName="test-sg-rollback", Description="Test SG", VpcId=vpc_id
        )
        sg_id = response["GroupId"]

        ec2_manager.ec2_client.create_tags(
            Resources=[sg_id], Tags=[{"Key": "ManagedBy", "Value": "campers"}]
        )

        response = ec2_manager.ec2_client.register_image(
            Name="test-ami-rollback",
            Description="Test AMI",
            Architecture="x86_64",
            RootDeviceName="/dev/sda1",
            VirtualizationType="hvm",
        )
        ami_id = response["ImageId"]

        instances = ec2_manager.ec2_client.run_instances(
            ImageId=ami_id, InstanceType="t3.medium", MinCount=1, MaxCount=1
        )
        instance_id = instances["Instances"][0]["InstanceId"]

        instance = ec2_manager.ec2_resource.Instance(instance_id)

        ec2_manager.ec2_client.create_tags(
            Resources=[instance_id],
            Tags=[
                {"Key": "ManagedBy", "Value": "campers"},
                {"Key": "UniqueId", "Value": "test-unique-id-rollback"},
            ],
        )

        ec2_manager.ec2_client.modify_instance_attribute(
            InstanceId=instance_id,
            Groups=[sg_id],
        )

        resources = {
            "instance": instance,
            "sg_id": sg_id,
            "key_name": None,
            "key_file": None,
        }

        ec2_manager._rollback_resources(resources)

        instance.reload()
        assert instance.state["Name"] == "terminated"

        sgs = ec2_manager.ec2_client.describe_security_groups()
        sg_ids = [sg["GroupId"] for sg in sgs["SecurityGroups"]]
        assert sg_id not in sg_ids


def test_ec2_instance_naming_with_camp_name(aws_credentials):
    """Test EC2 instance naming follows new convention with camp_name."""
    from unittest.mock import patch

    with mock_aws():
        from campers.providers.aws.compute import EC2Manager

        ec2_manager = EC2Manager(region="us-east-1")

        response = ec2_manager.ec2_client.register_image(
            Name="test-ami-naming",
            Description="Test AMI",
            Architecture="x86_64",
            RootDeviceName="/dev/sda1",
            VirtualizationType="hvm",
        )
        ami_id = response["ImageId"]

        config = {
            "instance_type": "t3.medium",
            "disk_size": 50,
            "region": "us-east-1",
            "camp_name": "jupyter",
            "ami": {"image_id": ami_id},
        }

        with (
            patch("campers.utils.get_git_project_name", return_value="simple1"),
            patch("campers.utils.get_git_branch", return_value="main"),
            patch("time.time", return_value=1234567890),
        ):
            result = ec2_manager.launch_instance(
                config, instance_name="campers-simple1-main-jupyter"
            )

        instance = ec2_manager.ec2_resource.Instance(result["instance_id"])
        instance.reload()

        tags = {tag["Key"]: tag["Value"] for tag in instance.tags}
        assert tags["Name"] == "campers-simple1-main-jupyter"
        assert tags["MachineConfig"] == "jupyter"

        sg_id = result["security_group_id"]
        sgs = ec2_manager.ec2_client.describe_security_groups(GroupIds=[sg_id])
        sg = sgs["SecurityGroups"][0]

        assert sg["GroupName"] == "campers-simple1-main-jupyter"
