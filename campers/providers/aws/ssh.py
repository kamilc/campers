"""AWS-specific SSH connection resolution."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

import boto3

if TYPE_CHECKING:
    from campers.services.ssh import SSHConnectionInfo

logger = logging.getLogger(__name__)


def get_aws_ssh_connection_info(
    instance_id: str, public_ip: str, key_file: str
) -> SSHConnectionInfo:
    """Determine SSH connection details using AWS-specific resolution.

    Checks for test harness SSH tags first (CampersSSHHost, CampersSSHPort)
    which are used by test environments like LocalStack. Falls back to public
    IP address for production AWS usage where instances have public connectivity.

    For production AWS usage, instances must have a public IP address to enable
    SSH connectivity. This is the standard configuration for development and
    testing workflows. For production use cases requiring private subnets,
    standard SSH proxy patterns apply (bastion hosts, VPNs, etc.).

    Parameters
    ----------
    instance_id : str
        EC2 instance ID
    public_ip : str
        Instance public IP address
    key_file : str
        SSH private key file path

    Returns
    -------
    SSHConnectionInfo
        SSH connection information with host, port, and key file

    Raises
    ------
    ValueError
        If SSH connection details cannot be determined
    """
    from campers.services.ssh import SSHConnectionInfo

    logger.info("get_aws_ssh_connection_info: instance_id=%s, public_ip=%r", instance_id, public_ip)

    ssh_host = _get_ssh_host_from_tags(instance_id)
    ssh_port = _get_ssh_port_from_tags(instance_id)

    if ssh_host is not None and ssh_port is not None:
        logger.info(
            "Using harness SSH configuration for instance %s: host=%s, port=%s",
            instance_id, ssh_host, ssh_port
        )
        return SSHConnectionInfo(host=ssh_host, port=ssh_port, key_file=key_file)

    if public_ip:
        logger.info(
            "Using public IP for instance %s: host=%s, port=22",
            instance_id, public_ip
        )
        return SSHConnectionInfo(host=public_ip, port=22, key_file=key_file)

    raise ValueError(
        f"Instance {instance_id} does not have SSH connection details. "
        "Neither test harness tags (CampersSSHHost/CampersSSHPort) nor "
        "public IP address are available."
    )


def _get_ssh_host_from_tags(instance_id: str) -> str | None:
    """Get SSH host from instance CampersSSHHost tag.

    Parameters
    ----------
    instance_id : str
        EC2 instance ID

    Returns
    -------
    str | None
        SSH host from tag, or None if not found
    """
    try:
        host = _get_instance_tag_value(instance_id, "CampersSSHHost")
        logger.debug("Retrieved CampersSSHHost tag for %s: %s", instance_id, host)
        return host
    except Exception as e:
        logger.debug(
            "Failed to retrieve CampersSSHHost tag for instance %s: %s",
            instance_id, e, exc_info=True
        )
        return None


def _get_ssh_port_from_tags(instance_id: str) -> int | None:
    """Get SSH port from instance CampersSSHPort tag.

    Parameters
    ----------
    instance_id : str
        EC2 instance ID

    Returns
    -------
    int | None
        SSH port from tag, or None if not found or cannot be parsed
    """
    try:
        port_str = _get_instance_tag_value(instance_id, "CampersSSHPort")
        logger.debug("Retrieved CampersSSHPort tag for %s: %s", instance_id, port_str)
        if port_str is not None:
            return int(port_str)
    except (ValueError, TypeError) as e:
        logger.debug(
            "Failed to parse CampersSSHPort tag for instance %s: %s",
            instance_id, e, exc_info=True
        )
    except Exception as e:
        logger.debug(
            "Failed to retrieve CampersSSHPort tag for instance %s: %s",
            instance_id, e, exc_info=True
        )
    return None


def _get_instance_tag_value(instance_id: str, tag_key: str) -> str | None:
    """Retrieve a specific tag value from an EC2 instance.

    Parameters
    ----------
    instance_id : str
        EC2 instance ID
    tag_key : str
        Tag key to retrieve

    Returns
    -------
    str | None
        Tag value, or None if not found

    Raises
    ------
    Exception
        If EC2 API call fails
    """
    endpoint_url = os.environ.get("AWS_ENDPOINT_URL")
    region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

    logger.debug(
        "Fetching instance tags: endpoint=%s, region=%s, instance_id=%s, tag_key=%s",
        endpoint_url, region, instance_id, tag_key
    )

    ec2_client = boto3.client(
        "ec2",
        endpoint_url=endpoint_url,
        region_name=region
    )
    response = ec2_client.describe_instances(InstanceIds=[instance_id])

    if not response["Reservations"]:
        logger.debug("No reservations found for instance %s", instance_id)
        return None

    instance = response["Reservations"][0]["Instances"][0]
    tags = instance.get("Tags", [])

    logger.debug("Instance %s has %d tags: %s", instance_id, len(tags), tags)

    for tag in tags:
        if tag.get("Key") == tag_key:
            value = tag.get("Value")
            logger.debug("Found tag %s=%s for instance %s", tag_key, value, instance_id)
            return value

    logger.debug("Tag %s not found for instance %s", tag_key, instance_id)
    return None
