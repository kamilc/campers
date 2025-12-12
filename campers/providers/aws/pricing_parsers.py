"""AWS Pricing API response parsers.

This module provides parsers to extract pricing information from complex
AWS Price List API JSON responses for EC2 and EBS services.
"""

import json


def parse_aws_pricing_response(price_item_json: str) -> float | None:
    """Extract on-demand USD rate from AWS pricing response.

    Handles both EC2 and EBS pricing responses using the same structure:
    terms → OnDemand → {offer_code} → priceDimensions → {dimension} → pricePerUnit → USD

    Parameters
    ----------
    price_item_json : str
        JSON string from AWS Price List API response containing pricing data

    Returns
    -------
    float or None
        USD rate for EC2 (hourly) or EBS (per GB-month), or None if parsing fails
    """
    try:
        data = json.loads(price_item_json)
        terms = data.get("terms", {})
        on_demand = terms.get("OnDemand", {})

        if not on_demand:
            return None

        offer_code = next(iter(on_demand.keys()))
        price_dimensions = on_demand[offer_code].get("priceDimensions", {})

        if not price_dimensions:
            return None

        dimension = price_dimensions[next(iter(price_dimensions.keys()))]
        usd_price = dimension.get("pricePerUnit", {}).get("USD")

        return float(usd_price) if usd_price is not None else None
    except (json.JSONDecodeError, KeyError, ValueError, StopIteration):
        return None


def parse_ec2_pricing(price_item_json: str) -> float | None:
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
    return parse_aws_pricing_response(price_item_json)


def parse_ebs_pricing(price_item_json: str) -> float | None:
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
    return parse_aws_pricing_response(price_item_json)
