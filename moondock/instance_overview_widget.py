"""TUI widget for displaying aggregate instance counts and daily burn rate."""

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from textual.widgets import Static

if TYPE_CHECKING:
    from moondock import Moondock

logger = logging.getLogger(__name__)


class InstanceOverviewWidget(Static):
    """Displays aggregate instance counts and daily burn rate across all regions.

    Parameters
    ----------
    moondock_instance : Moondock
        Moondock instance providing access to ec2_manager_factory for creating
        EC2 managers

    Attributes
    ----------
    running_count : int
        Count of running instances across all regions
    stopped_count : int
        Count of stopped instances across all regions
    daily_cost : float | None
        Estimated daily burn rate, None if pricing unavailable
    last_update : datetime | None
        Timestamp of last successful stats refresh
    """

    DEFAULT_CLASSES = "instance-overview"

    def __init__(self, moondock_instance: "Moondock") -> None:
        super().__init__(id="instance-overview-widget")
        from moondock.config import ConfigLoader
        from moondock.pricing import PricingService

        default_region = ConfigLoader.BUILT_IN_DEFAULTS["region"]
        self.ec2_manager = moondock_instance.ec2_manager_factory(region=default_region)
        self.pricing_service = PricingService()
        self.running_count = 0
        self.stopped_count = 0
        self.daily_cost: Optional[float] = None
        self.last_update: Optional[datetime] = None
        self._interval_timer = None

    async def on_mount(self) -> None:
        """Initialize widget: refresh stats immediately and start 30-second interval."""
        await self.refresh_stats()
        self._interval_timer = self.set_interval(30, self.refresh_stats)

    async def on_unmount(self) -> None:
        """Clean up interval timer when widget is unmounted."""
        if self._interval_timer is not None:
            self._interval_timer.stop()

    async def refresh_stats(self) -> None:
        """Query EC2 API for all instances across regions and calculate costs.

        Maintains last known state if API call fails. Logs errors at DEBUG level only.
        """
        try:
            all_instances = self.ec2_manager.list_instances(region_filter=None)

            running = [i for i in all_instances if i["state"] == "running"]
            stopped = [i for i in all_instances if i["state"] == "stopped"]

            self.running_count = len(running)
            self.stopped_count = len(stopped)

            if self.pricing_service.pricing_available:
                from moondock.pricing import calculate_monthly_cost

                monthly_costs = [
                    calculate_monthly_cost(
                        instance_type=i["instance_type"],
                        region=i["region"],
                        state="running",
                        volume_size_gb=i.get("volume_size", 100),
                        pricing_service=self.pricing_service,
                    )
                    for i in running
                ]
                total_monthly = sum(c for c in monthly_costs if c is not None)
                has_valid_pricing = any(c is not None for c in monthly_costs)
                self.daily_cost = total_monthly / 30 if has_valid_pricing else None
            else:
                self.daily_cost = None

            self.last_update = datetime.now()
            self.update(self.render_stats())

        except Exception as e:
            logger.debug(f"Failed to refresh instance stats: {e}")

    def render_stats(self) -> str:
        """Format stats for display.

        Returns
        -------
        str
            Formatted string "Running: X  Stopped: Y  $Z/day"
            or "Running: X  Stopped: Y  N/A"
        """
        cost_str = f"${self.daily_cost:.2f}/day" if self.daily_cost else "N/A"
        return (
            f"Running: {self.running_count}  Stopped: {self.stopped_count}  {cost_str}"
        )
