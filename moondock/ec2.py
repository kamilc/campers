"""EC2 instance management for moondock."""

import logging
import os
import time
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import (
    ClientError,
    EndpointConnectionError,
    NoCredentialsError,
    WaiterError,
)

logger = logging.getLogger(__name__)

ACTIVE_INSTANCE_STATES = ["pending", "running", "stopping", "stopped"]

VALID_INSTANCE_TYPES = [
    "t2.micro",
    "t2.small",
    "t2.medium",
    "t2.large",
    "t2.xlarge",
    "t2.2xlarge",
    "t3.micro",
    "t3.small",
    "t3.medium",
    "t3.large",
    "t3.xlarge",
    "t3.2xlarge",
    "t3a.micro",
    "t3a.small",
    "t3a.medium",
    "t3a.large",
    "t3a.xlarge",
    "t3a.2xlarge",
    "m5.large",
    "m5.xlarge",
    "m5.2xlarge",
    "m5.4xlarge",
    "m5.8xlarge",
    "m5.12xlarge",
    "m5.16xlarge",
    "m5.24xlarge",
    "m5a.large",
    "m5a.xlarge",
    "m5a.2xlarge",
    "m5a.4xlarge",
    "m5a.8xlarge",
    "m5a.12xlarge",
    "m5a.16xlarge",
    "m5a.24xlarge",
    "c5.large",
    "c5.xlarge",
    "c5.2xlarge",
    "c5.4xlarge",
    "c5.9xlarge",
    "c5.12xlarge",
    "c5.18xlarge",
    "c5.24xlarge",
    "r5.large",
    "r5.xlarge",
    "r5.2xlarge",
    "r5.4xlarge",
    "r5.8xlarge",
    "r5.12xlarge",
    "r5.16xlarge",
    "r5.24xlarge",
]


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

        moondock_dir = os.environ.get("MOONDOCK_DIR", str(Path.home() / ".moondock"))
        keys_dir = Path(moondock_dir) / "keys"
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
        ClientError
            If instance type is invalid
        """
        instance_type = config["instance_type"]

        if instance_type not in VALID_INSTANCE_TYPES:
            raise ClientError(
                {
                    "Error": {
                        "Code": "InvalidParameterValue",
                        "Message": f"Invalid instance type: {instance_type}",
                    }
                },
                "RunInstances",
            )

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
                InstanceType=instance_type,
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

    def list_instances(self, region_filter: str | None = None) -> list[dict[str, Any]]:
        """List all moondock-managed instances across regions.

        Parameters
        ----------
        region_filter : str | None
            Optional AWS region to filter results (e.g., "us-east-1")
            If None, queries all regions

        Returns
        -------
        list[dict[str, Any]]
            List of instance dictionaries with keys: instance_id, name, state,
            region, instance_type, launch_time, machine_config

        Notes
        -----
        When querying all regions (region_filter=None), this method performs
        sequential API calls to each AWS region (N+1 pattern: 1 call to
        describe_regions, then N calls to describe_instances per region).
        With 20+ AWS regions, total latency may reach several seconds depending
        on network conditions and number of instances per region.
        """
        if region_filter:
            regions = [region_filter]
        else:
            try:
                ec2_client = boto3.client("ec2", region_name=self.region)
                regions_response = ec2_client.describe_regions()
                regions = [r["RegionName"] for r in regions_response["Regions"]]
            except NoCredentialsError:
                raise
            except (ClientError, EndpointConnectionError) as e:
                logger.warning(
                    f"Unable to query all AWS regions ({e.__class__.__name__}), "
                    f"falling back to default region '{self.region}' only. "
                    f"Use --region flag to query specific regions."
                )
                regions = [self.region]

        instances = []

        for region in regions:
            try:
                regional_ec2 = boto3.client("ec2", region_name=region)

                response = regional_ec2.describe_instances(
                    Filters=[
                        {"Name": "tag:ManagedBy", "Values": ["moondock"]},
                        {
                            "Name": "instance-state-name",
                            "Values": ACTIVE_INSTANCE_STATES,
                        },
                    ]
                )

                for reservation in response["Reservations"]:
                    for instance in reservation["Instances"]:
                        tags = {
                            tag["Key"]: tag["Value"] for tag in instance.get("Tags", [])
                        }

                        instances.append(
                            {
                                "instance_id": instance["InstanceId"],
                                "name": tags.get("Name", "N/A"),
                                "state": instance["State"]["Name"],
                                "region": region,
                                "instance_type": instance["InstanceType"],
                                "launch_time": instance["LaunchTime"],
                                "machine_config": tags.get("MachineConfig", "ad-hoc"),
                            }
                        )

            except NoCredentialsError:
                raise
            except ClientError as e:
                logger.warning(f"Failed to query region {region}: {e}")
                continue

        instances.sort(key=lambda x: x["launch_time"], reverse=True)

        return instances

    def find_instances_by_name_or_id(
        self, name_or_id: str, region_filter: str | None = None
    ) -> list[dict[str, Any]]:
        """Find moondock-managed instances matching ID or MachineConfig.

        Parameters
        ----------
        name_or_id : str
            EC2 instance ID or MachineConfig name to search for
        region_filter : str | None
            Optional AWS region to filter results

        Returns
        -------
        list[dict[str, Any]]
            List of matching instances with keys: instance_id, name, state,
            region, instance_type, launch_time, machine_config
        """
        instances = self.list_instances(region_filter=region_filter)

        id_matches = [inst for inst in instances if inst["instance_id"] == name_or_id]

        if id_matches:
            return id_matches

        return [inst for inst in instances if inst["machine_config"] == name_or_id]

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

        try:
            waiter = self.ec2_client.get_waiter("instance_terminated")
            waiter.wait(
                InstanceIds=[instance_id], WaiterConfig={"Delay": 15, "MaxAttempts": 40}
            )
        except WaiterError as e:
            raise RuntimeError(f"Failed to terminate instance: {e}") from e

        if unique_id:
            try:
                self.ec2_client.delete_key_pair(KeyName=f"moondock-{unique_id}")
            except ClientError:
                pass

            moondock_dir = os.environ.get(
                "MOONDOCK_DIR", str(Path.home() / ".moondock")
            )
            key_file = Path(moondock_dir) / "keys" / f"{unique_id}.pem"

            if key_file.exists():
                key_file.unlink()

        if sg_id:
            try:
                self.ec2_client.delete_security_group(GroupId=sg_id)
            except ClientError:
                pass
