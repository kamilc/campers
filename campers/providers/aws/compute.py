"""EC2 instance management for campers."""

import logging
import os
import time
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import (
    ClientError,
    NoCredentialsError,
    WaiterError,
)

from campers.constants import (
    WAITER_DELAY_SECONDS,
    WAITER_MAX_ATTEMPTS_LONG,
    WAITER_MAX_ATTEMPTS_SHORT,
    SSH_IP_RETRY_DELAY,
    SSH_IP_RETRY_MAX,
)
from campers.providers.exceptions import (
    ProviderAPIError,
    ProviderConnectionError,
    ProviderCredentialsError,
)
from campers.providers.aws.utils import extract_instance_from_response
from campers.providers.aws.errors import handle_aws_errors
from campers.providers.aws.ami import AMIResolver
from campers.providers.aws.keypair import KeyPairManager
from campers.providers.aws.network import NetworkManager

logger = logging.getLogger(__name__)

ACTIVE_INSTANCE_STATES = ["pending", "running", "stopping", "stopped"]


VALID_INSTANCE_TYPES = frozenset(
    (
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
    )
)


class EC2Manager:
    """Manage EC2 instance lifecycle for campers."""

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

        self.ami_resolver = AMIResolver(self.ec2_client, region)
        self.keypair_manager = KeyPairManager(self.ec2_client, region)
        self.network_manager = NetworkManager(self.ec2_client, region)

    def validate_region(self, region: str) -> None:
        """Validate that a region string is a valid AWS region.

        Parameters
        ----------
        region : str
            AWS region string to validate

        Raises
        ------
        ValueError
            If region is not a valid AWS region
        """
        try:
            ec2_client = self.boto3_client_factory("ec2", region_name="us-east-1")
            regions_response = ec2_client.describe_regions()
            valid_regions = {r["RegionName"] for r in regions_response["Regions"]}

            if region not in valid_regions:
                raise ValueError(
                    f"Invalid region: '{region}'. "
                    f"Valid regions: {', '.join(sorted(valid_regions))}"
                )
        except NoCredentialsError as e:
            logger.warning(
                "Unable to validate region '%s' (%s). Proceeding without validation.",
                region,
                e.__class__.__name__,
            )
        except ClientError as e:
            logger.warning(
                "Unable to validate region '%s' (%s). Proceeding without validation.",
                region,
                e.__class__.__name__,
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
        return self.ami_resolver.resolve_ami(config)

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
        return self.ami_resolver.find_ami_by_query(
            name_pattern=name_pattern,
            owner=owner,
            architecture=architecture,
        )

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
        return self.keypair_manager.create_key_pair(unique_id)

    def create_security_group(
        self, unique_id: str, ssh_allowed_cidr: str | None = None
    ) -> str:
        """Create security group with SSH access.

        Parameters
        ----------
        unique_id : str
            Unique identifier to use in security group name
        ssh_allowed_cidr : str | None
            CIDR block for SSH access. If None, defaults to 0.0.0.0/0

        Returns
        -------
        str
            Security group ID
        """
        return self.network_manager.create_security_group(unique_id, ssh_allowed_cidr)

    def _check_region_mismatch(self, camp_name: str, target_region: str) -> None:
        """Check if an existing instance with same camp name exists in another region.

        Parameters
        ----------
        camp_name : str
            Camp name to check for
        target_region : str
            Target region for the new instance

        Raises
        ------
        RuntimeError
            If an existing instance with the same camp name exists in a different region
        """
        if camp_name == "ad-hoc":
            return

        existing_instances = self.find_instances_by_name_or_id(camp_name)

        for instance in existing_instances:
            if (
                instance["region"] != target_region
                and instance["camp_config"] == camp_name
            ):
                raise RuntimeError(
                    f"An instance for camp '{camp_name}' already exists in region "
                    f"'{instance['region']}', but you are trying to launch in region "
                    f"'{target_region}'. Please use the existing instance or terminate "
                    f"it first if you want to launch in a different region."
                )

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
            If instance fails to reach running state within timeout, if an
            existing instance with the same camp name exists in a different region,
            or if instance launch fails
        ValueError
            If instance type is invalid
        """
        self._validate_instance_type(config["instance_type"])

        camp_name = config.get("camp_name", "ad-hoc")
        self._check_region_mismatch(camp_name, config.get("region", self.region))

        resources = self._prepare_launch_resources(config, instance_name)

        try:
            instance_details = self._launch_ec2_instance(config, resources)
            return instance_details
        except Exception as e:
            self._rollback_resources(resources)
            raise RuntimeError(f"Failed to launch instance: {e}") from e

    def _validate_instance_type(self, instance_type: str) -> None:
        """Validate that instance type is supported.

        Parameters
        ----------
        instance_type : str
            Instance type to validate

        Raises
        ------
        ValueError
            If instance type is invalid
        """
        if instance_type not in VALID_INSTANCE_TYPES:
            raise ValueError(
                f"Invalid instance type: {instance_type}. "
                f"Must be one of: {', '.join(sorted(VALID_INSTANCE_TYPES))}"
            )

    def _prepare_launch_resources(
        self, config: dict[str, Any], instance_name: str | None
    ) -> dict[str, Any]:
        """Prepare resources for instance launch (key pair and security group).

        Parameters
        ----------
        config : dict[str, Any]
            Merged configuration
        instance_name : str | None
            Instance name for tags

        Returns
        -------
        dict[str, Any]
            Dictionary containing prepared resources: key_name, key_file, sg_id,
            ami_id, unique_id, instance_tag_name, instance_type
        """
        ami_id = self.resolve_ami(config)
        unique_id = str(int(time.time()))
        instance_tag_name = instance_name if instance_name else f"campers-{unique_id}"

        key_name, key_file = self.create_key_pair(unique_id)

        ssh_allowed_cidr = config.get("ssh_allowed_cidr")
        sg_id = self.create_security_group(unique_id, ssh_allowed_cidr)

        return {
            "key_name": key_name,
            "key_file": key_file,
            "sg_id": sg_id,
            "ami_id": ami_id,
            "unique_id": unique_id,
            "instance_tag_name": instance_tag_name,
            "instance_type": config["instance_type"],
            "disk_size": config["disk_size"],
            "camp_name": config.get("camp_name", "ad-hoc"),
            "instance": None,
        }

    def _launch_ec2_instance(
        self, config: dict[str, Any], resources: dict[str, Any]
    ) -> dict[str, Any]:
        """Launch EC2 instance and wait for it to be running.

        Parameters
        ----------
        config : dict[str, Any]
            Merged configuration
        resources : dict[str, Any]
            Prepared resources from _prepare_launch_resources

        Returns
        -------
        dict[str, Any]
            Instance details dictionary
        """
        instances = self.ec2_resource.create_instances(
            ImageId=resources["ami_id"],
            InstanceType=resources["instance_type"],
            KeyName=resources["key_name"],
            SecurityGroupIds=[resources["sg_id"]],
            MinCount=1,
            MaxCount=1,
            BlockDeviceMappings=[
                {
                    "DeviceName": "/dev/sda1",
                    "Ebs": {
                        "VolumeSize": resources["disk_size"],
                        "VolumeType": "gp3",
                        "DeleteOnTermination": True,
                    },
                }
            ],
            TagSpecifications=[
                {
                    "ResourceType": "instance",
                    "Tags": [
                        {"Key": "ManagedBy", "Value": "campers"},
                        {"Key": "Name", "Value": resources["instance_tag_name"]},
                        {"Key": "MachineConfig", "Value": resources["camp_name"]},
                        {"Key": "UniqueId", "Value": resources["unique_id"]},
                    ],
                }
            ],
        )

        instance = instances[0]
        resources["instance"] = instance
        instance_id = instance.id

        waiter = self.ec2_client.get_waiter("instance_running")
        waiter.wait(
            InstanceIds=[instance_id],
            WaiterConfig={
                "Delay": WAITER_DELAY_SECONDS,
                "MaxAttempts": WAITER_MAX_ATTEMPTS_SHORT,
            },
        )
        instance.reload()

        return {
            "instance_id": instance_id,
            "public_ip": instance.public_ip_address,
            "state": instance.state["Name"],
            "key_file": str(resources["key_file"]),
            "security_group_id": resources["sg_id"],
            "unique_id": resources["unique_id"],
            "launch_time": instance.launch_time,
        }

    def _rollback_resources(self, resources: dict[str, Any]) -> None:
        """Clean up resources after failed launch.

        Parameters
        ----------
        resources : dict[str, Any]
            Resources dictionary from _prepare_launch_resources
        """
        instance = resources.get("instance")
        if instance:
            try:
                instance.terminate()
            except ClientError as cleanup_error:
                logger.warning(
                    "Failed to terminate instance during rollback: %s",
                    cleanup_error,
                )

        sg_id = resources.get("sg_id")
        if sg_id:
            try:
                self.ec2_client.delete_security_group(GroupId=sg_id)
            except ClientError as cleanup_error:
                logger.warning(
                    "Failed to delete security group during rollback: %s",
                    cleanup_error,
                )

        key_name = resources.get("key_name")
        if key_name:
            try:
                self.ec2_client.delete_key_pair(KeyName=key_name)
            except ClientError as cleanup_error:
                logger.warning(
                    "Failed to delete key pair during rollback: %s", cleanup_error
                )

        key_file = resources.get("key_file")
        if key_file and key_file.exists():
            try:
                key_file.unlink()
            except OSError as cleanup_error:
                logger.warning(
                    "Failed to delete key file during rollback: %s", cleanup_error
                )

    def list_instances(self, region_filter: str | None = None) -> list[dict[str, Any]]:
        """List all campers-managed instances across regions.

        Parameters
        ----------
        region_filter : str | None
            Optional AWS region to filter results (e.g., "us-east-1")
            If None, queries all regions

        Returns
        -------
        list[dict[str, Any]]
            List of instance dictionaries with keys: instance_id, name, state,
            region, instance_type, launch_time, camp_config

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
                with handle_aws_errors():
                    ec2_client = self.boto3_client_factory(
                        "ec2", region_name=self.region
                    )
                    regions_response = ec2_client.describe_regions()
                    regions = [r["RegionName"] for r in regions_response["Regions"]]
            except ProviderCredentialsError:
                raise
            except (ProviderAPIError, ProviderConnectionError) as e:
                logger.warning(
                    f"Unable to query all AWS regions ({e.__class__.__name__}), "
                    f"falling back to default region '{self.region}' only. "
                    f"Use --region flag to query specific regions."
                )
                regions = [self.region]

        instances = []

        for region in regions:
            try:
                with handle_aws_errors():
                    regional_ec2 = self.boto3_client_factory("ec2", region_name=region)

                    paginator = regional_ec2.get_paginator("describe_instances")
                    page_iterator = paginator.paginate(
                        Filters=[
                            {"Name": "tag:ManagedBy", "Values": ["campers"]},
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
                                        "camp_config": tags.get(
                                            "MachineConfig", "ad-hoc"
                                        ),
                                    }
                                )
            except ProviderCredentialsError:
                raise
            except ProviderAPIError as e:
                logger.warning(f"Failed to query region {region}: {e}")
                continue
            except ProviderConnectionError as e:
                logger.warning(f"Failed to query region {region}: {e}")
                continue

        seen = set()
        unique_instances = []
        for instance in instances:
            instance_id = instance["instance_id"]
            if instance_id not in seen:
                seen.add(instance_id)
                unique_instances.append(instance)

        unique_instances.sort(key=lambda x: x["launch_time"], reverse=True)

        return unique_instances

    def find_instances_by_name_or_id(
        self, name_or_id: str, region_filter: str | None = None
    ) -> list[dict[str, Any]]:
        """Find campers-managed instances matching ID, Name tag, or MachineConfig.

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
            region, instance_type, launch_time, camp_config
        """
        instances = self.list_instances(region_filter=region_filter)

        id_matches = [inst for inst in instances if inst["instance_id"] == name_or_id]

        if id_matches:
            return id_matches

        name_matches = [inst for inst in instances if inst["name"] == name_or_id]

        if name_matches:
            return name_matches

        return [inst for inst in instances if inst["camp_config"] == name_or_id]

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
                InstanceIds=[instance_id],
                WaiterConfig={
                    "Delay": WAITER_DELAY_SECONDS,
                    "MaxAttempts": WAITER_MAX_ATTEMPTS_LONG,
                },
            )
        except WaiterError as e:
            raise RuntimeError(f"Failed to stop instance: {e}") from e

        response = self.ec2_client.describe_instances(InstanceIds=[instance_id])
        instance = extract_instance_from_response(response)

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
        instance = extract_instance_from_response(response)
        current_state = instance["State"]["Name"]

        if current_state == "running":
            logger.info(f"Instance {instance_id} is already running")
            return {
                "instance_id": instance_id,
                "public_ip": instance.get("PublicIpAddress"),
                "private_ip": instance.get("PrivateIpAddress"),
                "state": current_state,
                "instance_type": instance.get("InstanceType"),
                "launch_time": instance.get("LaunchTime"),
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
                InstanceIds=[instance_id],
                WaiterConfig={
                    "Delay": WAITER_DELAY_SECONDS,
                    "MaxAttempts": WAITER_MAX_ATTEMPTS_SHORT,
                },
            )
        except WaiterError as e:
            raise RuntimeError(f"Failed to start instance: {e}") from e

        max_retries = SSH_IP_RETRY_MAX
        instance = None
        for attempt in range(max_retries):
            response = self.ec2_client.describe_instances(InstanceIds=[instance_id])
            instance = extract_instance_from_response(response)
            state = instance["State"]["Name"]
            if state == "running":
                break
            if attempt < max_retries - 1:
                time.sleep(SSH_IP_RETRY_DELAY)

        new_ip = instance.get("PublicIpAddress")
        logger.info(f"Instance {instance_id} started with IP {new_ip}")

        unique_id = None
        tags = instance.get("Tags", [])
        for tag in tags:
            if tag["Key"] == "UniqueId":
                unique_id = tag["Value"]
                break

        key_file = None
        if unique_id:
            campers_dir = Path(os.environ.get("CAMPERS_DIR", "~/.campers")).expanduser()
            key_file = str(campers_dir / "keys" / f"{unique_id}.pem")

        return {
            "instance_id": instance_id,
            "public_ip": instance.get("PublicIpAddress"),
            "private_ip": instance.get("PrivateIpAddress"),
            "state": instance["State"]["Name"],
            "instance_type": instance.get("InstanceType"),
            "unique_id": unique_id,
            "key_file": key_file,
            "launch_time": instance.get("LaunchTime"),
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
        instance = extract_instance_from_response(response)

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

    def get_instance_tags(self, instance_id: str) -> dict[str, str]:
        """Get tags for an instance.

        Parameters
        ----------
        instance_id : str
            Instance ID

        Returns
        -------
        dict[str, str]
            Dictionary mapping tag keys to values
        """
        try:
            response = self.ec2_client.describe_instances(InstanceIds=[instance_id])
            instance = extract_instance_from_response(response)
            tags = instance.get("Tags", [])
            return {tag["Key"]: tag["Value"] for tag in tags}
        except (ClientError, IndexError, KeyError) as e:
            logger.warning(f"Failed to get tags for instance {instance_id}: {e}")
            return {}

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
                InstanceIds=[instance_id],
                WaiterConfig={
                    "Delay": WAITER_DELAY_SECONDS,
                    "MaxAttempts": WAITER_MAX_ATTEMPTS_LONG,
                },
            )
        except WaiterError as e:
            raise RuntimeError(f"Failed to terminate instance: {e}") from e

        if unique_id:
            try:
                self.ec2_client.delete_key_pair(KeyName=f"campers-{unique_id}")
            except ClientError as e:
                logger.debug("Failed to delete key pair during cleanup: %s", e)

            campers_dir = os.environ.get("CAMPERS_DIR", str(Path.home() / ".campers"))
            key_file = Path(campers_dir) / "keys" / f"{unique_id}.pem"

            if key_file.exists():
                key_file.unlink()

        if sg_id:
            try:
                self.ec2_client.delete_security_group(GroupId=sg_id)
            except ClientError as e:
                logger.debug("Failed to delete security group during cleanup: %s", e)
