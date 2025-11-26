"""Fake EC2Manager for testing with dependency injection."""

import os
import time
from pathlib import Path
from typing import Any


class FakeEC2Manager:
    """Fake EC2Manager that simulates EC2 operations for testing.

    This fake implementation matches the EC2Manager interface and is designed
    to be injected via dependency injection for fast test execution without
    accessing real AWS or LocalStack services.

    Parameters
    ----------
    region : str
        AWS region (used but does not need to be valid for testing)
    all_managers : dict[str, FakeEC2Manager] | None
        Optional dict of all managers for multi-region list operations
    """

    def __init__(self, region: str, all_managers: dict[str, Any] | None = None) -> None:
        """Initialize FakeEC2Manager.

        Parameters
        ----------
        region : str
            AWS region name
        all_managers : dict[str, FakeEC2Manager] | None
            Optional dict of all managers keyed by region for multi-region queries
        """
        self.region = region
        self.instances: dict[str, dict[str, Any]] = {}
        self.key_pairs: dict[str, str] = {}
        self.security_groups: dict[str, dict[str, Any]] = {}
        self.all_managers = all_managers

    def create_key_pair(self, unique_id: str) -> tuple[str, Path]:
        """Create a fake SSH key pair.

        Parameters
        ----------
        unique_id : str
            Unique identifier for the key pair

        Returns
        -------
        tuple[str, Path]
            Tuple of (key_name, key_file_path)
        """
        key_name = f"campers-{unique_id}"
        campers_dir = Path("/tmp/test-campers")
        keys_dir = campers_dir / "keys"
        keys_dir.mkdir(parents=True, exist_ok=True)

        key_file = keys_dir / f"{unique_id}.pem"
        key_file.write_text(
            "-----BEGIN RSA PRIVATE KEY-----\nFAKEKEY\n-----END RSA PRIVATE KEY-----"
        )
        key_file.chmod(0o600)

        self.key_pairs[key_name] = str(key_file)
        return key_name, key_file

    def create_security_group(self, unique_id: str) -> str:
        """Create a fake security group.

        Parameters
        ----------
        unique_id : str
            Unique identifier for the security group

        Returns
        -------
        str
            Fake security group ID
        """
        sg_id = f"sg-fake{unique_id}"
        self.security_groups[sg_id] = {
            "GroupId": sg_id,
            "GroupName": f"campers-{unique_id}",
            "IpPermissions": [
                {
                    "IpProtocol": "tcp",
                    "FromPort": 22,
                    "ToPort": 22,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                }
            ],
        }
        return sg_id

    def launch_instance(
        self, config: dict[str, Any], instance_name: str | None = None
    ) -> dict[str, Any]:
        """Launch a fake EC2 instance.

        Parameters
        ----------
        config : dict[str, Any]
            Configuration dict with instance_type, disk_size, etc.
        instance_name : str | None
            Optional instance name for Name tag. If None, uses timestamp-based name.

        Returns
        -------
        dict[str, Any]
            Fake instance details matching EC2Manager interface
        """
        unique_id = str(int(time.time()))
        instance_id = f"i-fake{unique_id}"

        key_name, key_file = self.create_key_pair(unique_id)
        sg_id = self.create_security_group(unique_id)

        public_ip = (
            None if os.environ.get("CAMPERS_NO_PUBLIC_IP") == "1" else "203.0.113.1"
        )

        instance = {
            "instance_id": instance_id,
            "public_ip": public_ip,
            "state": "running",
            "key_file": str(key_file),
            "security_group_id": sg_id,
            "unique_id": unique_id,
            "camp_config": instance_name,
        }

        self.instances[instance_id] = instance
        return instance

    def list_instances(self, region_filter: str | None = None) -> list[dict[str, Any]]:
        """List all fake instances across regions.

        Parameters
        ----------
        region_filter : str | None
            Optional region filter. If None, lists instances from all regions.

        Returns
        -------
        list[dict[str, Any]]
            List of fake instance details
        """
        instances_list = []

        if region_filter is None and self.all_managers:
            for manager in self.all_managers.values():
                for instance in manager.instances.values():
                    instances_list.append(
                        {
                            "instance_id": instance["instance_id"],
                            "name": instance.get("name", f"campers-{instance['unique_id']}"),
                            "state": instance["state"],
                            "region": instance.get("region", manager.region),
                            "instance_type": instance.get("instance_type", "t3.medium"),
                            "launch_time": instance.get(
                                "launch_time", "2024-01-01T00:00:00+00:00"
                            ),
                            "camp_config": instance.get("camp_config", "test"),
                            "volume_size": instance.get("volume_size", 30),
                        }
                    )
        else:
            for instance in self.instances.values():
                instances_list.append(
                    {
                        "instance_id": instance["instance_id"],
                        "name": instance.get("name", f"campers-{instance['unique_id']}"),
                        "state": instance["state"],
                        "region": instance.get("region", self.region),
                        "instance_type": instance.get("instance_type", "t3.medium"),
                        "launch_time": instance.get(
                            "launch_time", "2024-01-01T00:00:00+00:00"
                        ),
                        "camp_config": instance.get("camp_config", "test"),
                        "volume_size": instance.get("volume_size", 30),
                    }
                )
        return instances_list

    def find_instances_by_name_or_id(
        self, name_or_id: str, region_filter: str | None = None
    ) -> list[dict[str, Any]]:
        """Find instances by ID or name.

        Parameters
        ----------
        name_or_id : str
            Instance ID or machine config name
        region_filter : str | None
            Optional region filter

        Returns
        -------
        list[dict[str, Any]]
            List of matching instances
        """
        all_instances = self.list_instances(region_filter)
        return [
            inst
            for inst in all_instances
            if inst["instance_id"] == name_or_id or inst["camp_config"] == name_or_id
        ]

    def stop_instance(self, instance_id: str) -> dict[str, Any]:
        """Stop a fake EC2 instance.

        Parameters
        ----------
        instance_id : str
            Instance ID to stop

        Returns
        -------
        dict[str, Any]
            Instance details with state set to stopped and public_ip cleared
        """
        if instance_id not in self.instances:
            raise RuntimeError(f"Instance {instance_id} not found")

        instance = self.instances[instance_id]
        instance["state"] = "stopped"
        instance["public_ip"] = None

        return {
            "instance_id": instance_id,
            "public_ip": None,
            "private_ip": "10.0.0.1",
            "state": "stopped",
            "instance_type": instance.get("instance_type", "t3.medium"),
        }

    def start_instance(self, instance_id: str) -> dict[str, Any]:
        """Start a fake EC2 instance.

        Parameters
        ----------
        instance_id : str
            Instance ID to start

        Returns
        -------
        dict[str, Any]
            Instance details with state set to running and new public_ip assigned
        """
        if instance_id not in self.instances:
            raise RuntimeError(f"Instance {instance_id} not found")

        instance = self.instances[instance_id]
        instance["state"] = "running"
        instance["public_ip"] = "203.0.113.2"

        return {
            "instance_id": instance_id,
            "public_ip": "203.0.113.2",
            "private_ip": "10.0.0.1",
            "state": "running",
            "instance_type": instance.get("instance_type", "t3.medium"),
        }

    def get_volume_size(self, instance_id: str) -> int:
        """Get root volume size for a fake instance.

        Parameters
        ----------
        instance_id : str
            Instance ID to get volume size for

        Returns
        -------
        int
            Fake volume size in GB
        """
        if instance_id not in self.instances:
            raise RuntimeError(f"Instance {instance_id} not found")

        instance = self.instances[instance_id]

        if "volume_size" in instance:
            return instance["volume_size"]

        return 100

    def terminate_instance(self, instance_id: str) -> None:
        """Terminate a fake instance.

        Parameters
        ----------
        instance_id : str
            Instance ID to terminate
        """
        if instance_id in self.instances:
            instance = self.instances[instance_id]
            unique_id = instance["unique_id"]

            key_file = Path(instance["key_file"])
            if key_file.exists():
                key_file.unlink()

            self.key_pairs.pop(f"campers-{unique_id}", None)
            self.security_groups.pop(instance["security_group_id"], None)
            del self.instances[instance_id]
