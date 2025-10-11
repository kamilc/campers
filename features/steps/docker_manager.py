"""Docker container manager for SSH-enabled EC2 instance simulation."""

import logging
import os
import subprocess
import time
from pathlib import Path

import docker

logger = logging.getLogger(__name__)

SSH_CONTAINER_BOOT_TIMEOUT = int(
    os.environ.get("MOONDOCK_SSH_CONTAINER_BOOT_TIMEOUT", "10")
)


class EC2ContainerManager:
    """Manages Docker containers that simulate SSH-enabled EC2 instances.

    Attributes
    ----------
    client : docker.DockerClient
        Docker client instance
    instance_map : dict[str, tuple]
        Maps instance IDs to (container, port) tuples
    next_port : int
        Next available port for SSH container (starts at 2222)
    """

    def __init__(self) -> None:
        """Initialize EC2ContainerManager with Docker client and empty instance map."""
        self.client = docker.from_env()
        self.instance_map: dict[str, tuple] = {}
        self.next_port = 2222
        moondock_dir = os.environ.get("MOONDOCK_DIR", str(Path.home() / ".moondock"))
        self.keys_dir = Path(moondock_dir) / "keys"
        self.keys_dir.mkdir(parents=True, exist_ok=True)

    def generate_ssh_key(self, instance_id: str) -> Path:
        """Generate SSH key pair for container.

        Parameters
        ----------
        instance_id : str
            EC2 instance ID

        Returns
        -------
        Path
            Path to private key file

        Raises
        ------
        RuntimeError
            If SSH key generation fails
        """
        key_file = self.keys_dir / f"{instance_id}-test.pem"

        try:
            result = subprocess.run(
                [
                    "ssh-keygen",
                    "-t",
                    "rsa",
                    "-b",
                    "2048",
                    "-f",
                    str(key_file),
                    "-N",
                    "",
                    "-C",
                    f"test-key-{instance_id}",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            logger.debug(f"SSH key generation output: {result.stdout}")
        except subprocess.CalledProcessError as e:
            logger.error(
                f"SSH key generation failed with exit code {e.returncode}: {e.stderr}"
            )
            raise RuntimeError(
                f"Failed to generate SSH key for {instance_id}: {e.stderr}"
            ) from e
        except FileNotFoundError as e:
            logger.error("ssh-keygen command not found in PATH")
            raise RuntimeError(
                "ssh-keygen command not found. Please ensure OpenSSH is installed."
            ) from e

        try:
            key_file.chmod(0o600)
        except OSError as e:
            logger.error(f"Failed to set permissions on key file {key_file}: {e}")
            raise RuntimeError(f"Failed to set key file permissions: {e}") from e

        return key_file

    def create_instance_container(self, instance_id: str) -> tuple[int, Path]:
        """Spin up SSH container for EC2 instance.

        Parameters
        ----------
        instance_id : str
            EC2 instance ID from LocalStack

        Returns
        -------
        tuple[int, Path]
            (port, key_file_path) where port is SSH port and key_file_path is the private key
        """
        port = self.next_port
        self.next_port += 1

        logger.info(f"Creating SSH container for instance {instance_id} on port {port}")

        key_file = self.generate_ssh_key(instance_id)
        pub_key_file = Path(str(key_file) + ".pub")

        pub_key_content = pub_key_file.read_text().strip()

        container = self.client.containers.run(
            "linuxserver/openssh-server",
            name=f"ssh-{instance_id}",
            detach=True,
            remove=True,
            environment={
                "PUBLIC_KEY": pub_key_content,
                "USER_NAME": "ubuntu",
                "SUDO_ACCESS": "true",
            },
            ports={"2222/tcp": port},
        )

        self.instance_map[instance_id] = (container, port, key_file)

        logger.info(
            f"Waiting {SSH_CONTAINER_BOOT_TIMEOUT}s for SSH container to boot..."
        )
        time.sleep(SSH_CONTAINER_BOOT_TIMEOUT)

        container.reload()
        if container.status != "running":
            raise RuntimeError(
                f"SSH container {container.name} failed to reach running state (status: {container.status})"
            )

        logger.info(
            f"SSH container {container.name} ready at localhost:{port} with key {key_file}"
        )

        return port, key_file

    def get_instance_ssh_config(
        self, instance_id: str
    ) -> tuple[str | None, int | None, Path | None]:
        """Get SSH host, port, and key file for instance.

        Parameters
        ----------
        instance_id : str
            EC2 instance ID

        Returns
        -------
        tuple[str | None, int | None, Path | None]
            (host, port, key_file) tuple or (None, None, None) if not found
        """
        if instance_id in self.instance_map:
            _, port, key_file = self.instance_map[instance_id]
            return "localhost", port, key_file
        return None, None, None

    def terminate_instance_container(self, instance_id: str) -> None:
        """Remove SSH container for terminated instance.

        Parameters
        ----------
        instance_id : str
            EC2 instance ID
        """
        if instance_id not in self.instance_map:
            logger.debug(f"Instance {instance_id} not in map, skipping termination")
            return

        container, port, key_file = self.instance_map[instance_id]
        logger.info(f"Terminating SSH container for {instance_id} (port {port})")

        try:
            container.stop()
        except Exception as e:
            logger.debug(f"Error stopping container: {e}")

        self.cleanup_key_files(key_file)

        del self.instance_map[instance_id]

    def cleanup_key_files(self, key_file: Path) -> None:
        """Clean up SSH key files for an instance.

        Parameters
        ----------
        key_file : Path
            Path to the private key file
        """
        if key_file and key_file.exists():
            try:
                key_file.unlink()
                pub_key = Path(str(key_file) + ".pub")

                if pub_key.exists():
                    pub_key.unlink()
            except Exception as e:
                logger.debug(f"Error cleaning up SSH keys: {e}")

    def cleanup_all(self) -> None:
        """Clean up all instance containers and orphaned SSH containers."""
        for instance_id in list(self.instance_map.keys()):
            self.terminate_instance_container(instance_id)

        try:
            orphaned_containers = self.client.containers.list(
                all=True, filters={"name": "ssh-"}
            )

            for container in orphaned_containers:
                try:
                    logger.info(f"Removing orphaned container: {container.name}")
                    container.remove(force=True)
                except Exception as e:
                    logger.debug(
                        f"Error removing orphaned container {container.name}: {e}"
                    )
        except Exception as e:
            logger.debug(f"Error listing orphaned containers: {e}")

        if self.keys_dir.exists():
            for key_file in self.keys_dir.glob("*.pem"):
                try:
                    key_file.unlink()
                    logger.debug(f"Removed orphaned key file: {key_file}")
                except Exception as e:
                    logger.debug(f"Error removing key file {key_file}: {e}")

            for pub_key_file in self.keys_dir.glob("*.pub"):
                try:
                    pub_key_file.unlink()
                    logger.debug(f"Removed orphaned public key file: {pub_key_file}")
                except Exception as e:
                    logger.debug(f"Error removing public key file {pub_key_file}: {e}")
