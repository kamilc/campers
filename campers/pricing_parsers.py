"""AWS Pricing API response parsers.

This module provides parsers to extract pricing information from complex
AWS Price List API JSON responses for EC2 and EBS services.
"""

import json
from typing import Optional


def parse_ec2_pricing(price_item_json: str) -> Optional[float]:
    """Extract hourly on-demand rate from AWS EC2 pricing response.

    Parameters
    ----------
    price_item_json : str
        JSON string from AWS Price List API response containing EC2 pricing data

    Returns
    -------
    float or None
        Hourly USD rate for the EC2 instance, or None if parsing fails

    Notes
    -----
    AWS Pricing API returns complex nested JSON with this structure:
    terms → OnDemand → {offer_code} → priceDimensions → {dimension} → pricePerUnit → USD
    """
    try:
        data = json.loads(price_item_json)
        terms = data.get("terms", {})
        on_demand = terms.get("OnDemand", {})

        if not on_demand:
            return None

        offer_code = next(iter(on_demand.keys()))
        offer_terms = on_demand[offer_code]
        price_dimensions = offer_terms.get("priceDimensions", {})

        if not price_dimensions:
            return None

        dimension_code = next(iter(price_dimensions.keys()))
        dimension = price_dimensions[dimension_code]
        price_per_unit = dimension.get("pricePerUnit", {})
        usd_price = price_per_unit.get("USD")

        if usd_price is None:
            return None

        return float(usd_price)
    except (json.JSONDecodeError, KeyError, ValueError, StopIteration):
        return None


def parse_ebs_pricing(price_item_json: str) -> Optional[float]:
    """Extract GB-month storage rate from AWS EBS pricing response.

    Parameters
    ----------
    price_item_json : str
        JSON string from AWS Price List API response containing EBS pricing data

    Returns
    -------
    float or None
        Storage rate in USD per GB-month, or None if parsing fails

    Notes
    -----
    Uses same nested structure as EC2 pricing but for EBS storage rates.
    """
    try:
        data = json.loads(price_item_json)
        terms = data.get("terms", {})
        on_demand = terms.get("OnDemand", {})

        if not on_demand:
            return None

        offer_code = next(iter(on_demand.keys()))
        offer_terms = on_demand[offer_code]
        price_dimensions = offer_terms.get("priceDimensions", {})

        if not price_dimensions:
            return None

        dimension_code = next(iter(price_dimensions.keys()))
        dimension = price_dimensions[dimension_code]
        price_per_unit = dimension.get("pricePerUnit", {})
        usd_price = price_per_unit.get("USD")

        if usd_price is None:
            return None

        return float(usd_price)
    except (json.JSONDecodeError, KeyError, ValueError, StopIteration):
        return None
