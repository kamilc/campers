"""CLI entry point for Campers."""

from __future__ import annotations

import logging
import os
import re
import sys
from collections.abc import Callable
from typing import Any

import fire
import paramiko

from campers.core.interfaces import ComputeProvider
from campers.logging import StreamFormatter, StreamRoutingFilter
from campers.providers import ProviderAPIError, ProviderCredentialsError
from campers.providers.aws.utils import get_aws_credentials_error_message
from campers.services.ssh import SSHManager


def get_campers_base_class() -> type:
    """Get Campers base class on-demand to avoid circular imports.

    Returns
    -------
    type
        Campers base class
    """
    from campers.__main__ import Campers

    return Campers


class CampersCLI:
    """CLI wrapper that handles process exit codes.

    This is defined as a factory that creates a subclass of Campers
    at runtime to avoid circular import issues.

    Parameters
    ----------
    compute_provider_factory : Callable[[str], ComputeProvider] | None
        Optional factory function for creating compute provider instances.
        If None, uses the default compute provider class.
    ssh_manager_factory : type[SSHManager] | None
        Optional factory function for creating SSHManager instances.
        If None, uses the default SSHManager class.
    """

    _cached_class: type | None = None

    def __new__(
        cls,
        compute_provider_factory: Callable[[str], ComputeProvider] | None = None,
        ssh_manager_factory: type[SSHManager] | None = None,
    ) -> Any:
        """Create CampersCLI instance with dynamic subclassing.

        Parameters
        ----------
        compute_provider_factory : Callable[[str], ComputeProvider] | None
            Optional factory for compute provider (default: None, uses default provider)
        ssh_manager_factory : type[SSHManager] | None
            Optional factory for SSHManager (default: None, uses SSHManager)

        Returns
        -------
        Any
            Instance of dynamically created CampersCLI subclass
        """
        if cls._cached_class is None:
            Campers = get_campers_base_class()

            class CampersCLIImpl(Campers):
                """CLI wrapper implementation for Campers."""

                def __init__(
                    self,
                    compute_provider_factory: Callable[[str], ComputeProvider] | None = None,
                    ssh_manager_factory: type[SSHManager] | None = None,
                ) -> None:
                    """Initialize CampersCLI with optional dependency injection.

                    Parameters
                    ----------
                    compute_provider_factory : Callable[[str], ComputeProvider] | None
                        Optional factory for compute provider (default: None, uses default provider)
                    ssh_manager_factory : type[SSHManager] | None
                        Optional factory for SSHManager (default: None, uses SSHManager)
                    """
                    super().__init__(
                        compute_provider_factory=compute_provider_factory,
                        ssh_manager_factory=ssh_manager_factory,
                    )

                def run(
                    self,
                    camp_name: str | None = None,
                    command: str | None = None,
                    instance_type: str | None = None,
                    disk_size: int | None = None,
                    region: str | None = None,
                    port: str | list[int] | tuple[int, ...] | None = None,
                    include_vcs: str | bool | None = None,
                    ignore: str | None = None,
                    json_output: bool = False,
                    plain: bool = False,
                    verbose: bool = False,
                ) -> dict[str, Any] | str:
                    """Run Campers and handle TUI exit codes for CLI context.

                    Parameters
                    ----------
                    camp_name : str | None
                        Name of machine configuration from YAML
                    command : str | None
                        Command to execute on remote instance
                    instance_type : str | None
                        Instance type override
                    disk_size : int | None
                        Root disk size in GB override
                    region : str | None
                        Cloud region override
                    port : str | list[int] | tuple[int, ...] | None
                        Port(s) to forward
                    include_vcs : str | bool | None
                        Include VCS files in sync
                    ignore : str | None
                        Comma-separated ignore patterns
                    json_output : bool
                        Output result as JSON
                    plain : bool
                        Disable TUI, use plain stderr logging

                    Returns
                    -------
                    dict[str, Any] | str
                        Instance metadata dict or JSON string (never returns in TUI
                        mode, exits instead)
                    """
                    debug_mode = os.environ.get("CAMPERS_DEBUG") == "1"

                    try:
                        result = super().run(
                            camp_name=camp_name,
                            command=command,
                            instance_type=instance_type,
                            disk_size=disk_size,
                            region=region,
                            port=port,
                            include_vcs=include_vcs,
                            ignore=ignore,
                            json_output=json_output,
                            plain=plain,
                            verbose=verbose,
                        )

                        if isinstance(result, dict) and result.get("tui_mode"):
                            sys.exit(result.get("exit_code", 0))

                        return result

                    except ValueError as e:
                        if debug_mode:
                            raise

                        error_msg = str(e)
                        print(f"Configuration error: {error_msg}", file=sys.stderr)
                        sys.exit(2)

            cls._cached_class = CampersCLIImpl

        return cls._cached_class(
            compute_provider_factory=compute_provider_factory,
            ssh_manager_factory=ssh_manager_factory,
        )


