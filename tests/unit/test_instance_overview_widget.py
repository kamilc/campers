"""Unit tests for InstanceOverviewWidget."""

from datetime import datetime
from unittest.mock import Mock, patch

import pytest


@pytest.fixture
def mock_campers():
    """Create mock Campers instance."""
    campers = Mock()
    campers._ec2_manager_factory = Mock()
    return campers


@pytest.fixture
def mock_ec2_manager():
    """Create mock EC2Manager."""
    manager = Mock()
    manager.list_instances = Mock(return_value=[])
    return manager


@pytest.fixture
def mock_pricing_service():
    """Create mock PricingService."""
    service = Mock()
    service.pricing_available = False
    return service


@pytest.fixture
def initialized_widget(mock_campers, mock_ec2_manager, mock_pricing_service):
    """Create widget with mocked services pre-initialized."""
    from campers.tui.instance_overview_widget import InstanceOverviewWidget

    mock_campers._ec2_manager_factory.return_value = mock_ec2_manager

    with patch.object(
        InstanceOverviewWidget, "app", new_callable=lambda: Mock()
    ):
        widget = InstanceOverviewWidget(mock_campers)
        widget.ec2_manager = mock_ec2_manager
        widget.pricing_service = mock_pricing_service
        widget._initialized = True

        yield widget


def test_widget_initialization(mock_campers):
    """Test widget initializes with correct default attributes."""
    from campers.tui.instance_overview_widget import InstanceOverviewWidget

    widget = InstanceOverviewWidget(mock_campers)

    assert widget.running_count == 0
    assert widget.stopped_count == 0
    assert widget.daily_cost is None
    assert widget.last_update is None
    assert widget.ec2_manager is None
    assert widget.pricing_service is None
    assert widget._initialized is False


def test_refresh_stats_counts_instances_correctly(initialized_widget, mock_ec2_manager):
    """Test _refresh_stats_sync correctly counts running and stopped instances."""
    mock_ec2_manager.list_instances.return_value = [
        {
            "instance_id": "i-1",
            "state": "running",
            "instance_type": "t3.medium",
            "region": "us-east-1",
            "volume_size": 100,
        },
        {
            "instance_id": "i-2",
            "state": "running",
            "instance_type": "t3.large",
            "region": "us-west-2",
            "volume_size": 100,
        },
        {
            "instance_id": "i-3",
            "state": "stopped",
            "instance_type": "t3.medium",
            "region": "us-east-1",
            "volume_size": 50,
        },
        {
            "instance_id": "i-4",
            "state": "stopped",
            "instance_type": "m5.xlarge",
            "region": "us-west-2",
            "volume_size": 200,
        },
        {
            "instance_id": "i-5",
            "state": "stopped",
            "instance_type": "g5.2xlarge",
            "region": "eu-west-1",
            "volume_size": 150,
        },
    ]

    initialized_widget._refresh_stats_sync()

    assert initialized_widget.running_count == 2
    assert initialized_widget.stopped_count == 3
    assert isinstance(initialized_widget.last_update, datetime)


def test_refresh_stats_handles_empty_list(initialized_widget, mock_ec2_manager):
    """Test _refresh_stats_sync handles empty instance list."""
    mock_ec2_manager.list_instances.return_value = []

    initialized_widget._refresh_stats_sync()

    assert initialized_widget.running_count == 0
    assert initialized_widget.stopped_count == 0


def test_refresh_stats_calculates_daily_cost_when_pricing_available(
    initialized_widget, mock_ec2_manager
):
    """Test _refresh_stats_sync calculates daily cost when pricing is available."""
    mock_ec2_manager.list_instances.return_value = [
        {
            "instance_id": "i-1",
            "state": "running",
            "instance_type": "t3.medium",
            "region": "us-east-1",
            "volume_size": 100,
        },
        {
            "instance_id": "i-2",
            "state": "running",
            "instance_type": "t3.medium",
            "region": "us-east-1",
            "volume_size": 100,
        },
    ]

    initialized_widget.pricing_service.pricing_available = True

    with patch("campers.providers.aws.pricing.calculate_monthly_cost") as mock_calc:
        mock_calc.side_effect = [899.0, 899.0]

        initialized_widget._refresh_stats_sync()

        assert initialized_widget.daily_cost == pytest.approx(1798.0 / 30, rel=0.01)
        assert mock_calc.call_count == 2


