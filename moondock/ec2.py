"""EC2 instance management for moondock."""

import logging
import time
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class EC2Manager:
    """Manage EC2 instance lifecycle for moondock."""

    def __init__(self, region: str) -> None:
        """Initialize EC2 manager.

        Parameters
        ----------
        region : str
            AWS region for EC2 operations
        """
        self.region = region
        self.ec2_client = boto3.client("ec2", region_name=region)
        self.ec2_resource = boto3.resource("ec2", region_name=region)

    def find_ubuntu_ami(self) -> str:
        """Find latest Ubuntu 22.04 LTS AMI in region.

        Returns
        -------
        str
            AMI ID for latest Ubuntu 22.04 LTS

        Raises
        ------
        ValueError
            If no suitable AMI found in region
        """
        response = self.ec2_client.describe_images(
            Owners=["099720109477"],
            Filters=[
                {
                    "Name": "name",
                    "Values": [
                        "ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"
                    ],
                },
                {"Name": "virtualization-type", "Values": ["hvm"]},
                {"Name": "architecture", "Values": ["x86_64"]},
                {"Name": "state", "Values": ["available"]},
            ],
        )

        if not response["Images"]:
            raise ValueError(f"No Ubuntu 22.04 AMI found in region {self.region}")

        images = sorted(
            response["Images"], key=lambda x: x["CreationDate"], reverse=True
        )
        return images[0]["ImageId"]

    def create_key_pair(self, unique_id: str) -> tuple[str, Path]:
        """Create SSH key pair and save to disk.

        Parameters
        ----------
        unique_id : str
            Unique identifier to use in key name (timestamp)

        Returns
        -------
        tuple[str, Path]
            Tuple of (key_name, key_file_path)
        """
        key_name = f"moondock-{unique_id}"

        try:
            self.ec2_client.delete_key_pair(KeyName=key_name)
        except ClientError:
            pass

        response = self.ec2_client.create_key_pair(KeyName=key_name)

        keys_dir = Path.home() / ".moondock" / "keys"
        keys_dir.mkdir(parents=True, exist_ok=True)

        key_file = keys_dir / f"{unique_id}.pem"
        key_file.write_text(response["KeyMaterial"])
        key_file.chmod(0o600)

        return key_name, key_file

    def create_security_group(self, unique_id: str) -> str:
        """Create security group with SSH access.

        Parameters
        ----------
        unique_id : str
            Unique identifier to use in security group name

        Returns
        -------
        str
            Security group ID
        """
        sg_name = f"moondock-{unique_id}"

        vpcs = self.ec2_client.describe_vpcs(
            Filters=[{"Name": "isDefault", "Values": ["true"]}]
        )

        if not vpcs["Vpcs"]:
            raise ValueError(f"No default VPC found in region {self.region}")

        vpc_id = vpcs["Vpcs"][0]["VpcId"]

        try:
            existing_sgs = self.ec2_client.describe_security_groups(
                Filters=[
                    {"Name": "group-name", "Values": [sg_name]},
                    {"Name": "vpc-id", "Values": [vpc_id]},
                ]
            )

            if existing_sgs["SecurityGroups"]:
                self.ec2_client.delete_security_group(
                    GroupId=existing_sgs["SecurityGroups"][0]["GroupId"]
                )
        except ClientError:
            pass

        response = self.ec2_client.create_security_group(
            GroupName=sg_name,
            Description=f"Moondock security group {unique_id}",
            VpcId=vpc_id,
        )

        sg_id = response["GroupId"]

        self.ec2_client.create_tags(
            Resources=[sg_id], Tags=[{"Key": "ManagedBy", "Value": "moondock"}]
        )

        self.ec2_client.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 22,
                    "ToPort": 22,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                }
            ],
        )

        return sg_id

    def launch_instance(self, config: dict[str, Any]) -> dict[str, Any]:
        """Launch EC2 instance based on configuration.

        Parameters
        ----------
        config : dict[str, Any]
            Merged configuration from ConfigLoader

        Returns
        -------
        dict[str, Any]
            Instance details: {instance_id, public_ip, state, key_file, unique_id, security_group_id}

        Raises
        ------
        RuntimeError
            If instance fails to reach running state within timeout
        """
        ami_id = self.find_ubuntu_ami()
        unique_id = str(int(time.time()))
        machine_name = config.get("machine_name", "ad-hoc")

        key_name = None
        key_file = None
        sg_id = None
        instance = None

        try:
            key_name, key_file = self.create_key_pair(unique_id)

            sg_id = self.create_security_group(unique_id)

            instances = self.ec2_resource.create_instances(
                ImageId=ami_id,
                InstanceType=config["instance_type"],
                KeyName=key_name,
                SecurityGroupIds=[sg_id],
                MinCount=1,
                MaxCount=1,
                BlockDeviceMappings=[
                    {
                        "DeviceName": "/dev/sda1",
                        "Ebs": {
                            "VolumeSize": config["disk_size"],
                            "VolumeType": "gp3",
                            "DeleteOnTermination": True,
                        },
                    }
                ],
                TagSpecifications=[
                    {
                        "ResourceType": "instance",
                        "Tags": [
                            {"Key": "ManagedBy", "Value": "moondock"},
                            {"Key": "Name", "Value": f"moondock-{unique_id}"},
                            {"Key": "MachineConfig", "Value": machine_name},
                            {"Key": "UniqueId", "Value": unique_id},
                        ],
                    }
                ],
            )

            instance = instances[0]
            instance_id = instance.id

            waiter = self.ec2_client.get_waiter("instance_running")
            waiter.wait(
                InstanceIds=[instance_id], WaiterConfig={"Delay": 15, "MaxAttempts": 20}
            )
            instance.reload()

            return {
                "instance_id": instance_id,
                "public_ip": instance.public_ip_address,
                "state": instance.state["Name"],
                "key_file": str(key_file),
                "security_group_id": sg_id,
                "unique_id": unique_id,
            }

        except Exception as e:
            if instance:
                try:
                    instance.terminate()
                except ClientError as cleanup_error:
                    logger.warning(
                        f"Failed to terminate instance during rollback: {cleanup_error}"
                    )

            if sg_id:
                try:
                    self.ec2_client.delete_security_group(GroupId=sg_id)
                except ClientError as cleanup_error:
                    logger.warning(
                        f"Failed to delete security group during rollback: {cleanup_error}"
                    )

            if key_name:
                try:
                    self.ec2_client.delete_key_pair(KeyName=key_name)
                except ClientError as cleanup_error:
                    logger.warning(
                        f"Failed to delete key pair during rollback: {cleanup_error}"
                    )

            if key_file and key_file.exists():
                try:
                    key_file.unlink()
                except OSError as cleanup_error:
                    logger.warning(
                        f"Failed to delete key file during rollback: {cleanup_error}"
                    )

            raise RuntimeError(f"Failed to launch instance: {e}") from e

    def terminate_instance(self, instance_id: str) -> None:
        """Terminate instance and clean up resources.

        Parameters
        ----------
        instance_id : str
            Instance ID to terminate

        Raises
        ------
        RuntimeError
            If instance fails to terminate within timeout
        """
        instance = self.ec2_resource.Instance(instance_id)

        unique_id = None

        for tag in instance.tags or []:
            if tag["Key"] == "UniqueId":
                unique_id = tag["Value"]
                break

        sg_id = (
            instance.security_groups[0]["GroupId"] if instance.security_groups else None
        )

        instance.terminate()

        waiter = self.ec2_client.get_waiter("instance_terminated")
        waiter.wait(
            InstanceIds=[instance_id], WaiterConfig={"Delay": 15, "MaxAttempts": 40}
        )

        if unique_id:
            try:
                self.ec2_client.delete_key_pair(KeyName=f"moondock-{unique_id}")
            except ClientError:
                pass

            key_file = Path.home() / ".moondock" / "keys" / f"{unique_id}.pem"

            if key_file.exists():
                key_file.unlink()

        if sg_id:
            try:
                self.ec2_client.delete_security_group(GroupId=sg_id)
            except ClientError:
                pass
