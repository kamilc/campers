"""TUI widget for displaying aggregate instance counts and daily burn rate."""

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from textual.widgets import Static

from campers.constants import DEFAULT_PROVIDER, STATS_REFRESH_INTERVAL_SECONDS
from campers.core.interfaces import ComputeProvider, PricingProvider
from campers.providers import get_provider
from campers.providers.exceptions import ProviderError

if TYPE_CHECKING:
    from campers import Campers

logger = logging.getLogger(__name__)


class InstanceOverviewWidget(Static):
    """Displays aggregate instance counts and daily burn rate across all regions.

    Parameters
    ----------
    campers_instance : Campers
        Campers instance providing access to compute provider factory for creating
        compute providers

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

    def __init__(self, campers_instance: "Campers") -> None:
        super().__init__("Initializing...", id="instance-overview-widget")
        self._campers_instance = campers_instance
        self._compute_provider_factory = (
            campers_instance._compute_provider_factory_override
            or campers_instance._create_compute_provider
        )
        self.compute_provider: ComputeProvider | None = None
        self.pricing_service: PricingProvider | None = None
        self.running_count = 0
        self.stopped_count = 0
        self.daily_cost: float | None = None
        self.last_update: datetime | None = None
        self._interval_timer = None
        self._initialized = False

    async def on_mount(self) -> None:
        """Initialize widget: defer AWS initialization to background worker."""
        self.run_worker(self._initialize_services, thread=True)

    async def on_unmount(self) -> None:
        """Clean up interval timer when widget is unmounted."""
        if self._interval_timer is not None:
            self._interval_timer.stop()

    def _initialize_services(self) -> None:
        """Initialize cloud provider services in background thread."""
        from campers.core.config import ConfigLoader

        try:
            default_region = ConfigLoader().BUILT_IN_DEFAULTS["region"]
            self.compute_provider = self._compute_provider_factory(region=default_region)
            provider_info = get_provider(DEFAULT_PROVIDER)
            pricing_class = provider_info["pricing"]
            self.pricing_service = pricing_class()
            self._initialized = True
            self.app.call_from_thread(self._start_refresh_timer)
        except (RuntimeError, ValueError, OSError) as e:
            logger.warning("Failed to initialize cloud provider services: %s", e)
            self.app.call_from_thread(self._show_init_error)

    def _start_refresh_timer(self) -> None:
        """Start the refresh timer and do initial refresh after initialization."""
        self._interval_timer = self.set_interval(STATS_REFRESH_INTERVAL_SECONDS, self.refresh_stats)
        self.run_worker(self._refresh_stats_sync, thread=True)

    def _show_init_error(self) -> None:
        """Update widget to show initialization error."""
        self.update("AWS unavailable")

    def _refresh_stats_sync(self) -> None:
        """Synchronous version of refresh_stats for worker thread."""
        if not self._initialized or self.compute_provider is None:
            return

        try:
            all_instances = self.compute_provider.list_instances(region_filter=None)

            running = [i for i in all_instances if i["state"] == "running"]
            stopped = [i for i in all_instances if i["state"] == "stopped"]

            self.running_count = len(running)
            self.stopped_count = len(stopped)

            if self.pricing_service and self.pricing_service.pricing_available:
                provider_info = get_provider(DEFAULT_PROVIDER)
                calculate_monthly_cost = provider_info["calculate_monthly_cost"]

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
            self.app.call_from_thread(self._update_display)

        except (ProviderError, KeyError, ValueError, AttributeError) as e:
            logger.warning("Failed to refresh instance stats: %s", e)

    def _update_display(self) -> None:
        """Update the widget display on the main thread."""
        self.update(self.render_stats())

    async def refresh_stats(self) -> None:
        """Query EC2 API for all instances across regions and calculate costs."""
        self.run_worker(self._refresh_stats_sync, thread=True)

    def render_stats(self) -> str:
        """Format stats for display.

        Returns
        -------
        str
            Formatted string "Instances - Running: X  Stopped: Y  $Z/day"
            or "Instances - Running: X  Stopped: Y  N/A"
        """
        cost_str = f"${self.daily_cost:.2f}/day" if self.daily_cost else "N/A"
        return (
            f"Instances - Running: {self.running_count}  Stopped: {self.stopped_count}  {cost_str}"
        )
