"""EC2 instance management for campers."""

import logging
import os
import re
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import (
    ClientError,
    ConnectTimeoutError,
    EndpointConnectionError,
    NoCredentialsError,
    WaiterError,
)
from tenacity import RetryError, retry, stop_after_attempt, wait_exponential

from campers.providers.aws.ami import AMIResolver
from campers.providers.aws.constants import (
    ACTIVE_INSTANCE_STATES,
    SSH_IP_RETRY_DELAY,
    SSH_IP_RETRY_MAX,
    UUID_SLICE_LENGTH,
    VALID_INSTANCE_TYPES,
    WAITER_DELAY_SECONDS,
    WAITER_MAX_ATTEMPTS_LONG,
    WAITER_MAX_ATTEMPTS_SHORT,
)
from campers.providers.aws.errors import handle_aws_errors
from campers.providers.aws.keypair import KeyPairInfo, KeyPairManager
from campers.providers.aws.network import NetworkManager, delete_security_group_with_retry
from campers.providers.aws.utils import (
    extract_instance_from_response,
    extract_tag_value,
    tags_to_dict,
)
from campers.providers.exceptions import (
    ProviderAPIError,
    ProviderConnectionError,
    ProviderCredentialsError,
)

logger = logging.getLogger(__name__)


class EC2Manager:
    """Manage EC2 instance lifecycle for campers."""

    def __init__(
        self,
        region: str,
        boto3_client_factory: Callable[..., Any] | None = None,
        boto3_resource_factory: Callable[..., Any] | None = None,
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

        Raises
        ------
        ValueError
            If region format is invalid
        """
        self._validate_region_format(region)
        self.region = region
        self.boto3_client_factory = boto3_client_factory or boto3.client
        self.boto3_resource_factory = boto3_resource_factory or boto3.resource
        self.ec2_client = self.boto3_client_factory("ec2", region_name=region)
        self.ec2_resource = self.boto3_resource_factory("ec2", region_name=region)

        self.ami_resolver = AMIResolver(self.ec2_client, region)
        self.keypair_manager = KeyPairManager(self.ec2_client, region)
        self.network_manager = NetworkManager(self.ec2_client, region)

    def __enter__(self) -> "EC2Manager":
        """Enter context manager.

        Returns
        -------
        EC2Manager
            Self for use in with statement
        """
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context manager and close resources.

        Parameters
        ----------
        exc_type : Any
            Exception type if an exception was raised
        exc_val : Any
            Exception value if an exception was raised
        exc_tb : Any
            Exception traceback if an exception was raised
        """
        self.close()

    def close(self) -> None:
        """Close boto3 clients and release resources.

        This method safely closes both EC2 client and resource connections.
        Errors during closing are logged but do not raise exceptions.
        """
        try:
            if hasattr(self, "ec2_client") and self.ec2_client is not None:
                self.ec2_client.close()
        except (AttributeError, OSError) as e:
            logger.debug("Error closing EC2 client: %s", e)

        try:
            if (
                hasattr(self, "ec2_resource")
                and self.ec2_resource is not None
                and hasattr(self.ec2_resource, "meta")
                and hasattr(self.ec2_resource.meta, "client")
            ):
                self.ec2_resource.meta.client.close()
        except (AttributeError, OSError) as e:
            logger.debug("Error closing EC2 resource client: %s", e)

    def _validate_region_format(self, region: str) -> None:
        """Validate AWS region format.

        AWS regions follow the pattern: {area}-{direction}{number}
        Examples: us-east-1, eu-west-2, ap-southeast-1

        Parameters
        ----------
        region : str
            Region string to validate

        Raises
        ------
        ValueError
            If region format is invalid
        """
        region_pattern = r"^[a-z]{2}-[a-z]+-\d[a-z]?$"
        if not re.match(region_pattern, region):
            raise ValueError(
                f"Invalid AWS region format: '{region}'. "
                f"Region must match format like 'us-east-1', 'eu-west-2', etc."
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

    def create_key_pair(self, unique_id: str) -> KeyPairInfo:
        """Create SSH key pair and save to disk.

        Parameters
        ----------
        unique_id : str
            Unique identifier to use in key name (timestamp)

        Returns
        -------
        KeyPairInfo
            Key pair information with name and file path
        """
        return self.keypair_manager.create_key_pair(unique_id)

    def create_security_group(
        self,
        unique_id: str,
        ssh_allowed_cidr: str | None = None,
        public_ports: list[int] | None = None,
        public_ports_allowed_cidr: str | None = None,
        project_name: str | None = None,
        branch: str | None = None,
        camp_name: str | None = None,
    ) -> str:
        """Create security group with SSH access and optional public ports.

        Parameters
        ----------
        unique_id : str
            Unique identifier to use in security group name
        ssh_allowed_cidr : str | None
            CIDR block for SSH access. If None, defaults to 0.0.0.0/0
        public_ports : list[int] | None
            List of ports to open for public access (optional)
        public_ports_allowed_cidr : str | None
            CIDR block for public ports access (optional)
        project_name : str | None
            Project name for naming convention
        branch : str | None
            Branch name for naming convention
        camp_name : str | None
            Camp name for naming convention

        Returns
        -------
        str
            Security group ID
        """
        return self.network_manager.create_security_group(
            unique_id,
            ssh_allowed_cidr,
            public_ports,
            public_ports_allowed_cidr,
            project_name,
            branch,
            camp_name,
        )

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
            if instance["region"] != target_region and instance["camp_config"] == camp_name:
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
        except (ClientError, NoCredentialsError, WaiterError) as e:
            self._rollback_resources(resources)
            if isinstance(e, NoCredentialsError):
                raise ProviderCredentialsError(
                    "AWS credentials not configured for EC2 instance launch"
                ) from e
            raise ProviderAPIError(f"Failed to launch instance: {e}") from e
        except RuntimeError:
            self._rollback_resources(resources)
            raise

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
            ami_id, unique_id, instance_tag_name, instance_type, owner
        """
        from campers.utils import get_git_branch, get_git_project_name, get_user_identity

        ami_id = self.resolve_ami(config)
        unique_id = str(uuid.uuid4())[:UUID_SLICE_LENGTH]
        instance_tag_name = instance_name if instance_name else f"campers-{unique_id}"

        key_pair_info = self.create_key_pair(unique_id)
        key_name = key_pair_info.name
        key_file = key_pair_info.file_path

        ssh_allowed_cidr = config.get("ssh_allowed_cidr")
        public_ports = config.get("public_ports")
        public_ports_allowed_cidr = config.get("public_ports_allowed_cidr")
        project_name = get_git_project_name()
        branch = get_git_branch()
        camp_name = config.get("camp_name")
        sg_id = self.create_security_group(
            unique_id,
            ssh_allowed_cidr,
            public_ports,
            public_ports_allowed_cidr,
            project_name,
            branch,
            camp_name,
        )

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
            "owner": get_user_identity(),
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
                        {"Key": "Owner", "Value": resources["owner"]},
                    ],
                }
            ],
        )

        if not instances:
            raise RuntimeError("No instances created by AWS")

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
                logger.debug("Instance terminated successfully during rollback")
            except ClientError as cleanup_error:
                logger.warning(
                    "Failed to terminate instance during rollback: %s",
                    cleanup_error,
                )

        sg_id = resources.get("sg_id")
        if sg_id:
            if delete_security_group_with_retry(self.ec2_client, sg_id):
                logger.debug("Security group %s deleted successfully during rollback", sg_id)
            else:
                logger.warning(
                    "Failed to delete security group %s during rollback after retries",
                    sg_id,
                )

        key_name = resources.get("key_name")
        if key_name:
            try:
                self.ec2_client.delete_key_pair(KeyName=key_name)
                logger.debug("Key pair %s deleted successfully during rollback", key_name)
            except ClientError as cleanup_error:
                logger.warning("Failed to delete key pair during rollback: %s", cleanup_error)

        key_file = resources.get("key_file")
        if key_file and key_file.exists():
            try:
                key_file.unlink()
                logger.debug("Key file %s deleted successfully during rollback", key_file)
            except OSError as cleanup_error:
                logger.warning("Failed to delete key file during rollback: %s", cleanup_error)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    def describe_regions(self) -> list[str]:
        """Get list of available AWS regions with retry logic.

        Returns
        -------
        list[str]
            List of region names

        Raises
        ------
        Exception
            If describe_regions API call fails after all retries
        """
        ec2_client = self.boto3_client_factory("ec2", region_name=self.region)
        try:
            regions_response = ec2_client.describe_regions()
            return [r["RegionName"] for r in regions_response["Regions"]]
        finally:
            ec2_client.close()

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
                    regions = self.describe_regions()
            except ProviderCredentialsError:
                raise
            except (ProviderAPIError, ProviderConnectionError) as e:
                logger.warning(
                    "Unable to query all AWS regions (%s), "
                    "falling back to default region '%s' only. "
                    "Use --region flag to query specific regions.",
                    e.__class__.__name__,
                    self.region,
                )
                regions = [self.region]
            except RetryError as e:
                logger.warning(
                    "Unable to query all AWS regions (retries exhausted), "
                    "falling back to default region '%s' only. "
                    "Use --region flag to query specific regions. Error: %s",
                    self.region,
                    e,
                )
                regions = [self.region]

        instances = []

        for region in regions:
            regional_ec2 = None
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
                                tags = tags_to_dict(instance.get("Tags", []))

                                instances.append(
                                    {
                                        "instance_id": instance["InstanceId"],
                                        "name": tags.get("Name", "N/A"),
                                        "state": instance["State"]["Name"],
                                        "region": region,
                                        "instance_type": instance["InstanceType"],
                                        "launch_time": instance["LaunchTime"],
                                        "camp_config": tags.get("MachineConfig", "ad-hoc"),
                                        "owner": tags.get("Owner", "unknown"),
                                    }
                                )
            except ProviderCredentialsError:
                raise
            except ProviderAPIError as e:
                logger.warning("Failed to query region %s: %s", region, e)
                continue
            except ProviderConnectionError as e:
                logger.warning("Failed to query region %s: %s", region, e)
                continue
            finally:
                if regional_ec2 is not None:
                    try:
                        regional_ec2.close()
                    except (AttributeError, OSError) as e:
                        logger.debug("Failed to close regional EC2 client for %s: %s", region, e)

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
        ProviderAPIError
            If AWS API call fails
        """
        logger.info("Stopping instance %s...", instance_id)

        with handle_aws_errors():
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

        logger.info("Instance %s stopped", instance_id)
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
        logger.info("Starting instance %s...", instance_id)

        response = self.ec2_client.describe_instances(InstanceIds=[instance_id])
        instance = extract_instance_from_response(response)
        current_state = instance["State"]["Name"]

        if current_state == "running":
            logger.info("Instance %s is already running", instance_id)
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
        logger.info("Instance %s started with IP %s", instance_id, new_ip)

        tags = instance.get("Tags", [])
        unique_id = extract_tag_value(tags, "UniqueId")

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
            logger.warning("Instance %s has no block device mappings", instance_id)
            return None

        block_device = block_device_mappings[0]
        ebs = block_device.get("Ebs") if block_device else None
        volume_id = ebs.get("VolumeId") if ebs else None
        if not volume_id:
            raise RuntimeError(f"Instance {instance_id} has no root volume")

        try:
            volumes_response = self.ec2_client.describe_volumes(VolumeIds=[volume_id])
            volumes = volumes_response.get("Volumes", [])
            if not volumes:
                raise RuntimeError(f"Volume {volume_id} not found")
            volume = volumes[0]
            size = volume.get("Size", 0)
            logger.info("Instance %s has root volume size %sGB", instance_id, size)
            return size
        except ClientError as e:
            raise RuntimeError(f"Failed to get volume size for {instance_id}: {e}") from e

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
            return tags_to_dict(tags)
        except (ClientError, IndexError, KeyError) as e:
            logger.warning("Failed to get tags for instance %s: %s", instance_id, e)
            return {}

    def validate_region(self, region: str) -> bool:
        """Validate if a region is available for AWS.

        Parameters
        ----------
        region : str
            Region identifier to validate

        Returns
        -------
        bool
            True if region is valid, False otherwise
        """
        ec2 = None
        try:
            config = Config(
                connect_timeout=5, read_timeout=30, retries={"max_attempts": 3, "mode": "adaptive"}
            )
            ec2 = boto3.client("ec2", region_name=region, config=config)
            ec2.describe_regions(RegionNames=[region])
            return True
        except (ClientError, NoCredentialsError, EndpointConnectionError, ConnectTimeoutError) as e:
            logger.warning("Unable to validate region %s: %s", region, e)
            return False
        finally:
            if ec2:
                ec2.close()

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

        unique_id = extract_tag_value(instance.tags or [], "UniqueId")

        sg_id = instance.security_groups[0]["GroupId"] if instance.security_groups else None

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
            raise ProviderAPIError(f"Failed to terminate instance: {e}") from e

        if unique_id:
            try:
                self.ec2_client.delete_key_pair(KeyName=f"campers-{unique_id}")
            except ClientError as e:
                logger.debug("Failed to delete key pair during cleanup: %s", e)

            campers_dir = os.environ.get("CAMPERS_DIR", str(Path.home() / ".campers"))
            key_file = Path(campers_dir) / "keys" / f"{unique_id}.pem"

            if key_file.exists():
                key_file.unlink()

        if sg_id and not delete_security_group_with_retry(self.ec2_client, sg_id):
            logger.debug("Failed to delete security group %s during cleanup after retries", sg_id)
