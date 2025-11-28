"""AWS Pricing service for EC2 and EBS cost calculations.

This module provides pricing information retrieval from AWS Price List API
with in-memory caching to minimize API calls.
"""

import logging
import threading
from datetime import datetime, timedelta
from typing import Any, Optional

import boto3

from campers.providers.aws.pricing_parsers import parse_ebs_pricing, parse_ec2_pricing

logger = logging.getLogger(__name__)


class PricingCache:
    """In-memory cache for pricing data with time-based expiration.

    Parameters
    ----------
    ttl_hours : int, default=24
        Time-to-live for cached entries in hours

    Notes
    -----
    Cache is not persisted to disk. All entries are lost when process terminates.
    Cache access is protected by a thread-safe lock to prevent race conditions
    during concurrent get/set operations.
    """

    def __init__(self, ttl_hours: int = 24) -> None:
        self._cache: dict[str, tuple[Any, datetime]] = {}
        self._ttl = timedelta(hours=ttl_hours)
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        """Retrieve value from cache if not expired.

        Parameters
        ----------
        key : str
            Cache key

        Returns
        -------
        Any or None
            Cached value if key exists and not expired, None otherwise
        """
        with self._lock:
            if key in self._cache:
                value, timestamp = self._cache[key]

                if datetime.now() - timestamp < self._ttl:
                    return value

                del self._cache[key]

            return None

    def set(self, key: str, value: Any) -> None:
        """Store value in cache with current timestamp.

        Parameters
        ----------
        key : str
            Cache key
        value : Any
            Value to cache
        """
        with self._lock:
            self._cache[key] = (value, datetime.now())


