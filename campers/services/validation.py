"""Input validation utilities for services.

Provides validation functions for security-sensitive inputs that are interpolated
into configurations or commands to prevent injection attacks.
"""

import re

from campers.constants import (
    MAX_VALID_PORT,
    MIN_VALID_PORT,
    SAFE_HOSTNAME_PATTERN,
    SAFE_USERNAME_PATTERN,
)


def validate_ansible_host(host: str) -> str:
    """Validate hostname for safe Ansible inventory interpolation.

    Parameters
    ----------
    host : str
        Hostname to validate

    Returns
    -------
    str
        The validated hostname

    Raises
    ------
    ValueError
        If hostname contains invalid characters that could enable injection attacks
    """
    pattern = re.compile(SAFE_HOSTNAME_PATTERN)
    if not pattern.match(host):
        raise ValueError(
            f"Invalid hostname: {host}. "
            "Hostname must start with alphanumeric character and contain only "
            "alphanumeric characters, dots, and hyphens."
        )
    return host


def validate_ansible_user(user: str) -> str:
    """Validate username for safe Ansible inventory interpolation.

    Parameters
    ----------
    user : str
        Username to validate

    Returns
    -------
    str
        The validated username

    Raises
    ------
    ValueError
        If username contains invalid characters that could enable injection attacks
    """
    pattern = re.compile(SAFE_USERNAME_PATTERN)
    if not pattern.match(user):
        raise ValueError(
            f"Invalid username: {user}. "
            "Username must start with letter or underscore and contain only "
            "alphanumeric characters and underscores."
        )
    return user


def validate_port(port: int) -> int:
    """Validate port number for safe SSH configuration.

    Parameters
    ----------
    port : int
        Port number to validate

    Returns
    -------
    int
        The validated port number

    Raises
    ------
    ValueError
        If port is not an integer in the valid range 1-65535
    """
    if not isinstance(port, int):
        raise ValueError(f"Invalid port: {port}. Port must be an integer.")
    if port < MIN_VALID_PORT or port > MAX_VALID_PORT:
        raise ValueError(
            f"Invalid port: {port}. Port must be between {MIN_VALID_PORT} and {MAX_VALID_PORT}."
        )
    return port