def handle_credentials_error(debug_mode: bool) -> None:
    """Handle provider credentials error.

    Parameters
    ----------
    debug_mode : bool
        Whether debug mode is enabled

    Raises
    ------
    ProviderCredentialsError
        Re-raised if debug mode is enabled
    """
    if debug_mode:
        raise

    print(get_aws_credentials_error_message(), file=sys.stderr)
    sys.exit(1)


def handle_value_error(error: ValueError, debug_mode: bool) -> None:
    """Handle value error with context-specific messages.

    Parameters
    ----------
    error : ValueError
        The value error that was raised
    debug_mode : bool
        Whether debug mode is enabled

    Raises
    ------
    ValueError
        Re-raised if debug mode is enabled
    """
    if debug_mode:
        raise

    error_msg = str(error)

    if "No default VPC" in error_msg:
        match = re.search(r"in\s+region\s+(\S+)", error_msg)
        region = match.group(1) if match else "us-east-1"

        print(f"No default VPC in {region}\n", file=sys.stderr)
        print("Fix it:", file=sys.stderr)
        print("  campers setup\n", file=sys.stderr)
        print("Or manually:", file=sys.stderr)
        print(f"  aws ec2 create-default-vpc --region {region}\n", file=sys.stderr)
        print("Or use different region:", file=sys.stderr)
        print("  campers run --region us-west-2", file=sys.stderr)
        sys.exit(1)
    elif "startup_script" in error_msg and "sync_paths" in error_msg:
        print("Configuration error\n", file=sys.stderr)
        print("startup_script requires sync_paths to be configured\n", file=sys.stderr)
        print("Add sync_paths to your configuration:", file=sys.stderr)
        print("  sync_paths:", file=sys.stderr)
        print("    - local: ./src", file=sys.stderr)
        print("      remote: /home/ubuntu/src", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"Configuration error: {error_msg}", file=sys.stderr)
        sys.exit(2)


