"""Network and security group management for EC2 instances."""

import logging
import random
import time
import uuid
from typing import Any

from botocore.exceptions import ClientError

from campers.providers.aws.constants import SSH_SECURITY_GROUP_DEFAULT_CIDR
from campers.providers.aws.errors import handle_aws_errors
from campers.providers.exceptions import ProviderAPIError

logger = logging.getLogger(__name__)


def delete_security_group_with_retry(
    ec2_client: Any,
    sg_id: str,
    max_attempts: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
) -> bool:
    """Delete security group with exponential backoff for DependencyViolation.

    Implements exponential backoff retry strategy for transient AWS errors
    that prevent security group deletion (DependencyViolation, InvalidGroup.InUse).
    Treats InvalidGroup.NotFound as success (idempotent operation).
    Fails immediately on permission errors and other non-transient failures.

    Parameters
    ----------
    ec2_client : Any
        Boto3 EC2 client
    sg_id : str
        Security group ID to delete
    max_attempts : int
        Maximum retry attempts (default: 5)
    base_delay : float
        Initial delay in seconds (default: 1.0)
    max_delay : float
        Maximum delay cap in seconds (default: 30.0)

    Returns
    -------
    bool
        True if deleted successfully or already deleted, False if failed after all retries
    """
    for attempt in range(max_attempts):
        try:
            ec2_client.delete_security_group(GroupId=sg_id)
            logger.info("Deleted security group %s", sg_id)
            return True

        except ClientError as e:
            error_code = e.response["Error"]["Code"]

            if error_code == "InvalidGroup.NotFound":
                logger.debug("Security group %s already deleted", sg_id)
                return True

            if error_code in ("DependencyViolation", "InvalidGroup.InUse"):
                if attempt < max_attempts - 1:
                    delay = min(base_delay * (2**attempt), max_delay)
                    jitter = random.uniform(0, delay * 0.1)
                    wait_time = delay + jitter

                    logger.warning(
                        "Security group %s still in use, retrying in %.1fs (attempt %d/%d)",
                        sg_id,
                        wait_time,
                        attempt + 1,
                        max_attempts,
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(
                        "Failed to delete security group %s after %d attempts: "
                        "still has dependencies",
                        sg_id,
                        max_attempts,
                    )
                    return False
            else:
                logger.error(
                    "Failed to delete security group %s: %s - %s",
                    sg_id,
                    error_code,
                    e.response["Error"]["Message"],
                )
                return False

    return False


class NetworkManager:
    """Manage EC2 network resources (security groups, VPCs)."""

    def __init__(self, ec2_client: Any, region: str) -> None:
        """Initialize NetworkManager.

        Parameters
        ----------
        ec2_client : Any
            Boto3 EC2 client
        region : str
            AWS region name
        """
        self.ec2_client = ec2_client
        self.region = region

    def get_default_vpc_id(self) -> str:
        """Get the default VPC ID for the region.

        Returns
        -------
        str
            Default VPC ID

        Raises
        ------
        ValueError
            If no default VPC is found
        """
        with handle_aws_errors():
            vpcs = self.ec2_client.describe_vpcs(
                Filters=[{"Name": "isDefault", "Values": ["true"]}]
            )

        if not vpcs["Vpcs"]:
            raise ValueError(f"No default VPC found in region '{self.region}'")

        return vpcs["Vpcs"][0]["VpcId"]

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
            CIDR block for public ports access. If None, defaults to 0.0.0.0/0
        project_name : str | None
            Project name for naming convention. If provided along with branch and camp_name,
            uses format campers-{project_name}-{branch}-{camp_name}
        branch : str | None
            Branch name for naming convention
        camp_name : str | None
            Camp name for naming convention

        Returns
        -------
        str
            Security group ID
        """
        from campers.constants import PUBLIC_PORTS_DEFAULT_CIDR

        if project_name and branch and camp_name:
            sg_name = f"campers-{project_name}-{branch}-{camp_name}"
        else:
            sg_name = f"campers-{unique_id}"

        vpc_id = self.get_default_vpc_id()

        with handle_aws_errors():
            existing_sgs = self.ec2_client.describe_security_groups(
                Filters=[
                    {"Name": "group-name", "Values": [sg_name]},
                    {"Name": "vpc-id", "Values": [vpc_id]},
                ]
            )

        if existing_sgs["SecurityGroups"]:
            sg_id = existing_sgs["SecurityGroups"][0]["GroupId"]
            delete_security_group_with_retry(self.ec2_client, sg_id)

        sg_id = self._create_security_group_with_retry(sg_name, unique_id, vpc_id)

        with handle_aws_errors():
            self.ec2_client.create_tags(
                Resources=[sg_id], Tags=[{"Key": "ManagedBy", "Value": "campers"}]
            )

        cidr_block = ssh_allowed_cidr if ssh_allowed_cidr else SSH_SECURITY_GROUP_DEFAULT_CIDR

        if cidr_block == SSH_SECURITY_GROUP_DEFAULT_CIDR:
            logger.debug(
                "SSH security group using default CIDR %s",
                SSH_SECURITY_GROUP_DEFAULT_CIDR,
            )

        with handle_aws_errors():
            self.ec2_client.authorize_security_group_ingress(
                GroupId=sg_id,
                IpPermissions=[
                    {
                        "IpProtocol": "tcp",
                        "FromPort": 22,
                        "ToPort": 22,
                        "IpRanges": [{"CidrIp": cidr_block}],
                    }
                ],
            )

        if public_ports:
            public_cidr = public_ports_allowed_cidr or PUBLIC_PORTS_DEFAULT_CIDR

            if public_cidr == PUBLIC_PORTS_DEFAULT_CIDR:
                logger.warning(
                    "Public ports %s are open to the internet (%s)",
                    public_ports,
                    PUBLIC_PORTS_DEFAULT_CIDR,
                )
            else:
                logger.debug(
                    "Public ports %s are open to %s",
                    public_ports,
                    public_cidr,
                )

            for port in public_ports:
                with handle_aws_errors():
                    self.ec2_client.authorize_security_group_ingress(
                        GroupId=sg_id,
                        IpPermissions=[
                            {
                                "IpProtocol": "tcp",
                                "FromPort": port,
                                "ToPort": port,
                                "IpRanges": [{"CidrIp": public_cidr}],
                            }
                        ],
                    )
                logger.debug("Opened public port %d to %s", port, public_cidr)

        return sg_id

    def _create_security_group_with_retry(
        self, sg_name: str, unique_id: str, vpc_id: str, max_retries: int = 3
    ) -> str:
        """Create security group with exponential backoff retry on name collision.

        Handles InvalidGroup.Duplicate error by appending a unique suffix and retrying.

        Parameters
        ----------
        sg_name : str
            Base security group name
        unique_id : str
            Unique identifier for the group
        vpc_id : str
            VPC ID for the security group
        max_retries : int
            Maximum number of retries (default: 3)

        Returns
        -------
        str
            Security group ID

        Raises
        ------
        ProviderAPIError
            If creation fails after all retries
        """
        for attempt in range(max_retries):
            try:
                with handle_aws_errors():
                    response = self.ec2_client.create_security_group(
                        GroupName=sg_name,
                        Description=f"Campers security group {unique_id}",
                        VpcId=vpc_id,
                    )
                return response["GroupId"]
            except ProviderAPIError as e:
                if e.error_code != "InvalidGroup.Duplicate":
                    raise

                if attempt == max_retries - 1:
                    raise

                backoff_time = 2**attempt
                logger.debug(
                    "Security group name collision, retrying with suffix (attempt %d/%d)",
                    attempt + 1,
                    max_retries,
                )
                time.sleep(backoff_time)

                unique_suffix = str(uuid.uuid4())[:8]
                sg_name = f"campers-{unique_id}-{unique_suffix}"

        raise ProviderAPIError(
            message=f"Failed to create security group after {max_retries} attempts",
            error_code="SecurityGroupCreationFailed",
        )
