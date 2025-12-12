"""AMI resolution and querying for EC2 instances."""

import logging
import re
from typing import Any

from campers.providers.aws.errors import handle_aws_errors

logger = logging.getLogger(__name__)


class AMIResolver:
    """Resolve and query for AMI IDs."""

    def __init__(self, ec2_client: Any, region: str) -> None:
        """Initialize AMIResolver.

        Parameters
        ----------
        ec2_client : Any
            Boto3 EC2 client
        region : str
            AWS region name
        """
        self.ec2_client = ec2_client
        self.region = region

    def _is_localstack_endpoint(self) -> bool:
        """Check if the EC2 client is configured for LocalStack.

        Returns
        -------
        bool
            True if the endpoint URL contains 'localstack' or 'localhost:4566'
        """
        try:
            endpoint = self.ec2_client._endpoint
            if hasattr(endpoint, "host"):
                host = str(endpoint.host).lower()
                return "localstack" in host or "localhost:4566" in host
        except (AttributeError, TypeError):
            logger.debug("Unable to access EC2 client endpoint attribute")

        try:
            meta = self.ec2_client.meta
            if hasattr(meta, "endpoint_url"):
                url = str(meta.endpoint_url).lower()
                return "localstack" in url or "localhost:4566" in url
        except (AttributeError, TypeError):
            logger.debug("Unable to access EC2 client meta.endpoint_url attribute")

        return False

    def resolve_ami(self, config: dict[str, Any]) -> str:
        """Resolve AMI ID from configuration.

        Supports three modes of AMI selection with priority order:
        1. Direct AMI ID specification (ami.image_id)
        2. AMI query with filters (ami.query)
        3. Default Amazon Ubuntu 24 x86_64 if no ami section

        Parameters
        ----------
        config : dict[str, Any]
            Configuration dictionary containing optional ami section

        Returns
        -------
        str
            AMI ID to use for instance launch

        Raises
        ------
        ValueError
            If both image_id and query are specified, if image_id format is
            invalid, if query.name is missing, if architecture is invalid,
            or if query matches no AMIs
        """
        ami_config = config.get("ami", {})

        if "image_id" in ami_config and "query" in ami_config:
            raise ValueError(
                "Cannot specify both 'ami.image_id' and 'ami.query'. "
                "Use image_id for a specific AMI or query to search for the latest."
            )

        if "image_id" in ami_config:
            ami_id = ami_config["image_id"]
            if not re.match(r"^ami-[0-9a-f]{8,17}$", ami_id):
                raise ValueError(f"Invalid AMI ID format: '{ami_id}'")
            return ami_id

        if "query" in ami_config:
            query = ami_config["query"]

            if "name" not in query:
                raise ValueError("ami.query.name is required")

            return self.find_ami_by_query(
                name_pattern=query["name"],
                owner=query.get("owner"),
                architecture=query.get("architecture"),
            )

        is_localstack = self._is_localstack_endpoint()
        owner = None if is_localstack else "amazon"
        return self.find_ami_by_query(
            name_pattern="*Ubuntu 24*",
            owner=owner,
            architecture="x86_64",
        )

    def find_ami_by_query(
        self,
        name_pattern: str,
        owner: str | None = None,
        architecture: str | None = None,
    ) -> str:
        """Query AWS for AMI matching pattern and return newest by CreationDate.

        Parameters
        ----------
        name_pattern : str
            AMI name pattern (supports * and ? wildcards)
        owner : str | None
            AWS account ID or alias (e.g., "099720109477", "amazon")
        architecture : str | None
            CPU architecture: "x86_64" or "arm64"

        Returns
        -------
        str
            Image ID of the newest matching AMI

        Raises
        ------
        ValueError
            If architecture is invalid or no AMIs match the filters
        """
        if architecture and architecture not in ("x86_64", "arm64"):
            raise ValueError(f"Invalid architecture: '{architecture}'. Must be 'x86_64' or 'arm64'")

        is_localstack = self._is_localstack_endpoint()

        filters = [
            {"Name": "name", "Values": [name_pattern]},
        ]

        if not is_localstack:
            filters.append({"Name": "state", "Values": ["available"]})

        if architecture and not is_localstack:
            filters.append({"Name": "architecture", "Values": [architecture]})

        kwargs: dict[str, Any] = {"Filters": filters}
        if owner:
            kwargs["Owners"] = [owner]

        with handle_aws_errors():
            response = self.ec2_client.describe_images(**kwargs)

        if not response["Images"]:
            owner_msg = f"owner={owner}, " if owner else ""
            arch_msg = f"architecture={architecture}, " if architecture else ""
            raise ValueError(f"No AMI found for {owner_msg}{arch_msg}name={name_pattern}")

        images = sorted(
            response["Images"],
            key=lambda x: x["CreationDate"],
            reverse=True,
        )

        return images[0]["ImageId"]
