"""Tests for AWS pricing service and parsers."""

import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import ClientError

from botocore.config import Config

from campers.providers.aws.pricing import (
    PricingCache,
    PricingService,
    calculate_monthly_cost,
    format_cost,
)
from campers.providers.aws.pricing_parsers import parse_ebs_pricing, parse_ec2_pricing


class TestPricingParsers:
    """Tests for AWS Pricing API response parsers."""

    def test_parse_ec2_pricing_success(self) -> None:
        """Test parsing valid EC2 pricing response."""
        price_data = {
            "terms": {
                "OnDemand": {
                    "OFFER123": {"priceDimensions": {"DIM456": {"pricePerUnit": {"USD": "0.0416"}}}}
                }
            }
        }
        price_json = json.dumps(price_data)
        result = parse_ec2_pricing(price_json)
        assert result == 0.0416

    def test_parse_ec2_pricing_missing_terms(self) -> None:
        """Test parsing EC2 response without terms."""
        price_data = {}
        price_json = json.dumps(price_data)
        result = parse_ec2_pricing(price_json)
        assert result is None

    def test_parse_ec2_pricing_missing_ondemand(self) -> None:
        """Test parsing EC2 response without OnDemand section."""
        price_data = {"terms": {}}
        price_json = json.dumps(price_data)
        result = parse_ec2_pricing(price_json)
        assert result is None

    def test_parse_ec2_pricing_invalid_json(self) -> None:
        """Test parsing invalid JSON."""
        result = parse_ec2_pricing("not valid json")
        assert result is None

    def test_parse_ec2_pricing_missing_price(self) -> None:
        """Test parsing EC2 response without USD price."""
        price_data = {
            "terms": {
                "OnDemand": {"OFFER123": {"priceDimensions": {"DIM456": {"pricePerUnit": {}}}}}
            }
        }
        price_json = json.dumps(price_data)
        result = parse_ec2_pricing(price_json)
        assert result is None

    def test_parse_ebs_pricing_success(self) -> None:
        """Test parsing valid EBS pricing response."""
        price_data = {
            "terms": {
                "OnDemand": {
                    "OFFER789": {"priceDimensions": {"DIM101": {"pricePerUnit": {"USD": "0.08"}}}}
                }
            }
        }
        price_json = json.dumps(price_data)
        result = parse_ebs_pricing(price_json)
        assert result == 0.08

    def test_parse_ebs_pricing_invalid_json(self) -> None:
        """Test parsing invalid JSON for EBS."""
        result = parse_ebs_pricing("not valid json")
        assert result is None


class TestPricingCache:
    """Tests for PricingCache."""

    def test_get_returns_none_for_missing_key(self) -> None:
        """Test cache returns None for nonexistent key."""
        cache = PricingCache()
        result = cache.get("missing")
        assert result is None

    def test_set_and_get_value(self) -> None:
        """Test storing and retrieving cached value."""
        cache = PricingCache()
        cache.set("test_key", 42.5)
        result = cache.get("test_key")
        assert result == 42.5

    def test_expired_value_returns_none(self) -> None:
        """Test cache returns None for expired entries."""
        cache = PricingCache(ttl_hours=1)
        cache.set("test_key", 100)

        cache._cache["test_key"] = (
            100,
            datetime.now() - timedelta(hours=2),
        )

        result = cache.get("test_key")
        assert result is None
        assert "test_key" not in cache._cache

    def test_non_expired_value_returns_data(self) -> None:
        """Test cache returns data for non-expired entries."""
        cache = PricingCache(ttl_hours=24)
        cache.set("test_key", "test_value")
        result = cache.get("test_key")
        assert result == "test_value"


