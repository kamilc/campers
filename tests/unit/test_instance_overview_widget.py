"""Unit tests for InstanceOverviewWidget."""

import asyncio
from datetime import datetime
from unittest.mock import Mock, patch

import pytest


@pytest.fixture
def mock_campers():
    """Create mock Campers instance."""
    campers = Mock()
    campers.ec2_manager_factory = Mock()
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


def test_widget_initialization(mock_campers, mock_ec2_manager):
    """Test widget initializes with correct attributes."""
    from campers.instance_overview_widget import InstanceOverviewWidget

    mock_campers.ec2_manager_factory.return_value = mock_ec2_manager

    with patch("campers.pricing.PricingService") as MockPricing:
        mock_pricing = Mock()
        MockPricing.return_value = mock_pricing

        widget = InstanceOverviewWidget(mock_campers)

        assert widget.running_count == 0
        assert widget.stopped_count == 0
        assert widget.daily_cost is None
        assert widget.last_update is None
        assert widget.ec2_manager == mock_ec2_manager
        assert widget.pricing_service == mock_pricing


def test_refresh_stats_counts_instances_correctly(
    mock_campers, mock_ec2_manager, mock_pricing_service
):
    """Test refresh_stats correctly counts running and stopped instances."""
    from campers.instance_overview_widget import InstanceOverviewWidget

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

    mock_campers.ec2_manager_factory.return_value = mock_ec2_manager

    with patch("campers.pricing.PricingService") as MockPricing:
        MockPricing.return_value = mock_pricing_service

        widget = InstanceOverviewWidget(mock_campers)
        asyncio.run(widget.refresh_stats())

        assert widget.running_count == 2
        assert widget.stopped_count == 3
        assert isinstance(widget.last_update, datetime)


def test_refresh_stats_handles_empty_list(
    mock_campers, mock_ec2_manager, mock_pricing_service
):
    """Test refresh_stats handles empty instance list."""
    from campers.instance_overview_widget import InstanceOverviewWidget

    mock_ec2_manager.list_instances.return_value = []
    mock_campers.ec2_manager_factory.return_value = mock_ec2_manager

    with patch("campers.pricing.PricingService") as MockPricing:
        MockPricing.return_value = mock_pricing_service

        widget = InstanceOverviewWidget(mock_campers)
        asyncio.run(widget.refresh_stats())

        assert widget.running_count == 0
        assert widget.stopped_count == 0


def test_refresh_stats_calculates_daily_cost_when_pricing_available(
    mock_campers, mock_ec2_manager
):
    """Test refresh_stats calculates daily cost when pricing is available."""
    from campers.instance_overview_widget import InstanceOverviewWidget

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

    mock_campers.ec2_manager_factory.return_value = mock_ec2_manager

    with patch("campers.pricing.PricingService") as MockPricing, patch(
        "campers.pricing.calculate_monthly_cost"
    ) as mock_calc:
        mock_pricing = Mock()
        mock_pricing.pricing_available = True
        MockPricing.return_value = mock_pricing
        mock_calc.side_effect = [899.0, 899.0]

        widget = InstanceOverviewWidget(mock_campers)
        asyncio.run(widget.refresh_stats())

        assert widget.daily_cost == pytest.approx(1798.0 / 30, rel=0.01)
        assert mock_calc.call_count == 2


def test_refresh_stats_sets_none_cost_when_pricing_unavailable(
    mock_campers, mock_ec2_manager, mock_pricing_service
):
    """Test refresh_stats sets None for cost when pricing unavailable."""
    from campers.instance_overview_widget import InstanceOverviewWidget

    mock_ec2_manager.list_instances.return_value = [
        {
            "instance_id": "i-1",
            "state": "running",
            "instance_type": "t3.medium",
            "region": "us-east-1",
            "volume_size": 100,
        },
    ]

    mock_campers.ec2_manager_factory.return_value = mock_ec2_manager
    mock_pricing_service.pricing_available = False

    with patch("campers.pricing.PricingService") as MockPricing:
        MockPricing.return_value = mock_pricing_service

        widget = InstanceOverviewWidget(mock_campers)
        asyncio.run(widget.refresh_stats())

        assert widget.daily_cost is None
        assert widget.running_count == 1


