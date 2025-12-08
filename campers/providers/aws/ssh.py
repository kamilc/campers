"""AWS-specific SSH connection resolution."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

import boto3

from campers.providers.aws.constants import TAG_FETCH_RETRY_DELAY, TAG_FETCH_RETRY_MAX

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

    endpoint_url = os.environ.get("AWS_ENDPOINT_URL")

    if endpoint_url:
        ssh_host = _get_ssh_host_from_tags(instance_id)
        ssh_port = _get_ssh_port_from_tags(instance_id)
        ssh_username = _get_ssh_username_from_tags(instance_id)
        ssh_key_file = _get_ssh_key_file_from_tags(instance_id)
    else:
        ssh_host = None
        ssh_port = None
        ssh_username = None
        ssh_key_file = None

    if ssh_host is not None and ssh_port is not None:
        effective_key_file = ssh_key_file if ssh_key_file else key_file
        logger.info(
            "Using harness SSH config for %s: host=%s, port=%s, username=%s, key=%s",
            instance_id,
            ssh_host,
            ssh_port,
            ssh_username,
            effective_key_file,
        )
        return SSHConnectionInfo(
            host=ssh_host,
            port=ssh_port,
            key_file=effective_key_file,
            username=ssh_username,
            tag_key_file=ssh_key_file,
        )

    if public_ip:
        logger.info("Using public IP for instance %s: host=%s, port=22", instance_id, public_ip)
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
            instance_id,
            e,
            exc_info=True,
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
            "Failed to parse CampersSSHPort tag for instance %s: %s", instance_id, e, exc_info=True
        )
    except Exception as e:
        logger.debug(
            "Failed to retrieve CampersSSHPort tag for instance %s: %s",
            instance_id,
            e,
            exc_info=True,
        )
    return None


def _get_ssh_username_from_tags(instance_id: str) -> str | None:
    """Get SSH username from instance CampersSSHUsername tag.

    Parameters
    ----------
    instance_id : str
        EC2 instance ID

    Returns
    -------
    str | None
        SSH username from tag, or None if not found
    """
    try:
        username = _get_instance_tag_value(instance_id, "CampersSSHUsername")
        logger.debug("Retrieved CampersSSHUsername tag for %s: %s", instance_id, username)
        return username
    except Exception as e:
        logger.debug(
            "Failed to retrieve CampersSSHUsername tag for instance %s: %s",
            instance_id,
            e,
            exc_info=True,
        )
        return None


def _get_ssh_key_file_from_tags(instance_id: str) -> str | None:
    """Get SSH key file path from instance CampersSSHKeyFile tag.

    Parameters
    ----------
    instance_id : str
        EC2 instance ID

    Returns
    -------
    str | None
        SSH key file path from tag, or None if not found
    """
    try:
        key_file = _get_instance_tag_value(instance_id, "CampersSSHKeyFile")
        logger.debug("Retrieved CampersSSHKeyFile tag for %s: %s", instance_id, key_file)
        return key_file
    except Exception as e:
        logger.debug(
            "Failed to retrieve CampersSSHKeyFile tag for instance %s: %s",
            instance_id,
            e,
            exc_info=True,
        )
        return None


def _get_instance_tag_value(instance_id: str, tag_key: str) -> str | None:
    """Retrieve a specific tag value from an EC2 instance.

    Includes automatic retry logic to handle eventual consistency in distributed systems
    where tags may not be immediately available after instance creation or tagging.

    Parameters
    ----------
    instance_id : str
        EC2 instance ID
    tag_key : str
        Tag key to retrieve

    Returns
    -------
    str | None
        Tag value, or None if not found after retries

    Raises
    ------
    Exception
        If EC2 API call fails permanently
    """
    import time

    endpoint_url = os.environ.get("AWS_ENDPOINT_URL")
    region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

    logger.debug(
        "Fetching instance tags: endpoint=%s, region=%s, instance_id=%s, tag_key=%s",
        endpoint_url,
        region,
        instance_id,
        tag_key,
    )

    ec2_client = boto3.client("ec2", endpoint_url=endpoint_url, region_name=region)

    for attempt in range(TAG_FETCH_RETRY_MAX):
        try:
            response = ec2_client.describe_instances(InstanceIds=[instance_id])

            if not response["Reservations"]:
                logger.debug("No reservations found for instance %s", instance_id)
                return None

            instance = response["Reservations"][0]["Instances"][0]
            tags = instance.get("Tags", [])

            logger.debug(
                "Instance %s has %d tags (attempt %d/%d): %s",
                instance_id,
                len(tags),
                attempt + 1,
                TAG_FETCH_RETRY_MAX,
                tags,
            )

            for tag in tags:
                if tag.get("Key") == tag_key:
                    value = tag.get("Value")
                    logger.debug("Found tag %s=%s for instance %s", tag_key, value, instance_id)
                    return value

            if attempt < TAG_FETCH_RETRY_MAX - 1:
                logger.debug(
                    "Tag %s not found for instance %s on attempt %d/%d; retrying in %.0fms",
                    tag_key,
                    instance_id,
                    attempt + 1,
                    TAG_FETCH_RETRY_MAX,
                    TAG_FETCH_RETRY_DELAY * 1000,
                )
                time.sleep(TAG_FETCH_RETRY_DELAY)
            else:
                logger.debug(
                    "Tag %s not found for instance %s after %d attempts",
                    tag_key,
                    instance_id,
                    TAG_FETCH_RETRY_MAX,
                )
                return None

        except Exception as e:
            logger.debug(
                "Error fetching tags for instance %s on attempt %d/%d: %s",
                instance_id,
                attempt + 1,
                TAG_FETCH_RETRY_MAX,
                e,
            )
            if attempt < TAG_FETCH_RETRY_MAX - 1:
                time.sleep(TAG_FETCH_RETRY_DELAY)
            else:
                raise

    return None