class TestPricingService:
    """Tests for PricingService."""

    @patch("boto3.client")
    def test_initialization_success(self, mock_boto_client: Mock) -> None:
        """Test successful pricing service initialization."""
        mock_pricing = Mock()
        mock_boto_client.return_value = mock_pricing

        service = PricingService()

        assert service.pricing_available is True
        assert service.pricing_client is mock_pricing
        mock_boto_client.assert_called_once()
        call_args = mock_boto_client.call_args
        assert call_args[0][0] == "pricing"
        assert call_args[1]["region_name"] == "us-east-1"
        assert isinstance(call_args[1]["config"], Config)

    @patch("boto3.client")
    def test_initialization_failure(self, mock_boto_client: Mock) -> None:
        """Test pricing service handles initialization failure gracefully."""
        mock_boto_client.side_effect = ClientError(
            {"Error": {"Code": "ServiceUnavailable", "Message": "Service unavailable"}},
            "GetPricingData",
        )

        service = PricingService()

        assert service.pricing_available is False
        assert service.pricing_client is None

    @patch("boto3.client")
    def test_get_ec2_hourly_rate_when_unavailable(self, mock_boto_client: Mock) -> None:
        """Test EC2 pricing returns None when API unavailable."""
        mock_boto_client.side_effect = ClientError(
            {"Error": {"Code": "ServiceUnavailable", "Message": "Service unavailable"}},
            "GetPricingData",
        )

        service = PricingService()
        rate = service.get_ec2_hourly_rate("t3.medium", "us-east-1")

        assert rate is None

    @patch("boto3.client")
    def test_get_ec2_hourly_rate_success(self, mock_boto_client: Mock) -> None:
        """Test successful EC2 hourly rate retrieval."""
        mock_pricing = Mock()
        price_data = {
            "terms": {
                "OnDemand": {
                    "OFFER123": {"priceDimensions": {"DIM456": {"pricePerUnit": {"USD": "0.0416"}}}}
                }
            }
        }
        mock_pricing.get_products.return_value = {"PriceList": [json.dumps(price_data)]}
        mock_boto_client.return_value = mock_pricing

        service = PricingService(use_cache=False)
        rate = service.get_ec2_hourly_rate("t3.medium", "us-east-1")

        assert rate == 0.0416
        mock_pricing.get_products.assert_called_once()

        call_args = mock_pricing.get_products.call_args
        assert call_args[1]["ServiceCode"] == "AmazonEC2"
        filters = {f["Field"]: f["Value"] for f in call_args[1]["Filters"]}
        assert filters["instanceType"] == "t3.medium"
        assert filters["location"] == "US East (N. Virginia)"
        assert filters["operatingSystem"] == "Linux"

    @patch("boto3.client")
    def test_get_ec2_hourly_rate_unsupported_region(self, mock_boto_client: Mock) -> None:
        """Test EC2 pricing returns None for unsupported region."""
        mock_pricing = Mock()
        mock_boto_client.return_value = mock_pricing

        service = PricingService()
        rate = service.get_ec2_hourly_rate("t3.medium", "ap-unknown-1")

        assert rate is None
        mock_pricing.get_products.assert_not_called()

    @patch("boto3.client")
    def test_get_ec2_hourly_rate_uses_cache(self, mock_boto_client: Mock) -> None:
        """Test EC2 pricing uses cache for repeated requests."""
        mock_pricing = Mock()
        price_data = {
            "terms": {
                "OnDemand": {
                    "OFFER123": {"priceDimensions": {"DIM456": {"pricePerUnit": {"USD": "0.0416"}}}}
                }
            }
        }
        mock_pricing.get_products.return_value = {"PriceList": [json.dumps(price_data)]}
        mock_boto_client.return_value = mock_pricing

        service = PricingService(use_cache=True)

        rate1 = service.get_ec2_hourly_rate("t3.medium", "us-east-1")
        rate2 = service.get_ec2_hourly_rate("t3.medium", "us-east-1")

        assert rate1 == 0.0416
        assert rate2 == 0.0416
        mock_pricing.get_products.assert_called_once()

    @patch("boto3.client")
    def test_get_ec2_hourly_rate_empty_response(self, mock_boto_client: Mock) -> None:
        """Test EC2 pricing returns None when API returns empty results."""
        mock_pricing = Mock()
        mock_pricing.get_products.return_value = {"PriceList": []}
        mock_boto_client.return_value = mock_pricing

        service = PricingService()
        rate = service.get_ec2_hourly_rate("t3.medium", "us-east-1")

        assert rate is None

    @patch("boto3.client")
    def test_get_ebs_storage_rate_success(self, mock_boto_client: Mock) -> None:
        """Test successful EBS storage rate retrieval."""
        mock_pricing = Mock()
        price_data = {
            "terms": {
                "OnDemand": {
                    "OFFER789": {"priceDimensions": {"DIM101": {"pricePerUnit": {"USD": "0.08"}}}}
                }
            }
        }
        mock_pricing.get_products.return_value = {"PriceList": [json.dumps(price_data)]}
        mock_boto_client.return_value = mock_pricing

        service = PricingService(use_cache=False)
        rate = service.get_ebs_storage_rate("us-east-1")

        assert rate == 0.08
        mock_pricing.get_products.assert_called_once()

        call_args = mock_pricing.get_products.call_args
        assert call_args[1]["ServiceCode"] == "AmazonEC2"
        filters = {f["Field"]: f["Value"] for f in call_args[1]["Filters"]}
        assert filters["productFamily"] == "Storage"
        assert filters["volumeApiName"] == "gp3"

    @patch("boto3.client")
    def test_get_ebs_storage_rate_when_unavailable(self, mock_boto_client: Mock) -> None:
        """Test EBS pricing returns None when API unavailable."""
        mock_boto_client.side_effect = ClientError(
            {"Error": {"Code": "ServiceUnavailable", "Message": "Service unavailable"}},
            "GetPricingData",
        )

        service = PricingService()
        rate = service.get_ebs_storage_rate("us-east-1")

        assert rate is None

    @patch("boto3.client")
    def test_get_ebs_storage_rate_uses_cache(self, mock_boto_client: Mock) -> None:
        """Test EBS pricing uses cache for repeated requests."""
        mock_pricing = Mock()
        price_data = {
            "terms": {
                "OnDemand": {
                    "OFFER789": {"priceDimensions": {"DIM101": {"pricePerUnit": {"USD": "0.08"}}}}
                }
            }
        }
        mock_pricing.get_products.return_value = {"PriceList": [json.dumps(price_data)]}
        mock_boto_client.return_value = mock_pricing

        service = PricingService(use_cache=True)

        rate1 = service.get_ebs_storage_rate("us-east-1")
        rate2 = service.get_ebs_storage_rate("us-east-1")

        assert rate1 == 0.08
        assert rate2 == 0.08
        mock_pricing.get_products.assert_called_once()


