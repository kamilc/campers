"""CLI argument parsing and parameter conversion utilities."""

from __future__ import annotations

from typing import Any


def parse_port_parameter(port: str | list[int] | tuple[int, ...]) -> list[int]:
    """Parse port parameter into list of integers.

    Parameters
    ----------
    port : str | list[int] | tuple[int, ...]
        Port specification - can be single value, comma-separated string, list, or tuple

    Returns
    -------
    list[int]
        List of port numbers as integers
    """
    if isinstance(port, (tuple, list)):
        return [int(p) for p in port]

    return [int(p.strip()) for p in str(port).split(",") if p.strip()]


def parse_include_vcs(include_vcs: str | bool) -> bool:
    """Parse include_vcs parameter into boolean.

    Parameters
    ----------
    include_vcs : str | bool
        VCS inclusion flag - can be boolean or "true"/"false" string

    Returns
    -------
    bool
        Boolean value for VCS inclusion

    Raises
    ------
    ValueError
        If string value is not "true" or "false"
    """
    if isinstance(include_vcs, bool):
        return include_vcs

    if isinstance(include_vcs, str):
        vcs_lower = include_vcs.lower()

        if vcs_lower not in ("true", "false"):
            raise ValueError(f"include_vcs must be 'true' or 'false', got: {include_vcs}")

        return vcs_lower == "true"

    raise ValueError(f"Unexpected type for include_vcs: {type(include_vcs)}")


def parse_ignore_patterns(ignore: str) -> list[str]:
    """Parse comma-separated ignore patterns into list.

    Parameters
    ----------
    ignore : str
        Comma-separated file patterns to exclude

    Returns
    -------
    list[str]
        List of ignore patterns
    """
    return [pattern.strip() for pattern in ignore.split(",") if pattern.strip()]


def apply_cli_overrides(
    config: dict[str, Any],
    command: str | None,
    instance_type: str | None,
    disk_size: int | None,
    region: str | None,
    port: str | list[int] | tuple[int, ...] | None,
    include_vcs: str | bool | None,
    ignore: str | None,
) -> None:
    """Apply CLI option overrides to merged configuration.

    Parameters
    ----------
    config : dict[str, Any]
        Configuration dictionary to modify in-place
    command : str | None
        Command to execute on remote instance
    instance_type : str | None
        EC2 instance type
    disk_size : int | None
        Root disk size in GB
    region : str | None
        AWS region
    port : str | list[int] | tuple[int, ...] | None
        Local port(s) for forwarding
    include_vcs : str | bool | None
        Include VCS files
    ignore : str | None
        Comma-separated file patterns to exclude
    """
    if command is not None:
        config["command"] = command

    if instance_type is not None:
        config["instance_type"] = instance_type

    if disk_size is not None:
        config["disk_size"] = disk_size

    if region is not None:
        config["region"] = region

    if port is not None:
        config["ports"] = parse_port_parameter(port)
        config.pop("port", None)

    if include_vcs is not None:
        config["include_vcs"] = parse_include_vcs(include_vcs)

    if ignore is not None:
        config["ignore"] = parse_ignore_patterns(ignore)


__all__ = [
    "parse_port_parameter",
    "parse_include_vcs",
    "parse_ignore_patterns",
    "apply_cli_overrides",
]
