"""AWS-specific SSH connection resolution."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from campers.services.ssh import SSHConnectionInfo

logger = logging.getLogger(__name__)


def get_aws_ssh_connection_info(
    instance_id: str, public_ip: str, key_file: str
) -> SSHConnectionInfo:
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
    SSHConnectionInfo
        SSH connection information with host, port, and key file

    Raises
    ------
    ValueError
        If instance does not have a public IP address
    """
    from campers.services.ssh import SSHConnectionInfo

    logger.info("get_aws_ssh_connection_info: instance_id=%s, public_ip=%r", instance_id, public_ip)

    if public_ip:
        return SSHConnectionInfo(host=public_ip, port=22, key_file=key_file)

    raise ValueError(
        f"Instance {instance_id} does not have a public IP address. "
        "SSH connection requires public networking configuration."
    )