class TestCalculateMonthlyCost:
    """Tests for calculate_monthly_cost helper function."""

    @patch("campers.providers.aws.pricing.PricingService")
    def test_running_instance_cost(self, mock_service_class: Mock) -> None:
        """Test monthly cost calculation for running instance."""
        mock_service = Mock()
        mock_service.get_ec2_hourly_rate.return_value = 0.0416
        mock_service_class.return_value = mock_service

        cost = calculate_monthly_cost(
            instance_type="t3.medium",
            region="us-east-1",
            state="running",
            volume_size_gb=50,
        )

        assert cost == pytest.approx(0.0416 * 24 * 30)

    @patch("campers.providers.aws.pricing.PricingService")
    def test_stopped_instance_cost(self, mock_service_class: Mock) -> None:
        """Test monthly cost calculation for stopped instance."""
        mock_service = Mock()
        mock_service.get_ebs_storage_rate.return_value = 0.08
        mock_service_class.return_value = mock_service

        cost = calculate_monthly_cost(
            instance_type="t3.medium",
            region="us-east-1",
            state="stopped",
            volume_size_gb=50,
        )

        assert cost == pytest.approx(50 * 0.08)

    @patch("campers.providers.aws.pricing.PricingService")
    def test_returns_none_when_ec2_pricing_unavailable(self, mock_service_class: Mock) -> None:
        """Test returns None when EC2 pricing unavailable."""
        mock_service = Mock()
        mock_service.get_ec2_hourly_rate.return_value = None
        mock_service_class.return_value = mock_service

        cost = calculate_monthly_cost(
            instance_type="t3.medium",
            region="us-east-1",
            state="running",
            volume_size_gb=50,
        )

        assert cost is None

    @patch("campers.providers.aws.pricing.PricingService")
    def test_returns_none_when_ebs_pricing_unavailable(self, mock_service_class: Mock) -> None:
        """Test returns None when EBS pricing unavailable."""
        mock_service = Mock()
        mock_service.get_ebs_storage_rate.return_value = None
        mock_service_class.return_value = mock_service

        cost = calculate_monthly_cost(
            instance_type="t3.medium",
            region="us-east-1",
            state="stopped",
            volume_size_gb=50,
        )

        assert cost is None

    @patch("campers.providers.aws.pricing.PricingService")
    def test_returns_none_for_unknown_state(self, mock_service_class: Mock) -> None:
        """Test returns None for unknown instance state."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service

        cost = calculate_monthly_cost(
            instance_type="t3.medium",
            region="us-east-1",
            state="pending",
            volume_size_gb=50,
        )

        assert cost is None

    def test_uses_provided_pricing_service(self) -> None:
        """Test function uses provided pricing service instance."""
        mock_service = Mock()
        mock_service.get_ec2_hourly_rate.return_value = 0.0416

        cost = calculate_monthly_cost(
            instance_type="t3.medium",
            region="us-east-1",
            state="running",
            volume_size_gb=50,
            pricing_service=mock_service,
        )

        assert cost == pytest.approx(0.0416 * 24 * 30)
        mock_service.get_ec2_hourly_rate.assert_called_once()


class TestFormatCost:
    """Tests for format_cost helper function."""

    def test_format_cost_with_value(self) -> None:
        """Test formatting valid cost value."""
        result = format_cost(29.95)
        assert result == "$29.95/month"

    def test_format_cost_with_none(self) -> None:
        """Test formatting None cost."""
        result = format_cost(None)
        assert result == "Pricing unavailable"

    def test_format_cost_with_large_value(self) -> None:
        """Test formatting large cost with thousands separator."""
        result = format_cost(1234.56)
        assert result == "$1,234.56/month"

    def test_format_cost_with_zero(self) -> None:
        """Test formatting zero cost."""
        result = format_cost(0.0)
        assert result == "$0.00/month"
