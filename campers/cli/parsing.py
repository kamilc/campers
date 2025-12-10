"""CLI argument parsing and parameter conversion utilities."""

from __future__ import annotations

from typing import Any

from campers.constants import MAX_VALID_PORT, MIN_VALID_PORT


def parse_single_port_spec(port_spec: str | int) -> tuple[int, int]:
    """Parse a single port specification into (remote, local) tuple.

    Parameters
    ----------
    port_spec : str | int
        Port specification - can be:
        - Integer: same port for remote and local (e.g., 8888)
        - String with single value: same port for remote and local (e.g., "8888")
        - String with colon: remote:local mapping (e.g., "6006:6007")

    Returns
    -------
    tuple[int, int]
        Tuple of (remote_port, local_port)

    Raises
    ------
    ValueError
        If port value is not numeric or outside valid range (1-65535)
    """
    if isinstance(port_spec, int):
        return (port_spec, port_spec)

    port_str = str(port_spec).strip()

    if ":" in port_str:
        parts = port_str.split(":")

        if len(parts) != 2:
            raise ValueError(
                f"Invalid port mapping: '{port_str}'. "
                f"Expected format: 'remote:local' (e.g., '6006:6007')"
            )

        try:
            remote_port = int(parts[0].strip())
            local_port = int(parts[1].strip())
        except ValueError:
            raise ValueError(
                f"Invalid port mapping: '{port_str}'. Both remote and local ports must be numeric"
            ) from None

        return (remote_port, local_port)

    try:
        port = int(port_str)
        return (port, port)
    except ValueError:
        raise ValueError(f"Invalid port value: '{port_str}' is not numeric") from None


def validate_port_range(port: int, context: str = "") -> None:
    """Validate that a port is within valid range.

    Parameters
    ----------
    port : int
        Port number to validate
    context : str
        Optional context for error message (e.g., "remote", "local")

    Raises
    ------
    ValueError
        If port is outside valid range (1-65535)
    """
    if port < MIN_VALID_PORT or port > MAX_VALID_PORT:
        ctx = f" ({context})" if context else ""
        raise ValueError(
            f"Invalid port value: {port}{ctx}. Port must be between "
            f"{MIN_VALID_PORT} and {MAX_VALID_PORT}"
        )


def parse_port_parameter(
    port: str | int | list[int | str] | tuple[int | str, ...],
) -> list[tuple[int, int]]:
    """Parse port parameter into list of (remote, local) tuples with validation.

    Parameters
    ----------
    port : str | int | list[int | str] | tuple[int | str, ...]
        Port specification - can be:
        - Single integer: same port for remote and local
        - Comma-separated string: multiple ports (e.g., "8888,6006:6007")
        - List/tuple: multiple port specs

    Returns
    -------
    list[tuple[int, int]]
        List of (remote_port, local_port) tuples

    Raises
    ------
    ValueError
        If any port value is not numeric or outside valid range (1-65535)

    Examples
    --------
    >>> parse_port_parameter(8888)
    [(8888, 8888)]
    >>> parse_port_parameter("6006:6007")
    [(6006, 6007)]
    >>> parse_port_parameter("8888,6006:6007")
    [(8888, 8888), (6006, 6007)]
    """
    port_tuples: list[tuple[int, int]] = []

    if isinstance(port, (tuple, list)):
        for p in port:
            port_tuples.append(parse_single_port_spec(p))
    elif isinstance(port, int):
        port_tuples.append((port, port))
    else:
        port_strings = str(port).split(",")

        for port_str in port_strings:
            port_str = port_str.strip()

            if not port_str:
                continue

            port_tuples.append(parse_single_port_spec(port_str))

    for remote_port, local_port in port_tuples:
        validate_port_range(remote_port, "remote")
        validate_port_range(local_port, "local")

    return port_tuples


def normalize_ports_config(
    ports: list[int | str | tuple[int, int]] | None,
) -> list[tuple[int, int]]:
    """Normalize ports configuration to list of (remote, local) tuples.

    Parameters
    ----------
    ports : list[int | str | tuple[int, int]] | None
        Raw ports configuration from YAML or CLI

    Returns
    -------
    list[tuple[int, int]]
        List of (remote_port, local_port) tuples
    """
    if not ports:
        return []

    result: list[tuple[int, int]] = []

    for port in ports:
        if isinstance(port, tuple) and len(port) == 2:
            result.append(port)
        else:
            result.append(parse_single_port_spec(port))

    return result


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
    "parse_single_port_spec",
    "validate_port_range",
    "parse_port_parameter",
    "normalize_ports_config",
    "parse_include_vcs",
    "parse_ignore_patterns",
    "apply_cli_overrides",
]
