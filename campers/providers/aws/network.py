"""Network and security group management for EC2 instances."""

import logging
import time
import uuid
from typing import Any

from campers.providers.aws.constants import SSH_SECURITY_GROUP_DEFAULT_CIDR
from campers.providers.aws.errors import handle_aws_errors
from campers.providers.exceptions import ProviderAPIError

logger = logging.getLogger(__name__)


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

    def create_security_group(self, unique_id: str, ssh_allowed_cidr: str | None = None) -> str:
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
            try:
                with handle_aws_errors():
                    self.ec2_client.delete_security_group(GroupId=sg_id)
                logger.debug("Deleted existing security group %s", sg_id)
            except ProviderAPIError as e:
                logger.warning("Failed to delete existing security group %s: %s", sg_id, e)

        sg_id = self._create_security_group_with_retry(sg_name, unique_id, vpc_id)

        with handle_aws_errors():
            self.ec2_client.create_tags(
                Resources=[sg_id], Tags=[{"Key": "ManagedBy", "Value": "campers"}]
            )

        cidr_block = ssh_allowed_cidr if ssh_allowed_cidr else SSH_SECURITY_GROUP_DEFAULT_CIDR

        if cidr_block == SSH_SECURITY_GROUP_DEFAULT_CIDR:
            logger.warning(
                "SSH security group is using %s (all IPs). "
                "This allows SSH access from any IP address. "
                "Consider restricting this to your IP range for security.",
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
