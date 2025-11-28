from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from typing import Any

from campers.providers.exceptions import ProviderAPIError, ProviderCredentialsError
from campers.providers.aws.pricing import (
    PricingService,
    calculate_monthly_cost,
    format_cost,
)
from campers.utils import format_time_ago


class LifecycleManager:
    """Manages cloud instance lifecycle commands (list, stop, start, destroy, info).

    Parameters
    ----------
    config_loader : Any
        Configuration loader instance
    compute_provider_factory : Any
        Factory function to create compute provider instances
    log_and_print_error : Any
        Function to log and print errors to stderr
    validate_region : Any
        Function to validate cloud region
    truncate_name : Any
        Function to truncate instance names for display
    """

    def __init__(
        self,
        config_loader: Any,
        compute_provider_factory: Any,
        log_and_print_error: Any,
        validate_region: Any,
        truncate_name: Any,
    ) -> None:
        self.config_loader = config_loader
        self.compute_provider_factory = compute_provider_factory
        self.log_and_print_error = log_and_print_error
        self.validate_region = validate_region
        self.truncate_name = truncate_name

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
            self.log_and_print_error(
                "No campers-managed instances matched '%s'.", name_or_id
            )
            sys.exit(1)

        if len(matches) > 1:
            logging.error(
                "Ambiguous machine config '%s'; matches multiple instances.",
                name_or_id,
            )
            print(
                f"Multiple instances found. Please use a specific instance ID to {operation_name}:",
                file=sys.stderr,
            )

            for match in matches:
                print(f"  {match['instance_id']} ({match['region']})", file=sys.stderr)

            sys.exit(1)

        return matches[0]

    def list(self, region: str | None = None) -> None:
        """List all campers-managed cloud instances.

        Parameters
        ----------
        region : str | None
            Optional cloud region to filter results

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
            self.validate_region(region)

        try:
            compute_provider = self.compute_provider_factory(
                region=region or default_region
            )
            instances = compute_provider.list_instances(region_filter=region)

            if not instances:
                print("No campers-managed instances found")
                return

            pricing_service = PricingService()

            if not pricing_service.pricing_available:
                print("ℹ️  Pricing unavailable\n")

            total_monthly_cost = 0.0
            costs_available = False

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

            if region:
                print(f"Instances in {region}:")
                print(
                    f"{'NAME':<20} {'INSTANCE-ID':<20} {'STATUS':<12} {'TYPE':<15} {'LAUNCHED':<12} {'COST/MONTH':<21}"
                )
                print("-" * 100)

                for inst in instances:
                    name = self.truncate_name(inst["camp_config"])
                    launched = format_time_ago(inst["launch_time"])
                    cost_str = format_cost(inst["monthly_cost"])
                    print(
                        f"{name:<20} {inst['instance_id']:<20} {inst['state']:<12} {inst['instance_type']:<15} {launched:<12} {cost_str:<21}"
                    )
            else:
                print(
                    f"{'NAME':<20} {'INSTANCE-ID':<20} {'STATUS':<12} {'REGION':<15} {'TYPE':<15} {'LAUNCHED':<12} {'COST/MONTH':<21}"
                )
                print("-" * 115)

                for inst in instances:
                    name = self.truncate_name(inst["camp_config"])
                    launched = format_time_ago(inst["launch_time"])
                    cost_str = format_cost(inst["monthly_cost"])
                    print(
                        f"{name:<20} {inst['instance_id']:<20} {inst['state']:<12} {inst['region']:<15} {inst['instance_type']:<15} {launched:<12} {cost_str:<21}"
                    )

            if costs_available:
                print(f"\nTotal estimated cost: {format_cost(total_monthly_cost)}")

        except ProviderCredentialsError:
            print(
                "Error: Cloud provider credentials not found. Please configure credentials."
            )
            raise
        except ProviderAPIError as e:
            if e.error_code == "UnauthorizedOperation":
                print(
                    "Error: Insufficient cloud provider permissions to list instances."
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
            self.validate_region(region)

        target: dict[str, Any] | None = None

        try:
            target = self._find_and_validate_instance(name_or_id, region, "stop")
            instance_id = target["instance_id"]
            state = target.get("state", "unknown")

            if state == "stopped":
                print("Instance already stopped")
                return

            if state == "stopping":
                self.log_and_print_error(
                    "Instance %s is already stopping. Please wait for it to reach stopped state.",
                    instance_id,
                )
                sys.exit(1)

            if state in ("terminated", "shutting-down"):
                self.log_and_print_error(
                    "Cannot stop instance %s - it is %s.",
                    instance_id,
                    state,
                )
                sys.exit(1)

            if state not in ("running", "pending"):
                self.log_and_print_error(
                    "Instance %s is in state '%s' and cannot be stopped. "
                    "Valid states for stopping: running, pending",
                    instance_id,
                    state,
                )
                sys.exit(1)

            logging.info(
                "Stopping instance %s (%s) in %s...",
                instance_id,
                target["camp_config"],
                target["region"],
            )

            regional_manager = self.compute_provider_factory(region=target["region"])
            volume_size = regional_manager.get_volume_size(instance_id)

            if volume_size is None:
                volume_size = 0

            pricing_service = PricingService()

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

            regional_manager.stop_instance(instance_id)

            print(f"\nInstance {instance_id} has been successfully stopped.")

            if running_cost is not None and stopped_cost is not None:
                savings = running_cost - stopped_cost
                savings_pct = (savings / running_cost * 100) if running_cost > 0 else 0

                print("\n💰 Cost Impact:")
                print(f"  Previous: {format_cost(running_cost)}")
                print(f"  New: {format_cost(stopped_cost)}")
                print(
                    f"  Savings: {format_cost(savings)} (~{savings_pct:.0f}% reduction)"
                )
            else:
                print("\n(Cost information unavailable)")

            print(f"\n  Restart with: campers start {instance_id}")

        except RuntimeError as e:
            if target is not None:
                self.log_and_print_error(
                    "Failed to stop instance %s: %s",
                    target["instance_id"],
                    str(e),
                )
            else:
                self.log_and_print_error("Failed to stop instance: %s", str(e))

            sys.exit(1)
        except ProviderCredentialsError:
            self.log_and_print_error(
                "Cloud provider credentials not configured. Please set up credentials."
            )
            sys.exit(1)
        except ProviderAPIError as e:
            if e.error_code == "UnauthorizedOperation":
                self.log_and_print_error(
                    "Insufficient cloud provider permissions to perform this operation."
                )
                sys.exit(1)

            self.log_and_print_error("Cloud provider API error: %s", e)
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
            self.validate_region(region)

        target: dict[str, Any] | None = None

        try:
            target = self._find_and_validate_instance(name_or_id, region, "start")
            instance_id = target["instance_id"]
            state = target.get("state", "unknown")

            if state == "running":
                ip = target.get("public_ip", "N/A")
                print("Instance already running")
                print(f"  Public IP: {ip}")
                return

            if state == "pending":
                self.log_and_print_error(
                    "Instance is not in stopped state (Instance ID: %s, Current state: %s). Please wait for instance to reach stopped state.",
                    instance_id,
                    state,
                )
                sys.exit(1)

            if state in ("terminated", "shutting-down"):
                self.log_and_print_error(
                    "Cannot start instance %s - it is %s.",
                    instance_id,
                    state,
                )
                sys.exit(1)

            if state != "stopped":
                self.log_and_print_error(
                    "Instance is not in stopped state (Instance ID: %s, Current state: %s). "
                    "Valid state for starting: stopped",
                    instance_id,
                    state,
                )
                sys.exit(1)

            logging.info(
                "Starting instance %s (%s) in %s...",
                instance_id,
                target["camp_config"],
                target["region"],
            )

            regional_manager = self.compute_provider_factory(region=target["region"])
            volume_size = regional_manager.get_volume_size(instance_id)

            if volume_size is None:
                volume_size = 0

            pricing_service = PricingService()

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

            instance_details = regional_manager.start_instance(instance_id)

            new_ip = instance_details.get("public_ip", "N/A")
            print(f"\nInstance {instance_id} has been successfully started.")
            print(f"  Public IP: {new_ip}")

            if stopped_cost is not None and running_cost is not None:
                increase = running_cost - stopped_cost

                print("\n💰 Cost Impact:")
                print(f"  Previous: {format_cost(stopped_cost)}")
                print(f"  New: {format_cost(running_cost)}")
                print(f"  Increase: {format_cost(increase)}/month")
            else:
                print("\n(Cost information unavailable)")

            print("\n  To establish SSH/Mutagen/ports: campers run <machine>")

        except RuntimeError as e:
            if target is not None:
                self.log_and_print_error(
                    "Failed to start instance %s: %s",
                    target["instance_id"],
                    str(e),
                )
            else:
                self.log_and_print_error("Failed to start instance: %s", str(e))

            sys.exit(1)
        except ProviderCredentialsError:
            self.log_and_print_error(
                "Cloud provider credentials not configured. Please set up credentials."
            )
            sys.exit(1)
        except ProviderAPIError as e:
            if e.error_code == "UnauthorizedOperation":
                self.log_and_print_error(
                    "Insufficient cloud provider permissions to perform this operation."
                )
                sys.exit(1)

            self.log_and_print_error("Cloud provider API error: %s", e)
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
            self.validate_region(region)

        target: dict[str, Any] | None = None

        try:
            target = self._find_and_validate_instance(name_or_id, region, "view")
            instance_id = target["instance_id"]
            regional_manager = self.compute_provider_factory(region=target["region"])

            unique_id = target.get("unique_id")
            if not unique_id:
                try:
                    response = regional_manager.ec2_client.describe_instances(
                        InstanceIds=[instance_id]
                    )
                    instance = response["Reservations"][0]["Instances"][0]

                    tags = instance.get("Tags", [])
                    for tag in tags:
                        if tag["Key"] == "UniqueId":
                            unique_id = tag["Value"]
                            break
                except (AttributeError, KeyError):
                    pass

            key_file = None
            if unique_id:
                key_file = f"~/.campers/keys/{unique_id}.pem"

            launch_time = target.get("launch_time")
            if isinstance(launch_time, str):
                try:
                    launch_time = datetime.fromisoformat(
                        launch_time.replace("Z", "+00:00")
                    )
                except (ValueError, AttributeError):
                    launch_time = None

            launch_time_str = launch_time.isoformat() if launch_time else "Unknown"

            now_utc = datetime.now(timezone.utc)
            if launch_time:
                try:
                    if launch_time.tzinfo is None:
                        launch_time = launch_time.replace(tzinfo=timezone.utc)
                    elapsed = now_utc - launch_time
                    total_seconds = int(elapsed.total_seconds())
                    if total_seconds < 0:
                        total_seconds = 0

                    hours = total_seconds // 3600
                    minutes = (total_seconds % 3600) // 60

                    if hours > 0:
                        uptime_str = f"{hours}h {minutes}m"
                    else:
                        uptime_str = f"{minutes}m"
                except (TypeError, ValueError):
                    uptime_str = "Unknown"
            else:
                uptime_str = "Unknown"

            print(f"Instance Information: {target.get('camp_config', 'N/A')}")
            print(f"  Instance ID: {instance_id}")
            print(f"  State: {target.get('state', 'Unknown')}")
            print(f"  Instance Type: {target.get('instance_type', 'N/A')}")
            print(f"  Region: {target['region']}")
            print(f"  Launch Time: {launch_time_str}")
            print(f"  Unique ID: {unique_id if unique_id else 'N/A'}")
            print(f"  Key File: {key_file if key_file else 'N/A'}")
            print(f"  Uptime: {uptime_str}")

        except ProviderCredentialsError:
            self.log_and_print_error(
                "Cloud provider credentials not configured. Please set up credentials."
            )
            sys.exit(1)
        except ProviderAPIError as e:
            if e.error_code == "UnauthorizedOperation":
                self.log_and_print_error(
                    "Insufficient cloud provider permissions to perform this operation."
                )
                sys.exit(1)

            self.log_and_print_error("Cloud provider API error: %s", e)
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
            self.validate_region(region)

        target: dict[str, Any] | None = None

        try:
            target = self._find_and_validate_instance(name_or_id, region, "destroy")
            logging.info(
                "Terminating instance %s (%s) in %s...",
                target["instance_id"],
                target["camp_config"],
                target["region"],
            )

            regional_manager = self.compute_provider_factory(region=target["region"])
            regional_manager.terminate_instance(target["instance_id"])

            print(f"Instance {target['instance_id']} has been successfully terminated.")
        except RuntimeError as e:
            if target is not None:
                self.log_and_print_error(
                    "Failed to terminate instance %s: %s",
                    target["instance_id"],
                    str(e),
                )
            else:
                self.log_and_print_error("Failed to terminate instance: %s", str(e))

            sys.exit(1)
        except ProviderCredentialsError:
            self.log_and_print_error(
                "Cloud provider credentials not configured. Please set up credentials."
            )
            sys.exit(1)
        except ProviderAPIError as e:
            if e.error_code == "UnauthorizedOperation":
                self.log_and_print_error(
                    "Insufficient cloud provider permissions to perform this operation."
                )
                sys.exit(1)

            self.log_and_print_error("Cloud provider API error: %s", e)
            sys.exit(1)