class PricingService:
    """AWS Pricing API client with caching for EC2 and EBS rates.

    Parameters
    ----------
    use_cache : bool, default=True
        Enable in-memory caching with 24-hour TTL

    Attributes
    ----------
    pricing_available : bool
        True if AWS Pricing API is accessible, False otherwise

    Notes
    -----
    AWS Pricing API is only available in us-east-1 region regardless of
    the region where resources are being priced. The service gracefully
    handles environments where Pricing API is unavailable (e.g., LocalStack).
    """

    REGION_TO_LOCATION = {
        "us-east-1": "US East (N. Virginia)",
        "us-east-2": "US East (Ohio)",
        "us-west-1": "US West (N. California)",
        "us-west-2": "US West (Oregon)",
        "eu-west-1": "EU (Ireland)",
        "eu-west-2": "EU (London)",
        "eu-west-3": "EU (Paris)",
        "eu-central-1": "EU (Frankfurt)",
        "eu-north-1": "EU (Stockholm)",
        "eu-south-1": "EU (Milan)",
        "ap-northeast-1": "Asia Pacific (Tokyo)",
        "ap-northeast-2": "Asia Pacific (Seoul)",
        "ap-northeast-3": "Asia Pacific (Osaka)",
        "ap-southeast-1": "Asia Pacific (Singapore)",
        "ap-southeast-2": "Asia Pacific (Sydney)",
        "ap-south-1": "Asia Pacific (Mumbai)",
        "sa-east-1": "South America (Sao Paulo)",
        "ca-central-1": "Canada (Central)",
        "me-south-1": "Middle East (Bahrain)",
        "af-south-1": "Africa (Cape Town)",
    }

    def __init__(self, use_cache: bool = True) -> None:
        self.cache = PricingCache() if use_cache else None
        self.pricing_available = False

        try:
            self.pricing_client = boto3.client("pricing", region_name="us-east-1")
            self.pricing_available = True
            logger.debug("AWS Pricing API initialized successfully")
        except Exception as e:
            logger.debug(f"Failed to initialize AWS Pricing API: {e}")
            self.pricing_client = None

    def get_ec2_hourly_rate(
        self,
        instance_type: str,
        region: str,
        operating_system: str = "Linux",
    ) -> Optional[float]:
        """Fetch EC2 on-demand hourly rate from AWS Pricing API.

        Parameters
        ----------
        instance_type : str
            EC2 instance type (e.g., "t3.medium", "g5.2xlarge")
        region : str
            AWS region code (e.g., "us-east-1")
        operating_system : str, default="Linux"
            Operating system for pricing lookup

        Returns
        -------
        float or None
            Hourly rate in USD, or None if pricing unavailable

        Notes
        -----
        Results are cached with 24-hour TTL to minimize API calls.
        Returns None for unsupported regions or when API is unavailable.
        """
        if not self.pricing_available:
            return None

        cache_key = f"ec2_{instance_type}_{region}_{operating_system}"

        if self.cache:
            cached = self.cache.get(cache_key)

            if cached is not None:
                return cached

        try:
            rate = self._fetch_ec2_rate_from_api(
                instance_type, region, operating_system
            )

            if self.cache and rate is not None:
                self.cache.set(cache_key, rate)

            return rate
        except Exception as e:
            logger.error(f"Failed to fetch EC2 pricing: {e}")
            return None

    def _fetch_ec2_rate_from_api(
        self,
        instance_type: str,
        region: str,
        operating_system: str,
    ) -> Optional[float]:
        """Query AWS Pricing API for EC2 instance pricing.

        Parameters
        ----------
        instance_type : str
            EC2 instance type
        region : str
            AWS region code
        operating_system : str
            Operating system filter

        Returns
        -------
        float or None
            Hourly rate in USD, or None if not found
        """
        location = self.REGION_TO_LOCATION.get(region)

        if location is None:
            return None

        if self.pricing_client is None:
            return None

        response = self.pricing_client.get_products(
            ServiceCode="AmazonEC2",
            Filters=[
                {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
                {"Type": "TERM_MATCH", "Field": "location", "Value": location},
                {
                    "Type": "TERM_MATCH",
                    "Field": "operatingSystem",
                    "Value": operating_system,
                },
                {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": "NA"},
                {"Type": "TERM_MATCH", "Field": "tenancy", "Value": "Shared"},
                {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": "Used"},
            ],
            MaxResults=1,
        )

        if not response.get("PriceList"):
            return None

        return parse_ec2_pricing(response["PriceList"][0])

    def get_ebs_storage_rate(
        self,
        region: str,
        volume_type: str = "gp3",
    ) -> Optional[float]:
        """Fetch EBS storage rate per GB-month from AWS Pricing API.

        Parameters
        ----------
        region : str
            AWS region code (e.g., "us-east-1")
        volume_type : str, default="gp3"
            EBS volume type for pricing lookup

        Returns
        -------
        float or None
            Storage rate in USD per GB-month, or None if pricing unavailable

        Notes
        -----
        Results are cached with 24-hour TTL to minimize API calls.
        Returns None for unsupported regions or when API is unavailable.
        """
        if not self.pricing_available:
            return None

        cache_key = f"ebs_{region}_{volume_type}"

        if self.cache:
            cached = self.cache.get(cache_key)

            if cached is not None:
                return cached

        try:
            rate = self._fetch_ebs_rate_from_api(region, volume_type)

            if self.cache and rate is not None:
                self.cache.set(cache_key, rate)

            return rate
        except Exception as e:
            logger.error(f"Failed to fetch EBS pricing: {e}")
            return None

    def _fetch_ebs_rate_from_api(
        self,
        region: str,
        volume_type: str,
    ) -> Optional[float]:
        """Query AWS Pricing API for EBS storage pricing.

        Parameters
        ----------
        region : str
            AWS region code
        volume_type : str
            EBS volume type

        Returns
        -------
        float or None
            Storage rate in USD per GB-month, or None if not found
        """
        location = self.REGION_TO_LOCATION.get(region)

        if location is None:
            return None

        if self.pricing_client is None:
            return None

        response = self.pricing_client.get_products(
            ServiceCode="AmazonEC2",
            Filters=[
                {"Type": "TERM_MATCH", "Field": "productFamily", "Value": "Storage"},
                {"Type": "TERM_MATCH", "Field": "location", "Value": location},
                {"Type": "TERM_MATCH", "Field": "volumeApiName", "Value": volume_type},
            ],
            MaxResults=1,
        )

        if not response.get("PriceList"):
            return None

        return parse_ebs_pricing(response["PriceList"][0])

    def get_instance_price(self, instance_type: str, region: str) -> Optional[float]:
        """Get hourly price for an instance type in a region.

        This method implements the PricingProvider protocol interface.

        Parameters
        ----------
        instance_type : str
            Instance type identifier (e.g., 't3.micro')
        region : str
            Region identifier

        Returns
        -------
        float or None
            Hourly price in USD, or None if not available
        """
        return self.get_ec2_hourly_rate(instance_type, region)

    def get_storage_price(self, region: str) -> float:
        """Get monthly price per GB for storage in a region.

        This method implements the PricingProvider protocol interface.

        Parameters
        ----------
        region : str
            Region identifier

        Returns
        -------
        float
            Monthly price per GB in USD
        """
        rate = self.get_ebs_storage_rate(region)
        return rate if rate is not None else 0.0


def calculate_monthly_cost(
    instance_type: str,
    region: str,
    state: str,
    volume_size_gb: int,
    pricing_service: Optional[PricingService] = None,
) -> Optional[float]:
    """Calculate estimated monthly cost for an EC2 instance.

    Parameters
    ----------
    instance_type : str
        EC2 instance type (e.g., "t3.medium")
    region : str
        AWS region code (e.g., "us-east-1")
    state : str
        Instance state ("running" or "stopped")
    volume_size_gb : int
        Root volume size in GB
    pricing_service : PricingService or None, default=None
        Optional pricing service instance for reuse across multiple calls

    Returns
    -------
    float or None
        Estimated monthly cost in USD, or None if pricing unavailable

    Notes
    -----
    For running instances, calculates: hourly_rate × 24 × 30
    For stopped instances, calculates: volume_size_gb × ebs_storage_rate
    Returns None when pricing data cannot be retrieved.
    """
    if pricing_service is None:
        pricing_service = PricingService()

    if state == "running":
        hourly_rate = pricing_service.get_ec2_hourly_rate(instance_type, region)

        if hourly_rate is None:
            return None

        return hourly_rate * 24 * 30
    elif state == "stopped":
        storage_rate = pricing_service.get_ebs_storage_rate(region)

        if storage_rate is None:
            return None

        return volume_size_gb * storage_rate

    return None


def format_cost(cost: Optional[float]) -> str:
    """Format cost value for display.

    Parameters
    ----------
    cost : float or None
        Cost in USD

    Returns
    -------
    str
        Formatted cost string (e.g., "$29.95/month") or "Pricing unavailable"
    """
    if cost is None:
        return "Pricing unavailable"

    return f"${cost:,.2f}/month"