def test_refresh_stats_sets_none_cost_when_pricing_unavailable(
    initialized_widget, mock_ec2_manager
):
    """Test _refresh_stats_sync sets None for cost when pricing unavailable."""
    mock_ec2_manager.list_instances.return_value = [
        {
            "instance_id": "i-1",
            "state": "running",
            "instance_type": "t3.medium",
            "region": "us-east-1",
            "volume_size": 100,
        },
    ]

    initialized_widget.pricing_service.pricing_available = False

    initialized_widget._refresh_stats_sync()

    assert initialized_widget.daily_cost is None
    assert initialized_widget.running_count == 1


def test_refresh_stats_handles_ec2_api_errors_gracefully(
    initialized_widget, mock_ec2_manager
):
    """Test _refresh_stats_sync maintains last known state when EC2 API fails."""
    mock_ec2_manager.list_instances.side_effect = Exception("EC2 API error")

    initialized_widget.running_count = 5
    initialized_widget.stopped_count = 3

    initialized_widget._refresh_stats_sync()

    assert initialized_widget.running_count == 5
    assert initialized_widget.stopped_count == 3


def test_render_stats_formats_with_cost(mock_campers):
    """Test render_stats formats display with cost."""
    from campers.tui.instance_overview_widget import InstanceOverviewWidget

    widget = InstanceOverviewWidget(mock_campers)
    widget.running_count = 2
    widget.stopped_count = 3
    widget.daily_cost = 72.72

    result = widget.render_stats()

    assert result == "Instances - Running: 2  Stopped: 3  $72.72/day"


def test_render_stats_formats_without_cost(mock_campers):
    """Test render_stats formats display without cost (N/A)."""
    from campers.tui.instance_overview_widget import InstanceOverviewWidget

    widget = InstanceOverviewWidget(mock_campers)
    widget.running_count = 1
    widget.stopped_count = 0
    widget.daily_cost = None

    result = widget.render_stats()

    assert result == "Instances - Running: 1  Stopped: 0  N/A"


def test_widget_queries_all_regions(initialized_widget, mock_ec2_manager):
    """Test widget queries all regions using region_filter=None."""
    mock_ec2_manager.list_instances.return_value = []

    initialized_widget._refresh_stats_sync()

    mock_ec2_manager.list_instances.assert_called_once_with(region_filter=None)


def test_refresh_stats_shows_na_when_all_prices_none(
    initialized_widget, mock_ec2_manager
):
    """Test widget shows N/A when all running instances return None for pricing."""
    mock_ec2_manager.list_instances.return_value = [
        {
            "instance_id": "i-1",
            "state": "running",
            "instance_type": "t3.medium",
            "region": "us-east-1",
            "volume_size": 100,
        },
    ]

    initialized_widget.pricing_service.pricing_available = True

    with patch("campers.providers.aws.pricing.calculate_monthly_cost") as mock_calc:
        mock_calc.return_value = None

        initialized_widget._refresh_stats_sync()

        assert initialized_widget.daily_cost is None
        assert initialized_widget.render_stats() == "Instances - Running: 1  Stopped: 0  N/A"


def test_refresh_stats_skips_when_not_initialized(mock_campers, mock_ec2_manager):
    """Test _refresh_stats_sync returns early when not initialized."""
    from campers.tui.instance_overview_widget import InstanceOverviewWidget

    widget = InstanceOverviewWidget(mock_campers)
    widget.ec2_manager = mock_ec2_manager
    widget._initialized = False

    widget._refresh_stats_sync()

    mock_ec2_manager.list_instances.assert_not_called()
