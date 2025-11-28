"""CLI entry point for Campers."""

from __future__ import annotations

import logging
import os
import socket
import sys
from typing import Any

import fire
import paramiko
from botocore.exceptions import ClientError, NoCredentialsError

from campers.logging import StreamFormatter, StreamRoutingFilter


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
    compute_provider_factory : Callable[..., Any] | None
        Optional factory function for creating compute provider instances.
        If None, uses the default compute provider class.
    ssh_manager_factory : Callable[..., Any] | None
        Optional factory function for creating SSHManager instances.
        If None, uses the default SSHManager class.
    boto3_client_factory : Callable[..., Any] | None
        Optional factory function for creating boto3 clients.
        If None, uses the default boto3.client function.
    boto3_resource_factory : Callable[..., Any] | None
        Optional factory function for creating boto3 resources.
        If None, uses the default boto3.resource function.
    """

    _cached_class: type | None = None

    def __new__(
        cls,
        compute_provider_factory: Any | None = None,
        ssh_manager_factory: Any | None = None,
        boto3_client_factory: Any | None = None,
        boto3_resource_factory: Any | None = None,
    ) -> Any:
        """Create CampersCLI instance with dynamic subclassing.

        Parameters
        ----------
        compute_provider_factory : Callable[..., Any] | None
            Optional factory for compute provider (default: None, uses default provider)
        ssh_manager_factory : Callable[..., Any] | None
            Optional factory for SSHManager (default: None, uses SSHManager)
        boto3_client_factory : Callable[..., Any] | None
            Optional factory for boto3 clients (default: None, uses boto3.client)
        boto3_resource_factory : Callable[..., Any] | None
            Optional factory for boto3 resources (default: None, uses boto3.resource)

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
                    compute_provider_factory: Any | None = None,
                    ssh_manager_factory: Any | None = None,
                    boto3_client_factory: Any | None = None,
                    boto3_resource_factory: Any | None = None,
                ) -> None:
                    """Initialize CampersCLI with optional dependency injection.

                    Parameters
                    ----------
                    compute_provider_factory : Callable[..., Any] | None
                        Optional factory for compute provider (default: None, uses default provider)
                    ssh_manager_factory : Callable[..., Any] | None
                        Optional factory for SSHManager (default: None, uses SSHManager)
                    boto3_client_factory : Callable[..., Any] | None
                        Optional factory for boto3 clients (default: None, uses boto3.client)
                    boto3_resource_factory : Callable[..., Any] | None
                        Optional factory for boto3 resources (default: None, uses boto3.resource)
                    """
                    super().__init__(
                        compute_provider_factory=compute_provider_factory,
                        ssh_manager_factory=ssh_manager_factory,
                        boto3_client_factory=boto3_client_factory,
                        boto3_resource_factory=boto3_resource_factory,
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
                        Instance metadata dict or JSON string (never returns in TUI mode, exits instead)
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
            boto3_client_factory=boto3_client_factory,
            boto3_resource_factory=boto3_resource_factory,
        )


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
    except NoCredentialsError:
        if debug_mode:
            raise

        print("AWS credentials not found\n", file=sys.stderr)
        print("Configure your credentials:", file=sys.stderr)
        print("  aws configure\n", file=sys.stderr)
        print("Or set environment variables:", file=sys.stderr)
        print("  export AWS_ACCESS_KEY_ID=...", file=sys.stderr)
        print("  export AWS_SECRET_ACCESS_KEY=...", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        if debug_mode:
            raise

        error_msg = str(e)

        if "No default VPC" in error_msg:
            import re

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
            print(
                "startup_script requires sync_paths to be configured\n", file=sys.stderr
            )
            print("Add sync_paths to your configuration:", file=sys.stderr)
            print("  sync_paths:", file=sys.stderr)
            print("    - local: ./src", file=sys.stderr)
            print("      remote: /home/ubuntu/src", file=sys.stderr)
            sys.exit(1)
        else:
            print(f"Configuration error: {error_msg}", file=sys.stderr)
            sys.exit(2)
    except ClientError as e:
        if debug_mode:
            raise

        error_code = e.response.get("Error", {}).get("Code", "")
        error_msg = e.response.get("Error", {}).get("Message", str(e))

        if error_code == "UnauthorizedOperation":
            print("Insufficient IAM permissions\n", file=sys.stderr)
            print(
                "Your AWS credentials don't have the required permissions.",
                file=sys.stderr,
            )
            print("Contact your AWS administrator to grant:", file=sys.stderr)
            print(
                "  - Compute permissions (DescribeInstances, RunInstances, TerminateInstances)",
                file=sys.stderr,
            )
            print(
                "  - VPC permissions (DescribeVpcs, CreateDefaultVpc)", file=sys.stderr
            )
            print(
                "  - Key Pair permissions (CreateKeyPair, DeleteKeyPair, DescribeKeyPairs)",
                file=sys.stderr,
            )
            print("  - Security Group permissions", file=sys.stderr)
        elif (
            error_code == "InvalidParameterValue"
            and "instance type" in error_msg.lower()
        ):
            print("Invalid instance type\n", file=sys.stderr)
            print("This usually means:", file=sys.stderr)
            print("  - Instance type not available in this region", file=sys.stderr)
            print("  - Typo in instance type name\n", file=sys.stderr)
            print("Fix it:", file=sys.stderr)
            print("  campers doctor", file=sys.stderr)
            print("  campers run --instance-type t3.medium", file=sys.stderr)
        elif error_code in ["InstanceLimitExceeded", "RequestLimitExceeded"]:
            print("AWS quota exceeded\n", file=sys.stderr)
            print("This usually means:", file=sys.stderr)
            print("  - Too many instances running", file=sys.stderr)
            print("  - Need to request quota increase\n", file=sys.stderr)
            print("Fix it:", file=sys.stderr)
            print("  https://console.aws.amazon.com/servicequotas/", file=sys.stderr)
            print("  campers list", file=sys.stderr)
        elif error_code in ["ExpiredToken", "RequestExpired", "ExpiredTokenException"]:
            print("AWS credentials have expired\n", file=sys.stderr)
            print("This usually means:", file=sys.stderr)
            print("  - Your temporary credentials (STS) have expired", file=sys.stderr)
            print("  - Your session token needs to be refreshed\n", file=sys.stderr)
            print("Fix it:", file=sys.stderr)
            print("  aws sso login           # If using AWS SSO", file=sys.stderr)
            print(
                "  aws configure           # Re-configure credentials", file=sys.stderr
            )
            print("  # Or refresh your temporary credentials", file=sys.stderr)
        else:
            print(f"AWS API error: {error_msg}", file=sys.stderr)

        sys.exit(1)
    except (paramiko.SSHException, paramiko.AuthenticationException, socket.error):
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
    except Exception as e:
        if debug_mode:
            raise

        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)
