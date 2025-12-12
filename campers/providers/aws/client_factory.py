"""AWS client and resource factory for boto3 clients."""

from __future__ import annotations

from typing import Any

import boto3
from botocore.config import Config


class AWSClientFactory:
    """Factory for creating AWS boto3 clients and resources."""

    def get_client(self, service_name: str, **kwargs: Any) -> Any:
        """Get a boto3 client for the specified service.

        Parameters
        ----------
        service_name : str
            Name of the AWS service (e.g., 'ec2', 'pricing')
        **kwargs : Any
            Additional arguments to pass to boto3.client()

        Returns
        -------
        Any
            A boto3 service client
        """
        if "config" not in kwargs:
            kwargs["config"] = Config(
                connect_timeout=5, read_timeout=30, retries={"max_attempts": 3, "mode": "adaptive"}
            )
        return boto3.client(service_name, **kwargs)

    def get_resource(self, service_name: str, **kwargs: Any) -> Any:
        """Get a boto3 resource for the specified service.

        Parameters
        ----------
        service_name : str
            Name of the AWS service (e.g., 'ec2')
        **kwargs : Any
            Additional arguments to pass to boto3.resource()

        Returns
        -------
        Any
            A boto3 service resource
        """
        if "config" not in kwargs:
            kwargs["config"] = Config(
                connect_timeout=5, read_timeout=30, retries={"max_attempts": 3, "mode": "adaptive"}
            )
        return boto3.resource(service_name, **kwargs)


def create_aws_client_factory() -> AWSClientFactory:
    """Create an AWS client factory instance.

    Returns
    -------
    AWSClientFactory
        A new instance of AWSClientFactory
    """
    return AWSClientFactory()