def handle_api_error(error: ProviderAPIError, debug_mode: bool) -> None:
    """Handle provider API error with context-specific messages.

    Parameters
    ----------
    error : ProviderAPIError
        The API error that was raised
    debug_mode : bool
        Whether debug mode is enabled

    Raises
    ------
    ProviderAPIError
        Re-raised if debug mode is enabled
    """
    if debug_mode:
        raise

    error_code = error.error_code
    error_msg = str(error)

    if error_code == "UnauthorizedOperation":
        print("Insufficient IAM permissions\n", file=sys.stderr)
        print(
            "Your cloud credentials don't have the required permissions.",
            file=sys.stderr,
        )
        print("Contact your cloud administrator to grant:", file=sys.stderr)
        print(
            "  - Compute permissions (DescribeInstances, RunInstances, TerminateInstances)",
            file=sys.stderr,
        )
        print("  - VPC permissions (DescribeVpcs, CreateDefaultVpc)", file=sys.stderr)
        print(
            "  - Key Pair permissions (CreateKeyPair, DeleteKeyPair, DescribeKeyPairs)",
            file=sys.stderr,
        )
        print("  - Security Group permissions", file=sys.stderr)
    elif error_code == "InvalidParameterValue" and "instance type" in error_msg.lower():
        print("Invalid instance type\n", file=sys.stderr)
        print("This usually means:", file=sys.stderr)
        print("  - Instance type not available in this region", file=sys.stderr)
        print("  - Typo in instance type name\n", file=sys.stderr)
        print("Fix it:", file=sys.stderr)
        print("  campers doctor", file=sys.stderr)
        print("  campers run --instance-type t3.medium", file=sys.stderr)
    elif error_code in ["InstanceLimitExceeded", "RequestLimitExceeded"]:
        print("Cloud quota exceeded\n", file=sys.stderr)
        print("This usually means:", file=sys.stderr)
        print("  - Too many instances running", file=sys.stderr)
        print("  - Need to request quota increase\n", file=sys.stderr)
        print("Fix it:", file=sys.stderr)
        print("  https://console.aws.amazon.com/servicequotas/", file=sys.stderr)
        print("  campers list", file=sys.stderr)
    elif error_code in ["ExpiredToken", "RequestExpired", "ExpiredTokenException"]:
        print("Cloud credentials have expired\n", file=sys.stderr)
        print("This usually means:", file=sys.stderr)
        print("  - Your temporary credentials (STS) have expired", file=sys.stderr)
        print("  - Your session token needs to be refreshed\n", file=sys.stderr)
        print("Fix it:", file=sys.stderr)
        print("  aws sso login           # If using AWS SSO", file=sys.stderr)
        print("  aws configure           # Re-configure credentials", file=sys.stderr)
        print("  # Or refresh your temporary credentials", file=sys.stderr)
    else:
        print(f"Cloud API error: {error_msg}", file=sys.stderr)

    sys.exit(1)


def handle_ssh_error(debug_mode: bool) -> None:
    """Handle SSH connectivity error.

    Parameters
    ----------
    debug_mode : bool
        Whether debug mode is enabled

    Raises
    ------
    OSError, paramiko.SSHException, paramiko.AuthenticationException
        Re-raised if debug mode is enabled
    """
    if debug_mode:
        raise

    print("SSH connectivity error\n", file=sys.stderr)
    print("This usually means:", file=sys.stderr)
    print("  - Instance not yet ready", file=sys.stderr)
    print("  - Security group blocking SSH", file=sys.stderr)
    print("  - Network connectivity issues\n", file=sys.stderr)
    print("Debugging steps:", file=sys.stderr)
    print("  1. Wait 30-60 seconds and try again", file=sys.stderr)
    print("  2. Check security group allows port 22", file=sys.stderr)
    print("  3. Verify instance is running: campers list", file=sys.stderr)
    sys.exit(1)


def handle_runtime_error(error: RuntimeError, debug_mode: bool) -> None:
    """Handle unexpected runtime error.

    Parameters
    ----------
    error : RuntimeError
        The runtime error that was raised
    debug_mode : bool
        Whether debug mode is enabled

    Raises
    ------
    RuntimeError
        Re-raised if debug mode is enabled
    """
    if debug_mode:
        raise

    print(f"Unexpected error: {error}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    """Entry point for Fire CLI with graceful error handling.

    This function initializes the Fire CLI interface by passing the CampersCLI
    class to Fire, which automatically generates CLI commands from the class
    methods. The function should be called when the script is executed directly.

    Notes
    -----
    Fire automatically maps class methods to CLI commands and handles argument
    parsing, help text generation, and command routing.
    """
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(StreamFormatter("%(message)s"))
    stdout_handler.addFilter(StreamRoutingFilter("stdout"))

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(StreamFormatter("%(message)s"))
    stderr_handler.addFilter(StreamRoutingFilter("stderr"))

    logging.basicConfig(
        level=logging.INFO,
        handlers=[stdout_handler, stderr_handler],
    )

    debug_mode = os.environ.get("CAMPERS_DEBUG") == "1"

    try:
        fire.Fire(CampersCLI())
    except ProviderCredentialsError:
        handle_credentials_error(debug_mode)
    except ValueError as e:
        handle_value_error(e, debug_mode)
    except ProviderAPIError as e:
        handle_api_error(e, debug_mode)
    except (OSError, paramiko.SSHException, paramiko.AuthenticationException):
        handle_ssh_error(debug_mode)
    except RuntimeError as e:
        handle_runtime_error(e, debug_mode)