def test_refresh_stats_handles_ec2_api_errors_gracefully(
    mock_campers, mock_ec2_manager, mock_pricing_service
):
    """Test refresh_stats maintains last known state when EC2 API fails."""
    from campers.instance_overview_widget import InstanceOverviewWidget

    mock_ec2_manager.list_instances.side_effect = Exception("EC2 API error")
    mock_campers.ec2_manager_factory.return_value = mock_ec2_manager

    with patch("campers.pricing.PricingService") as MockPricing:
        MockPricing.return_value = mock_pricing_service

        widget = InstanceOverviewWidget(mock_campers)
        widget.running_count = 5
        widget.stopped_count = 3

        asyncio.run(widget.refresh_stats())

        assert widget.running_count == 5
        assert widget.stopped_count == 3


def test_render_stats_formats_with_cost(mock_campers, mock_ec2_manager):
    """Test render_stats formats display with cost."""
    from campers.instance_overview_widget import InstanceOverviewWidget

    mock_campers.ec2_manager_factory.return_value = mock_ec2_manager

    with patch("campers.pricing.PricingService") as MockPricing:
        MockPricing.return_value = Mock()

        widget = InstanceOverviewWidget(mock_campers)
        widget.running_count = 2
        widget.stopped_count = 3
        widget.daily_cost = 72.72

        result = widget.render_stats()

        assert result == "Running: 2  Stopped: 3  $72.72/day"


def test_render_stats_formats_without_cost(mock_campers, mock_ec2_manager):
    """Test render_stats formats display without cost (N/A)."""
    from campers.instance_overview_widget import InstanceOverviewWidget

    mock_campers.ec2_manager_factory.return_value = mock_ec2_manager

    with patch("campers.pricing.PricingService") as MockPricing:
        MockPricing.return_value = Mock()

        widget = InstanceOverviewWidget(mock_campers)
        widget.running_count = 1
        widget.stopped_count = 0
        widget.daily_cost = None

        result = widget.render_stats()

        assert result == "Running: 1  Stopped: 0  N/A"


def test_widget_queries_all_regions(
    mock_campers, mock_ec2_manager, mock_pricing_service
):
    """Test widget queries all regions using region_filter=None."""
    from campers.instance_overview_widget import InstanceOverviewWidget

    mock_ec2_manager.list_instances.return_value = []
    mock_campers.ec2_manager_factory.return_value = mock_ec2_manager

    with patch("campers.pricing.PricingService") as MockPricing:
        MockPricing.return_value = mock_pricing_service

        widget = InstanceOverviewWidget(mock_campers)
        asyncio.run(widget.refresh_stats())

        mock_ec2_manager.list_instances.assert_called_once_with(region_filter=None)


def test_refresh_stats_shows_na_when_all_prices_none(
    mock_campers, mock_ec2_manager
):
    """Test widget shows N/A when all running instances return None for pricing."""
    from campers.instance_overview_widget import InstanceOverviewWidget

    mock_ec2_manager.list_instances.return_value = [
        {
            "instance_id": "i-1",
            "state": "running",
            "instance_type": "t3.medium",
            "region": "us-east-1",
            "volume_size": 100,
        },
    ]

    mock_campers.ec2_manager_factory.return_value = mock_ec2_manager

    with patch("campers.pricing.PricingService") as MockPricing, patch(
        "campers.pricing.calculate_monthly_cost"
    ) as mock_calc:
        mock_pricing = Mock()
        mock_pricing.pricing_available = True
        MockPricing.return_value = mock_pricing
        mock_calc.return_value = None

        widget = InstanceOverviewWidget(mock_campers)
        asyncio.run(widget.refresh_stats())

        assert widget.daily_cost is None
        assert widget.render_stats() == "Running: 1  Stopped: 0  N/A"
