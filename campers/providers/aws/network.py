"""Network and security group management for EC2 instances."""

import logging
from typing import Any

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

        with handle_aws_errors():
            response = self.ec2_client.create_security_group(
                GroupName=sg_name,
                Description=f"Campers security group {unique_id}",
                VpcId=vpc_id,
            )

        sg_id = response["GroupId"]

        with handle_aws_errors():
            self.ec2_client.create_tags(
                Resources=[sg_id], Tags=[{"Key": "ManagedBy", "Value": "campers"}]
            )

        cidr_block = ssh_allowed_cidr if ssh_allowed_cidr else "0.0.0.0/0"

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
