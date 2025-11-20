"""EC2 instance management for moondock."""

import logging
import os
import re
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

    def __init__(
        self,
        region: str,
        boto3_client_factory: Any | None = None,
        boto3_resource_factory: Any | None = None,
    ) -> None:
        """Initialize EC2 manager.

        Parameters
        ----------
        region : str
            AWS region for EC2 operations
        boto3_client_factory : Callable[..., Any] | None
            Optional factory for creating boto3 clients. If None, uses boto3.client
        boto3_resource_factory : Callable[..., Any] | None
            Optional factory for creating boto3 resources. If None, uses boto3.resource
        """
        self.region = region
        self.boto3_client_factory = boto3_client_factory or boto3.client
        self.boto3_resource_factory = boto3_resource_factory or boto3.resource
        self.ec2_client = self.boto3_client_factory("ec2", region_name=region)
        self.ec2_resource = self.boto3_resource_factory("ec2", region_name=region)

    def _is_localstack_endpoint(self) -> bool:
        """Detect if EC2 client is configured for LocalStack.

        This method enables high-fidelity BDD testing against LocalStack while
        maintaining clean production code. Production AWS users never trigger this
        code path because real AWS endpoints never contain "localstack" or ":4566".

        The LocalStack detection is defensive: it checks the actual boto3 endpoint
        URL configuration rather than environment variables or test mode flags.
        This approach isolates test-specific behavior to clearly documented
        locations while preserving standard AWS behavior for production users.

        Returns
        -------
        bool
            True if endpoint URL contains 'localstack' or ':4566' (default
            LocalStack port), False otherwise
        """
        endpoint = self.ec2_client.meta.endpoint_url
        return endpoint is not None and (
            "localstack" in endpoint.lower() or ":4566" in endpoint
        )

    def resolve_ami(self, config: dict[str, Any]) -> str:
        """Resolve AMI ID from configuration.

        Supports three modes of AMI selection with priority order:
        1. Direct AMI ID specification (ami.image_id)
        2. AMI query with filters (ami.query)
        3. Default Amazon Ubuntu 24 x86_64 if no ami section

        Parameters
        ----------
        config : dict[str, Any]
            Configuration dictionary containing optional ami section

        Returns
        -------
        str
            AMI ID to use for instance launch

        Raises
        ------
        ValueError
            If both image_id and query are specified, if image_id format is
            invalid, if query.name is missing, if architecture is invalid,
            or if query matches no AMIs
        """
        ami_config = config.get("ami", {})

        if "image_id" in ami_config and "query" in ami_config:
            raise ValueError(
                "Cannot specify both 'ami.image_id' and 'ami.query'. "
                "Use image_id for a specific AMI or query to search for the latest."
            )

        if "image_id" in ami_config:
            ami_id = ami_config["image_id"]
            if not re.match(r"^ami-[0-9a-f]{8,17}$", ami_id):
                raise ValueError(f"Invalid AMI ID format: '{ami_id}'")
            return ami_id

        if "query" in ami_config:
            query = ami_config["query"]

            if "name" not in query:
                raise ValueError("ami.query.name is required")

            return self.find_ami_by_query(
                name_pattern=query["name"],
                owner=query.get("owner"),
                architecture=query.get("architecture"),
            )

        if self._is_localstack_endpoint():
            return self.find_ami_by_query(
                name_pattern="*Ubuntu 24*",
                owner=None,
                architecture="x86_64",
            )

        return self.find_ami_by_query(
            name_pattern="*Ubuntu 24*",
            owner="amazon",
            architecture="x86_64",
        )

    def find_ami_by_query(
        self,
        name_pattern: str,
        owner: str | None = None,
        architecture: str | None = None,
    ) -> str:
        """Query AWS for AMI matching pattern and return newest by CreationDate.

        Parameters
        ----------
        name_pattern : str
            AMI name pattern (supports * and ? wildcards)
        owner : str | None
            AWS account ID or alias (e.g., "099720109477", "amazon")
        architecture : str | None
            CPU architecture: "x86_64" or "arm64"

        Returns
        -------
        str
            Image ID of the newest matching AMI

        Raises
        ------
        ValueError
            If architecture is invalid or no AMIs match the filters
        """
        filters = [
            {"Name": "name", "Values": [name_pattern]},
            {"Name": "state", "Values": ["available"]},
        ]

        if architecture:
            if architecture not in ("x86_64", "arm64"):
                raise ValueError(
                    f"Invalid architecture: '{architecture}'. Must be 'x86_64' or 'arm64'"
                )
            if not self._is_localstack_endpoint():
                filters.append({"Name": "architecture", "Values": [architecture]})

        kwargs: dict[str, Any] = {"Filters": filters}
        if owner:
            if not self._is_localstack_endpoint():
                kwargs["Owners"] = [owner]

        response = self.ec2_client.describe_images(**kwargs)

        if not response["Images"]:
            owner_msg = f"owner={owner}, " if owner else ""
            arch_msg = f"architecture={architecture}, " if architecture else ""
            raise ValueError(
                f"No AMI found for {owner_msg}{arch_msg}name={name_pattern}"
            )

        images = sorted(
            response["Images"],
            key=lambda x: x["CreationDate"],
            reverse=True,
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
            raise ValueError(f"No default VPC found in region '{self.region}'")

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

    def launch_instance(
        self, config: dict[str, Any], instance_name: str | None = None
    ) -> dict[str, Any]:
        """Launch EC2 instance based on configuration.

        Parameters
        ----------
        config : dict[str, Any]
            Merged configuration from ConfigLoader
        instance_name : str | None
            Optional instance name for Name tag. If None, uses timestamp-based name.

        Returns
        -------
        dict[str, Any]
            Instance details: {instance_id, public_ip, state, key_file, unique_id,
            security_group_id}

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

        ami_id = self.resolve_ami(config)
        unique_id = str(int(time.time()))
        machine_name = config.get("machine_name", "ad-hoc")

        instance_tag_name = instance_name if instance_name else f"moondock-{unique_id}"

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
                            {"Key": "Name", "Value": instance_tag_name},
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

            public_ip = instance.public_ip_address
            if self._is_localstack_endpoint():
                public_ip = None

            return {
                "instance_id": instance_id,
                "public_ip": public_ip,
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
                        "Failed to delete security group during rollback: "
                        f"{cleanup_error}"
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
                ec2_client = self.boto3_client_factory("ec2", region_name=self.region)
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
                regional_ec2 = self.boto3_client_factory("ec2", region_name=region)

                paginator = regional_ec2.get_paginator("describe_instances")
                page_iterator = paginator.paginate(
                    Filters=[
                        {"Name": "tag:ManagedBy", "Values": ["moondock"]},
                        {
                            "Name": "instance-state-name",
                            "Values": ACTIVE_INSTANCE_STATES,
                        },
                    ]
                )

                for page in page_iterator:
                    for reservation in page["Reservations"]:
                        for instance in reservation["Instances"]:
                            tags = {
                                tag["Key"]: tag["Value"]
                                for tag in instance.get("Tags", [])
                            }

                            instances.append(
                                {
                                    "instance_id": instance["InstanceId"],
                                    "name": tags.get("Name", "N/A"),
                                    "state": instance["State"]["Name"],
                                    "region": region,
                                    "instance_type": instance["InstanceType"],
                                    "launch_time": instance["LaunchTime"],
                                    "machine_config": tags.get(
                                        "MachineConfig", "ad-hoc"
                                    ),
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
        """Find moondock-managed instances matching ID, Name tag, or MachineConfig.

        Parameters
        ----------
        name_or_id : str
            EC2 instance ID, Name tag, or MachineConfig name to search for
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

        name_matches = [inst for inst in instances if inst["name"] == name_or_id]

        if name_matches:
            return name_matches

        return [inst for inst in instances if inst["machine_config"] == name_or_id]

    def stop_instance(self, instance_id: str) -> dict[str, Any]:
        """Stop EC2 instance and wait for stopped state.

        Parameters
        ----------
        instance_id : str
            Instance ID to stop

        Returns
        -------
        dict[str, Any]
            Instance details with normalized keys: instance_id, public_ip,
            private_ip, state, instance_type

        Raises
        ------
        RuntimeError
            If instance fails to reach stopped state within timeout
        """
        logger.info(f"Stopping instance {instance_id}...")

        self.ec2_client.stop_instances(InstanceIds=[instance_id])

        try:
            waiter = self.ec2_client.get_waiter("instance_stopped")
            waiter.wait(
                InstanceIds=[instance_id], WaiterConfig={"Delay": 15, "MaxAttempts": 40}
            )
        except WaiterError as e:
            raise RuntimeError(f"Failed to stop instance: {e}") from e

        response = self.ec2_client.describe_instances(InstanceIds=[instance_id])
        instance = response["Reservations"][0]["Instances"][0]

        logger.info(f"Instance {instance_id} stopped")
        return {
            "instance_id": instance_id,
            "public_ip": instance.get("PublicIpAddress"),
            "private_ip": instance.get("PrivateIpAddress"),
            "state": instance["State"]["Name"],
            "instance_type": instance.get("InstanceType"),
        }

    def start_instance(self, instance_id: str) -> dict[str, Any]:
        """Start EC2 instance and wait for running state.

        Parameters
        ----------
        instance_id : str
            Instance ID to start

        Returns
        -------
        dict[str, Any]
            Instance details with normalized keys: instance_id, public_ip,
            private_ip, state, instance_type

        Raises
        ------
        RuntimeError
            If instance fails to reach running state within timeout or
            if instance is not in stopped state
        """
        logger.info(f"Starting instance {instance_id}...")

        response = self.ec2_client.describe_instances(InstanceIds=[instance_id])
        instance = response["Reservations"][0]["Instances"][0]
        current_state = instance["State"]["Name"]

        if current_state == "running":
            logger.info(f"Instance {instance_id} is already running")
            return {
                "instance_id": instance_id,
                "public_ip": instance.get("PublicIpAddress"),
                "private_ip": instance.get("PrivateIpAddress"),
                "state": current_state,
                "instance_type": instance.get("InstanceType"),
            }

        if current_state != "stopped":
            raise RuntimeError(
                f"Instance is not in stopped state. Current state: {current_state}. "
                "Please wait for instance to reach stopped state."
            )

        self.ec2_client.start_instances(InstanceIds=[instance_id])

        try:
            waiter = self.ec2_client.get_waiter("instance_running")
            waiter.wait(
                InstanceIds=[instance_id], WaiterConfig={"Delay": 15, "MaxAttempts": 20}
            )
        except WaiterError as e:
            raise RuntimeError(f"Failed to start instance: {e}") from e

        response = self.ec2_client.describe_instances(InstanceIds=[instance_id])
        instance = response["Reservations"][0]["Instances"][0]

        new_ip = instance.get("PublicIpAddress")
        logger.info(f"Instance {instance_id} started with IP {new_ip}")

        return {
            "instance_id": instance_id,
            "public_ip": instance.get("PublicIpAddress"),
            "private_ip": instance.get("PrivateIpAddress"),
            "state": instance["State"]["Name"],
            "instance_type": instance.get("InstanceType"),
        }

    def get_volume_size(self, instance_id: str) -> int | None:
        """Get root volume size for instance in GB.

        Parameters
        ----------
        instance_id : str
            Instance ID to get volume size for

        Returns
        -------
        int | None
            Volume size in GB, or None if instance has no block device mappings

        Raises
        ------
        RuntimeError
            If instance has no root volume or volume information cannot be retrieved
        """
        response = self.ec2_client.describe_instances(InstanceIds=[instance_id])
        instance = response["Reservations"][0]["Instances"][0]

        block_device_mappings = instance.get("BlockDeviceMappings", [])
        if not block_device_mappings:
            logger.warning(f"Instance {instance_id} has no block device mappings")
            return None

        volume_id = block_device_mappings[0].get("Ebs", {}).get("VolumeId")
        if not volume_id:
            raise RuntimeError(f"Instance {instance_id} has no root volume")

        try:
            volumes_response = self.ec2_client.describe_volumes(VolumeIds=[volume_id])
            volume = volumes_response["Volumes"][0]
            size = volume.get("Size", 0)
            logger.info(f"Instance {instance_id} has root volume size {size}GB")
            return size
        except ClientError as e:
            raise RuntimeError(
                f"Failed to get volume size for {instance_id}: {e}"
            ) from e

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
