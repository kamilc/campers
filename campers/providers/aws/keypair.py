"""SSH key pair management for EC2 instances."""

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from campers.providers.aws.errors import handle_aws_errors
from campers.providers.exceptions import ProviderAPIError

logger = logging.getLogger(__name__)


@dataclass
class KeyPairInfo:
    """SSH key pair information.

    Attributes
    ----------
    name : str
        Key pair name
    file_path : Path
        Path to private key file
    """

    name: str
    file_path: Path


class KeyPairManager:
    """Manage EC2 key pairs."""

    def __init__(self, ec2_client: Any, region: str) -> None:
        """Initialize KeyPairManager.

        Parameters
        ----------
        ec2_client : Any
            Boto3 EC2 client
        region : str
            AWS region name
        """
        self.ec2_client = ec2_client
        self.region = region

    def create_key_pair(self, unique_id: str) -> KeyPairInfo:
        """Create SSH key pair and save to disk.

        Parameters
        ----------
        unique_id : str
            Unique identifier to use in key name (timestamp)

        Returns
        -------
        KeyPairInfo
            Key pair information with name and file path
        """
        key_name = f"campers-{unique_id}"

        try:
            with handle_aws_errors():
                self.ec2_client.delete_key_pair(KeyName=key_name)
        except ProviderAPIError as e:
            logger.debug("Failed to delete key pair %s: %s", key_name, e)

        with handle_aws_errors():
            response = self.ec2_client.create_key_pair(KeyName=key_name)

        campers_dir = os.environ.get("CAMPERS_DIR", str(Path.home() / ".campers"))
        keys_dir = Path(campers_dir) / "keys"
        keys_dir.mkdir(parents=True, exist_ok=True)

        key_file = keys_dir / f"{unique_id}.pem"
        key_file.write_text(response["KeyMaterial"])
        key_file.chmod(0o600)

        return KeyPairInfo(name=key_name, file_path=key_file)
