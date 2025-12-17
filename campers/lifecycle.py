from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from campers.core.config import ConfigLoader
from campers.core.interfaces import ComputeProvider
from campers.core.utils import get_volume_size_or_default
from campers.providers import get_provider
from campers.providers.exceptions import ProviderAPIError, ProviderCredentialsError
from campers.utils import format_time_ago, get_user_identity, status_spinner


class LifecycleManager:
    """Manages cloud instance lifecycle commands (list, stop, start, destroy, info).

    Parameters
    ----------
    config_loader : ConfigLoader
        Configuration loader instance
    compute_provider_factory : Callable[..., ComputeProvider]
        Factory function to create compute provider instances
    truncate_name : Callable[[str, int], str]
        Function to truncate instance names for display
    """

    def __init__(
        self,
        config_loader: ConfigLoader,
        compute_provider_factory: Callable[..., ComputeProvider],
        truncate_name: Callable[[str, int], str],
    ) -> None:
        self.config_loader = config_loader
        self.compute_provider_factory = compute_provider_factory
        self.truncate_name = truncate_name

    def _get_pricing_service_and_functions(
        self, provider_name: str = "aws"
    ) -> tuple[Any, Any, Any]:
        """Get PricingService and pricing functions from provider registry.

        Parameters
        ----------
        provider_name : str
            Name of the provider (default: "aws")

        Returns
        -------
        tuple[Any, Any, Any]
            Tuple of (PricingService class, calculate_monthly_cost function, format_cost function)
        """
        from campers.constants import DEFAULT_PROVIDER

        provider = get_provider(DEFAULT_PROVIDER)
        return (
            provider["pricing_service"],
            provider["calculate_monthly_cost"],
            provider["format_cost"],
        )

    def _build_list_header(self, show_all: bool, region: str | None) -> tuple[str, int]:
        """Build table header for list output.

        Parameters
        ----------
        show_all : bool
            Whether to show all instances or filter by current user
        region : str | None
            Whether region filter is applied

        Returns
        -------
        tuple[str, int]
            Header string and separator width
        """
        if region:
            if show_all:
                header = (
                    f"{'NAME':<20} {'INSTANCE-ID':<20} {'STATUS':<12} {'OWNER':<25} "
                    f"{'TYPE':<15} {'LAUNCHED':<12} {'COST/MONTH':<21}"
                )
                separator_width = 125
            else:
                header = (
                    f"{'NAME':<20} {'INSTANCE-ID':<20} {'STATUS':<12} {'TYPE':<15} "
                    f"{'LAUNCHED':<12} {'COST/MONTH':<21}"
                )
                separator_width = 100
        else:
            if show_all:
                header = (
                    f"{'NAME':<20} {'INSTANCE-ID':<20} {'STATUS':<12} {'OWNER':<25} "
                    f"{'REGION':<15} {'TYPE':<15} {'LAUNCHED':<12} {'COST/MONTH':<21}"
                )
                separator_width = 140
            else:
                header = (
                    f"{'NAME':<20} {'INSTANCE-ID':<20} {'STATUS':<12} {'REGION':<15} "
                    f"{'TYPE':<15} {'LAUNCHED':<12} {'COST/MONTH':<21}"
                )
                separator_width = 115

        return header, separator_width

    def _build_list_row(self, inst: dict[str, Any], show_all: bool, region: str | None) -> str:
        """Build table row for list output.

        Parameters
        ----------
        inst : dict[str, Any]
            Instance data from list_instances
        show_all : bool
            Whether to show all instances or filter by current user
        region : str | None
            Whether region filter is applied

        Returns
        -------
        str
            Formatted row string
        """
        name = self.truncate_name(inst["camp_config"])
        launched = format_time_ago(inst["launch_time"])
        cost_str = inst.get("cost_str", "")

        if region:
            if show_all:
                owner = inst.get("owner", "unknown")
                row = (
                    f"{name:<20} {inst['instance_id']:<20} {inst['state']:<12} "
                    f"{owner:<25} {inst['instance_type']:<15} {launched:<12} "
                    f"{cost_str:<21}"
                )
            else:
                row = (
                    f"{name:<20} {inst['instance_id']:<20} {inst['state']:<12} "
                    f"{inst['instance_type']:<15} {launched:<12} {cost_str:<21}"
                )
        else:
            if show_all:
                owner = inst.get("owner", "unknown")
                row = (
                    f"{name:<20} {inst['instance_id']:<20} {inst['state']:<12} "
                    f"{owner:<25} {inst['region']:<15} {inst['instance_type']:<15} "
                    f"{launched:<12} {cost_str:<21}"
                )
            else:
                row = (
                    f"{name:<20} {inst['instance_id']:<20} {inst['state']:<12} "
                    f"{inst['region']:<15} {inst['instance_type']:<15} {launched:<12} "
                    f"{cost_str:<21}"
                )

        return row

    def _validate_region(self, region: str) -> None:
        """Validate that a region is valid using the compute provider.

        Parameters
        ----------
        region : str
            Region to validate

        Raises
        ------
        ValueError
            If region is not valid
        """
        default_region = self.config_loader.BUILT_IN_DEFAULTS["region"]
        compute_provider = self.compute_provider_factory(region=default_region)
        compute_provider.validate_region(region)

    def _find_and_validate_instance(
        self, name_or_id: str, region: str | None, operation_name: str
    ) -> dict[str, Any] | None:
        """Find instance and validate single match.

        Parameters
        ----------
        name_or_id : str
            Instance ID or MachineConfig name
        region : str | None
            Optional cloud region to narrow search
        operation_name : str
            Name of operation for error messages

        Returns
        -------
        dict[str, Any] | None
            Instance details if found and unique, None if not found, exits if multiple matches
        """
        default_region = self.config_loader.BUILT_IN_DEFAULTS["region"]
        search_manager = self.compute_provider_factory(region=region or default_region)
        matches = search_manager.find_instances_by_name_or_id(
            name_or_id=name_or_id, region_filter=region
        )

        if not matches:
            logging.error(
                "No campers-managed instances matched '%s'.",
                name_or_id,
                extra={"stream": "stderr"},
            )
            sys.exit(1)

        if len(matches) > 1:
            logging.error(
                "Ambiguous machine config '%s'; matches multiple instances.",
                name_or_id,
            )
            logging.error(
                f"Multiple instances found. Please use a specific instance ID to {operation_name}:",
                extra={"stream": "stderr"},
            )

            for match in matches:
                logging.error(
                    f"  {match['instance_id']} ({match['region']})",
                    extra={"stream": "stderr"},
                )

            sys.exit(1)

        return matches[0]

    def list(self, region: str | None = None, show_all: bool = False) -> None:
        """List all campers-managed cloud instances.

        Parameters
        ----------
        region : str | None
            Optional cloud region to filter results
        show_all : bool
            If False, filter to show only current user's instances.
            If True, show all instances from all users.

        Raises
        ------
        ProviderCredentialsError
            If cloud provider credentials are not configured
        ProviderAPIError
            If cloud provider API calls fail
        ValueError
            If provided region is not a valid cloud region
        """
        default_region = self.config_loader.BUILT_IN_DEFAULTS["region"]

        if region is not None:
            self._validate_region(region)

        try:
            compute_provider = self.compute_provider_factory(region=region or default_region)

            with status_spinner("Fetching instances"):
                instances = compute_provider.list_instances(region_filter=region)

            current_user = get_user_identity()

            if not show_all:
                instances = [i for i in instances if i.get("owner") == current_user]

            if not instances:
                logging.info("No campers-managed instances found", extra={"stream": "stdout"})
                return

            (
                PricingService,
                calculate_monthly_cost,
                format_cost,
            ) = self._get_pricing_service_and_functions()
            pricing_service = PricingService()

            try:
                if not pricing_service.pricing_available:
                    logging.info("ℹ️  Pricing unavailable", extra={"stream": "stdout"})

                total_monthly_cost = 0.0
                costs_available = False

                with status_spinner("Calculating costs"):
                    for inst in instances:
                        regional_manager = self.compute_provider_factory(region=inst["region"])
                        volume_size = regional_manager.get_volume_size(inst["instance_id"])

                        if volume_size is None:
                            volume_size = 0

                        monthly_cost = calculate_monthly_cost(
                            instance_type=inst["instance_type"],
                            region=inst["region"],
                            state=inst["state"],
                            volume_size_gb=volume_size,
                            pricing_service=pricing_service,
                        )

                        if monthly_cost is not None:
                            total_monthly_cost += monthly_cost
                            costs_available = True

                        inst["monthly_cost"] = monthly_cost
                        inst["volume_size"] = volume_size
                        inst["cost_str"] = format_cost(monthly_cost)

                if not show_all:
                    logging.info(
                        f"Instances for {current_user}:",
                        extra={"stream": "stdout"},
                    )

                header, separator_width = self._build_list_header(show_all, region)
                logging.info(header, extra={"stream": "stdout"})
                logging.info("-" * separator_width, extra={"stream": "stdout"})

                for inst in instances:
                    row = self._build_list_row(inst, show_all, region)
                    logging.info(row, extra={"stream": "stdout"})

                if costs_available:
                    logging.info(
                        f"Total estimated cost: {format_cost(total_monthly_cost)}",
                        extra={"stream": "stdout"},
                    )
            finally:
                pricing_service.close()

        except ProviderCredentialsError:
            logging.error(
                "Error: Cloud provider credentials not found. Please configure credentials.",
                extra={"stream": "stderr"},
            )
            raise
        except ProviderAPIError as e:
            if e.error_code == "UnauthorizedOperation":
                logging.error(
                    "Error: Insufficient cloud provider permissions to list instances.",
                    extra={"stream": "stderr"},
                )
                raise

            raise

    def stop(self, name_or_id: str, region: str | None = None) -> None:
        """Stop a running campers-managed cloud instance by MachineConfig or ID.

        Parameters
        ----------
        name_or_id : str
            Instance ID or MachineConfig name to stop
        region : str | None
            Optional cloud region to narrow search scope

        Raises
        ------
        SystemExit
            Exits with code 1 if no instance matches, multiple instances match,
            or cloud errors occur. Returns normally on successful stop.
        """
        if region:
            self._validate_region(region)

        target: dict[str, Any] | None = None

        try:
            with status_spinner("Finding instance"):
                target = self._find_and_validate_instance(name_or_id, region, "stop")
            instance_id = target["instance_id"]
            state = target.get("state", "unknown")

            if state == "stopped":
                logging.info("Instance already stopped", extra={"stream": "stdout"})
                return

            if state == "stopping":
                logging.error(
                    "Instance %s is already stopping. Please wait for it to reach stopped state.",
                    instance_id,
                    extra={"stream": "stderr"},
                )
                sys.exit(1)

            if state in ("terminated", "shutting-down"):
                logging.error(
                    "Cannot stop instance %s - it is %s.",
                    instance_id,
                    state,
                    extra={"stream": "stderr"},
                )
                sys.exit(1)

            if state not in ("running", "pending"):
                logging.error(
                    "Instance %s is in state '%s' and cannot be stopped. "
                    "Valid states for stopping: running, pending",
                    instance_id,
                    state,
                    extra={"stream": "stderr"},
                )
                sys.exit(1)

            logging.info(
                "Stopping instance %s (%s) in %s...",
                instance_id,
                target["camp_config"],
                target["region"],
            )

            regional_manager = self.compute_provider_factory(region=target["region"])
            volume_size = get_volume_size_or_default(regional_manager, instance_id)

            (
                PricingService,
                calculate_monthly_cost,
                format_cost,
            ) = self._get_pricing_service_and_functions()
            pricing_service = PricingService()

            try:
                running_cost = calculate_monthly_cost(
                    instance_type=target["instance_type"],
                    region=target["region"],
                    state="running",
                    volume_size_gb=volume_size,
                    pricing_service=pricing_service,
                )

                stopped_cost = calculate_monthly_cost(
                    instance_type=target["instance_type"],
                    region=target["region"],
                    state="stopped",
                    volume_size_gb=volume_size,
                    pricing_service=pricing_service,
                )

                with status_spinner("Stopping instance"):
                    regional_manager.stop_instance(instance_id)

                logging.info(
                    f"Instance {instance_id} has been successfully stopped.",
                    extra={"stream": "stdout"},
                )

                if running_cost is not None and stopped_cost is not None:
                    savings = running_cost - stopped_cost
                    savings_pct = (savings / running_cost * 100) if running_cost > 0 else 0

                    logging.info("\U0001f4b0 Cost Impact:", extra={"stream": "stdout"})
                    logging.info(
                        f"  Previous: {format_cost(running_cost)}", extra={"stream": "stdout"}
                    )
                    logging.info(f"  New: {format_cost(stopped_cost)}", extra={"stream": "stdout"})
                    logging.info(
                        f"  Savings: {format_cost(savings)} (~{savings_pct:.0f}% reduction)",
                        extra={"stream": "stdout"},
                    )
                else:
                    logging.info("(Cost information unavailable)", extra={"stream": "stdout"})

                logging.info(
                    f"Restart with: campers start {instance_id}", extra={"stream": "stdout"}
                )
            finally:
                pricing_service.close()

        except RuntimeError as e:
            if target is not None:
                logging.error(
                    "Failed to stop instance %s: %s",
                    target["instance_id"],
                    str(e),
                    extra={"stream": "stderr"},
                )
            else:
                logging.error(
                    "Failed to stop instance: %s",
                    str(e),
                    extra={"stream": "stderr"},
                )

            sys.exit(1)
        except ProviderCredentialsError:
            logging.error(
                "Cloud provider credentials not configured. Please set up credentials.",
                extra={"stream": "stderr"},
            )
            sys.exit(1)
        except ProviderAPIError as e:
            if e.error_code == "UnauthorizedOperation":
                logging.error(
                    "Insufficient cloud provider permissions to perform this operation.",
                    extra={"stream": "stderr"},
                )
                sys.exit(1)

            logging.error(
                "Cloud provider API error: %s",
                e,
                extra={"stream": "stderr"},
            )
            sys.exit(1)

    def start(self, name_or_id: str, region: str | None = None) -> None:
        """Start a stopped campers-managed cloud instance by MachineConfig or ID.

        Parameters
        ----------
        name_or_id : str
            Instance ID or MachineConfig name to start
        region : str | None
            Optional cloud region to narrow search scope

        Raises
        ------
        SystemExit
            Exits with code 1 if no instance matches, multiple instances match,
            or cloud errors occur. Returns normally on successful start.
        """
        if region:
            self._validate_region(region)

        target: dict[str, Any] | None = None

        try:
            with status_spinner("Finding instance"):
                target = self._find_and_validate_instance(name_or_id, region, "start")
            instance_id = target["instance_id"]
            state = target.get("state", "unknown")

            if state == "running":
                ip = target.get("public_ip", "N/A")
                logging.info("Instance already running", extra={"stream": "stdout"})
                logging.info(f"  Public IP: {ip}", extra={"stream": "stdout"})
                return

            if state == "pending":
                logging.error(
                    (
                        "Instance is not in stopped state (Instance ID: %s, "
                        "Current state: %s). Please wait for instance to reach "
                        "stopped state."
                    ),
                    instance_id,
                    state,
                    extra={"stream": "stderr"},
                )
                sys.exit(1)

            if state in ("terminated", "shutting-down"):
                logging.error(
                    "Cannot start instance %s - it is %s.",
                    instance_id,
                    state,
                    extra={"stream": "stderr"},
                )
                sys.exit(1)

            if state != "stopped":
                logging.error(
                    "Instance is not in stopped state (Instance ID: %s, Current state: %s). "
                    "Valid state for starting: stopped",
                    instance_id,
                    state,
                    extra={"stream": "stderr"},
                )
                sys.exit(1)

            logging.info(
                "Starting instance %s (%s) in %s...",
                instance_id,
                target["camp_config"],
                target["region"],
            )

            regional_manager = self.compute_provider_factory(region=target["region"])
            volume_size = get_volume_size_or_default(regional_manager, instance_id)

            (
                PricingService,
                calculate_monthly_cost,
                format_cost,
            ) = self._get_pricing_service_and_functions()
            pricing_service = PricingService()

            try:
                stopped_cost = calculate_monthly_cost(
                    instance_type=target["instance_type"],
                    region=target["region"],
                    state="stopped",
                    volume_size_gb=volume_size,
                    pricing_service=pricing_service,
                )

                running_cost = calculate_monthly_cost(
                    instance_type=target["instance_type"],
                    region=target["region"],
                    state="running",
                    volume_size_gb=volume_size,
                    pricing_service=pricing_service,
                )

                with status_spinner("Starting instance"):
                    instance_details = regional_manager.start_instance(instance_id)

                new_ip = instance_details.get("public_ip", "N/A")
                logging.info(
                    f"Instance {instance_id} has been successfully started.",
                    extra={"stream": "stdout"},
                )
                logging.info(f"  Public IP: {new_ip}", extra={"stream": "stdout"})

                if stopped_cost is not None and running_cost is not None:
                    increase = running_cost - stopped_cost

                    logging.info("\U0001f4b0 Cost Impact:", extra={"stream": "stdout"})
                    logging.info(
                        f"  Previous: {format_cost(stopped_cost)}", extra={"stream": "stdout"}
                    )
                    logging.info(f"  New: {format_cost(running_cost)}", extra={"stream": "stdout"})
                    logging.info(
                        f"  Increase: {format_cost(increase)}/month", extra={"stream": "stdout"}
                    )
                else:
                    logging.info("(Cost information unavailable)", extra={"stream": "stdout"})

                logging.info(
                    "To establish SSH/Mutagen/ports: campers run <machine>",
                    extra={"stream": "stdout"},
                )
            finally:
                pricing_service.close()

        except RuntimeError as e:
            if target is not None:
                logging.error(
                    "Failed to start instance %s: %s",
                    target["instance_id"],
                    str(e),
                    extra={"stream": "stderr"},
                )
            else:
                logging.error(
                    "Failed to start instance: %s",
                    str(e),
                    extra={"stream": "stderr"},
                )

            sys.exit(1)
        except ProviderCredentialsError:
            logging.error(
                "Cloud provider credentials not configured. Please set up credentials.",
                extra={"stream": "stderr"},
            )
            sys.exit(1)
        except ProviderAPIError as e:
            if e.error_code == "UnauthorizedOperation":
                logging.error(
                    "Insufficient cloud provider permissions to perform this operation.",
                    extra={"stream": "stderr"},
                )
                sys.exit(1)

            logging.error(
                "Cloud provider API error: %s",
                e,
                extra={"stream": "stderr"},
            )
            sys.exit(1)

    def info(self, name_or_id: str, region: str | None = None) -> None:
        """Display detailed information about a campers-managed cloud instance.

        Parameters
        ----------
        name_or_id : str
            Instance ID or MachineConfig name
        region : str | None
            Optional cloud region to narrow search scope

        Raises
        ------
        SystemExit
            Exits with code 1 if no instance matches, multiple instances match,
            or cloud errors occur. Returns normally on successful info display.
        """
        if region:
            self._validate_region(region)

        target: dict[str, Any] | None = None

        try:
            with status_spinner("Fetching instance info"):
                target = self._find_and_validate_instance(name_or_id, region, "view")
                instance_id = target["instance_id"]
                regional_manager = self.compute_provider_factory(region=target["region"])

                unique_id = target.get("unique_id")
                public_ports = []

                if not unique_id:
                    try:
                        tags = regional_manager.get_instance_tags(instance_id)
                        unique_id = tags.get("UniqueId")
                        machine_config = tags.get("MachineConfig")

                        if machine_config and machine_config != "ad-hoc":
                            try:
                                full_config = self.config_loader.load_config()
                                camp_config = self.config_loader.get_camp_config(
                                    full_config, machine_config
                                )
                                public_ports = camp_config.get("public_ports", [])
                            except (ValueError, KeyError, AttributeError) as e:
                                logging.debug("Failed to load camp config for public ports: %s", e)
                    except (AttributeError, KeyError) as e:
                        logging.debug("Failed to get tags from instance: %s", e)

                try:
                    instance_details = regional_manager.describe_instance(instance_id)
                    if instance_details:
                        target["public_ip"] = instance_details.get("public_ip")
                except (AttributeError, RuntimeError) as e:
                    logging.debug("Failed to get public IP from instance details: %s", e)

                camp_config_name = target.get("camp_config")
                if not public_ports and camp_config_name and camp_config_name != "ad-hoc":
                    try:
                        full_config = self.config_loader.load_config()
                        camp_config = self.config_loader.get_camp_config(
                            full_config, camp_config_name
                        )
                        public_ports = camp_config.get("public_ports", [])
                    except (ValueError, KeyError, AttributeError) as e:
                        logging.debug("Failed to load camp config for public ports: %s", e)

                if public_ports:
                    target["public_ports"] = public_ports

            key_file = None
            if unique_id:
                key_file = f"~/.campers/keys/{unique_id}.pem"

            launch_time = target.get("launch_time")
            if isinstance(launch_time, str):
                try:
                    launch_time = datetime.fromisoformat(launch_time.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    launch_time = None

            launch_time_str = launch_time.isoformat() if launch_time else "Unknown"

            now_utc = datetime.now(UTC)
            if launch_time:
                try:
                    if launch_time.tzinfo is None:
                        launch_time = launch_time.replace(tzinfo=UTC)
                    elapsed = now_utc - launch_time
                    total_seconds = int(elapsed.total_seconds())
                    if total_seconds < 0:
                        total_seconds = 0

                    hours = total_seconds // 3600
                    minutes = (total_seconds % 3600) // 60

                    uptime_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
                except (TypeError, ValueError):
                    uptime_str = "Unknown"
            else:
                uptime_str = "Unknown"

            logging.info(
                f"Instance Information: {target.get('camp_config', 'N/A')}",
                extra={"stream": "stdout"},
            )
            logging.info(f"  Instance ID: {instance_id}", extra={"stream": "stdout"})
            logging.info(f"  State: {target.get('state', 'Unknown')}", extra={"stream": "stdout"})
            logging.info(
                f"  Instance Type: {target.get('instance_type', 'N/A')}", extra={"stream": "stdout"}
            )
            logging.info(f"  Region: {target['region']}", extra={"stream": "stdout"})
            logging.info(f"  Launch Time: {launch_time_str}", extra={"stream": "stdout"})
            logging.info(
                f"  Unique ID: {unique_id if unique_id else 'N/A'}", extra={"stream": "stdout"}
            )
            logging.info(
                f"  Key File: {key_file if key_file else 'N/A'}", extra={"stream": "stdout"}
            )
            logging.info(f"  Uptime: {uptime_str}", extra={"stream": "stdout"})

            public_ports = target.get("public_ports", [])
            public_ip = target.get("public_ip")
            if public_ports and public_ip:
                logging.info("", extra={"stream": "stdout"})
                logging.info("  Public Access:", extra={"stream": "stdout"})
                for port in public_ports:
                    protocol = "https" if port == 443 else "http"
                    logging.info(f"    {protocol}://{public_ip}:{port}", extra={"stream": "stdout"})

        except ProviderCredentialsError:
            logging.error(
                "Cloud provider credentials not configured. Please set up credentials.",
                extra={"stream": "stderr"},
            )
            sys.exit(1)
        except ProviderAPIError as e:
            if e.error_code == "UnauthorizedOperation":
                logging.error(
                    "Insufficient cloud provider permissions to perform this operation.",
                    extra={"stream": "stderr"},
                )
                sys.exit(1)

            logging.error(
                "Cloud provider API error: %s",
                e,
                extra={"stream": "stderr"},
            )
            sys.exit(1)

    def destroy(self, name_or_id: str, region: str | None = None) -> None:
        """Destroy a campers-managed cloud instance by MachineConfig or ID.

        Parameters
        ----------
        name_or_id : str
            Instance ID or MachineConfig name to destroy
        region : str | None
            Optional cloud region to narrow search scope

        Raises
        ------
        SystemExit
            Exits with code 1 if no instance matches, multiple instances match,
            or cloud errors occur. Returns normally on successful termination.
        """
        if region:
            self._validate_region(region)

        target: dict[str, Any] | None = None

        try:
            with status_spinner("Finding instance"):
                target = self._find_and_validate_instance(name_or_id, region, "destroy")
            logging.info(
                "Terminating instance %s (%s) in %s...",
                target["instance_id"],
                target["camp_config"],
                target["region"],
            )

            regional_manager = self.compute_provider_factory(region=target["region"])

            with status_spinner("Terminating instance"):
                regional_manager.terminate_instance(target["instance_id"])

            logging.info(
                f"Instance {target['instance_id']} has been successfully terminated.",
                extra={"stream": "stdout"},
            )
        except RuntimeError as e:
            if target is not None:
                logging.error(
                    "Failed to terminate instance %s: %s",
                    target["instance_id"],
                    str(e),
                    extra={"stream": "stderr"},
                )
            else:
                logging.error(
                    "Failed to terminate instance: %s",
                    str(e),
                    extra={"stream": "stderr"},
                )

            sys.exit(1)
        except ProviderCredentialsError:
            logging.error(
                "Cloud provider credentials not configured. Please set up credentials.",
                extra={"stream": "stderr"},
            )
            sys.exit(1)
        except ProviderAPIError as e:
            if e.error_code == "UnauthorizedOperation":
                logging.error(
                    "Insufficient cloud provider permissions to perform this operation.",
                    extra={"stream": "stderr"},
                )
                sys.exit(1)

            logging.error(
                "Cloud provider API error: %s",
                e,
                extra={"stream": "stderr"},
            )
            sys.exit(1)
