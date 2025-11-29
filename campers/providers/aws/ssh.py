"""AWS-specific SSH connection resolution."""

import logging

logger = logging.getLogger(__name__)


def get_aws_ssh_connection_info(
    instance_id: str, public_ip: str, key_file: str
) -> tuple[str, int, str]:
    """Determine SSH connection details using AWS-specific resolution.

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
    tuple[str, int, str]
        (host, port, key_file) tuple for SSH connection

    Raises
    ------
    ValueError
        If instance does not have a public IP address
    """
    logger.info(f"get_aws_ssh_connection_info: instance_id={instance_id}, public_ip={public_ip!r}")

    if public_ip:
        return public_ip, 22, key_file

    raise ValueError(
        f"Instance {instance_id} does not have a public IP address. "
        "SSH connection requires public networking configuration."
    )
