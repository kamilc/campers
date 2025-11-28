"""AWS-specific SSH connection resolution."""

import logging
import time

import boto3

from campers.constants import SSH_IP_RETRY_DELAY, SSH_IP_RETRY_MAX
from campers.utils import is_localstack_endpoint, validate_port

logger = logging.getLogger(__name__)


def get_aws_ssh_connection_info(
    instance_id: str, public_ip: str, key_file: str
) -> tuple[str, int, str]:
    """Determine SSH connection details using AWS-specific resolution.

    Standard AWS path: If instance has a public IP, returns (public_ip, 22,
    key_file) using standard AWS configuration. This is the normal path for
    production AWS users and development on real EC2 instances.

    LocalStack path: If instance has no public IP and LocalStack is detected
    via boto3 endpoint URL inspection, reads SSH connection details from EC2
    instance tags (CampersSSHHost, CampersSSHPort, CampersSSHKeyFile).
    This enables high-fidelity BDD testing against LocalStack.

    LocalStack detection is defensive: checks actual boto3 endpoint URL for
    "localstack" or ":4566" (default LocalStack port) rather than using
    environment variables or test mode flags. Real AWS users with public-facing
    instances never trigger this code path because they have public IPs. For
    production use cases requiring private subnets, standard SSH proxy patterns
    apply (bastion hosts, VPNs, etc.).

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
    tuple[str, int, str]
        (host, port, key_file) tuple for SSH connection

    Raises
    ------
    ValueError
        If instance has no public IP address and LocalStack is not detected
    """
    logger.info(
        f"get_aws_ssh_connection_info: instance_id={instance_id}, public_ip={public_ip!r}"
    )

    if public_ip:
        return public_ip, 22, key_file

    logger.info(
        f"Instance {instance_id} has no public IP, checking for SSH tags in LocalStack"
    )

    try:
        ec2_client = boto3.client("ec2")
        logger.info(f"EC2 endpoint: {ec2_client.meta.endpoint_url}")

        if is_localstack_endpoint(ec2_client):
            logger.info("Detected LocalStack endpoint")

            for attempt in range(SSH_IP_RETRY_MAX):
                response = ec2_client.describe_tags(
                    Filters=[
                        {"Name": "resource-id", "Values": [instance_id]},
                        {
                            "Name": "key",
                            "Values": [
                                "CampersSSHHost",
                                "CampersSSHPort",
                                "CampersSSHKeyFile",
                            ],
                        },
                    ]
                )

                tags = {tag["Key"]: tag["Value"] for tag in response.get("Tags", [])}

                if (
                    "CampersSSHHost" in tags
                    and "CampersSSHPort" in tags
                    and "CampersSSHKeyFile" in tags
                ):
                    host = tags["CampersSSHHost"]
                    try:
                        port = int(tags["CampersSSHPort"])
                        validate_port(port)
                    except (ValueError, TypeError) as e:
                        logger.error("Invalid SSH port in tags: %s", e)
                        raise ValueError(
                            f"Invalid SSH port in instance tags: {e}"
                        ) from e
                    tag_key_file = tags["CampersSSHKeyFile"]
                    logger.info(
                        f"Using tag-based SSH config for {instance_id}: {host}:{port}"
                    )
                    return host, port, tag_key_file

                if attempt < SSH_IP_RETRY_MAX - 1:
                    time.sleep(SSH_IP_RETRY_DELAY)

            logger.warning(
                f"SSH tags not found for {instance_id} after {SSH_IP_RETRY_MAX} attempts"
            )

    except Exception as e:
        logger.warning(f"Failed to read SSH tags from instance {instance_id}: {e}")

    raise ValueError(
        f"Instance {instance_id} does not have a public IP address. "
        "SSH connection requires public networking configuration."
    )
