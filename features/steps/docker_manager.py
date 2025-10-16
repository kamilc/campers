"""Docker container manager for SSH-enabled EC2 instance simulation."""

import logging
import os
import socket
import subprocess
import time
from pathlib import Path

import docker

logger = logging.getLogger(__name__)

SSH_CONTAINER_BOOT_BASE_TIMEOUT = int(
    os.environ.get("MOONDOCK_SSH_CONTAINER_BOOT_TIMEOUT", "20")
)


def get_ssh_container_boot_timeout() -> int:
    """Calculate SSH container boot timeout including delay and initialization.

    Returns
    -------
    int
        Total timeout in seconds
    """
    base = SSH_CONTAINER_BOOT_BASE_TIMEOUT
    delay = int(os.environ.get("MOONDOCK_SSH_DELAY_SECONDS", "0"))
    buffer_for_init = 5
    total = base + delay + buffer_for_init
    logger.debug(
        f"SSH boot timeout: {total}s (base={base}s, delay={delay}s, buffer={buffer_for_init}s)"
    )
    return total


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

    def is_ssh_server_ready(self, port: int, max_attempts: int = 5) -> bool:
        """Check if SSH server is accepting connections on the container port.

        Parameters
        ----------
        port : int
            SSH port to check
        max_attempts : int
            Number of connection attempts (default: 5)

        Returns
        -------
        bool
            True if SSH server is responding, False otherwise
        """

        for attempt in range(max_attempts):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(("localhost", port))
                sock.close()

                if result == 0:
                    logger.debug(
                        f"SSH server ready on port {port} (attempt {attempt + 1})"
                    )
                    return True
            except Exception as e:
                logger.debug(f"SSH health check failed (attempt {attempt + 1}): {e}")

        return False

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
        pub_key_file = Path(str(key_file) + ".pub")

        if key_file.exists() or pub_key_file.exists():
            logger.warning(
                f"Key files already exist for {instance_id}, cleaning up before regeneration"
            )
            if key_file.exists():
                key_file.unlink()
                logger.debug(f"Removed old private key: {key_file}")
            if pub_key_file.exists():
                pub_key_file.unlink()
                logger.debug(f"Removed old public key: {pub_key_file}")

        logger.info(f"Generating SSH key pair for {instance_id} at {key_file}")

        try:
            cmd = [
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
            ]
            logger.debug(f"Running SSH key generation command: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
            )
            logger.debug(f"SSH key generation stdout: {result.stdout}")
            logger.debug(f"SSH key generation stderr: {result.stderr}")
        except subprocess.CalledProcessError as e:
            logger.error(f"SSH key generation failed with exit code {e.returncode}")
            logger.error(f"stdout: {e.stdout}")
            logger.error(f"stderr: {e.stderr}")
            logger.error(f"command: {e.cmd}")
            raise RuntimeError(
                f"Failed to generate SSH key for {instance_id}: stdout={e.stdout}, stderr={e.stderr}"
            ) from e
        except FileNotFoundError as e:
            logger.error("ssh-keygen command not found in PATH")
            raise RuntimeError(
                "ssh-keygen command not found. Please ensure OpenSSH is installed."
            ) from e

        try:
            key_file.chmod(0o600)
            logger.debug(f"Set permissions 0600 on key file {key_file}")
        except OSError as e:
            logger.error(f"Failed to set permissions on key file {key_file}: {e}")
            raise RuntimeError(f"Failed to set key file permissions: {e}") from e

        logger.info(
            f"SSH key generation completed: {key_file} (exists: {key_file.exists()})"
        )
        return key_file

    def create_instance_container(self, instance_id: str) -> tuple[int | None, Path]:
        """Spin up SSH container for EC2 instance.

        Parameters
        ----------
        instance_id : str
            EC2 instance ID from LocalStack

        Returns
        -------
        tuple[int | None, Path]
            (port, key_file_path) where port is SSH port (or None if blocked) and key_file_path is the private key
        """
        logger.debug(f"Starting create_instance_container for {instance_id}")
        logger.debug(
            f"Checking SSH delay env var: MOONDOCK_SSH_DELAY_SECONDS={os.environ.get('MOONDOCK_SSH_DELAY_SECONDS', 'not set')}"
        )
        logger.debug(
            f"Checking SSH block env var: MOONDOCK_SSH_BLOCK_CONNECTIONS={os.environ.get('MOONDOCK_SSH_BLOCK_CONNECTIONS', 'not set')}"
        )

        ssh_delay = int(os.environ.get("MOONDOCK_SSH_DELAY_SECONDS", "0"))
        block_ssh = os.environ.get("MOONDOCK_SSH_BLOCK_CONNECTIONS") == "1"

        if block_ssh:
            ports = {}
            logger.info(
                f"Creating SSH container for {instance_id} WITHOUT port mapping (blocked)"
            )
        else:
            port = self.next_port
            self.next_port += 1
            ports = {"2222/tcp": port}
            logger.info(f"Creating SSH container for {instance_id} on port {port}")

        key_file = self.generate_ssh_key(instance_id)
        pub_key_file = Path(str(key_file) + ".pub")

        pub_key_content = pub_key_file.read_text().strip()

        environment = {
            "PUBLIC_KEY": pub_key_content,
            "USER_NAME": "ubuntu",
            "SUDO_ACCESS": "true",
        }

        if ssh_delay > 0:
            delay_script = f"""#!/bin/bash
echo "Delaying SSH startup by {ssh_delay} seconds..."
sleep {ssh_delay}
exec /init
"""
            logger.info(f"SSH container will delay startup by {ssh_delay} seconds")
            try:
                logger.debug(
                    f"About to call containers.run() for {instance_id} with delay"
                )
                container = self.client.containers.run(
                    "linuxserver/openssh-server",
                    name=f"ssh-{instance_id}",
                    detach=True,
                    remove=True,
                    environment=environment,
                    ports=ports,
                    entrypoint="/bin/bash",
                    command=["-c", delay_script],
                )
                logger.debug(
                    f"Successfully created container {container.id} for {instance_id}"
                )
            except Exception as e:
                logger.error(
                    f"Docker API call failed for {instance_id}: {e}", exc_info=True
                )
                raise
        else:
            try:
                logger.debug(f"About to call containers.run() for {instance_id}")
                container = self.client.containers.run(
                    "linuxserver/openssh-server",
                    name=f"ssh-{instance_id}",
                    detach=True,
                    remove=True,
                    environment=environment,
                    ports=ports,
                )
                logger.debug(
                    f"Successfully created container {container.id} for {instance_id}"
                )
            except Exception as e:
                logger.error(
                    f"Docker API call failed for {instance_id}: {e}", exc_info=True
                )
                raise

        if not block_ssh:
            self.instance_map[instance_id] = (container, port, key_file)
        else:
            self.instance_map[instance_id] = (container, None, key_file)

        timeout = get_ssh_container_boot_timeout()
        ssh_delay = int(os.environ.get("MOONDOCK_SSH_DELAY_SECONDS", "0"))
        logger.info(
            f"Polling container status for up to {timeout}s (delay={ssh_delay}s)..."
        )
        start_time = time.time()

        container_ready = False

        while time.time() - start_time < timeout:
            container.reload()

            if container.status == "running":
                container_ready = True
                elapsed_container = time.time() - start_time
                logger.debug(
                    f"Container {container.short_id} running after {elapsed_container:.1f}s"
                )
                break
            time.sleep(0.5)

        if not container_ready:
            container.reload()
            raise TimeoutError(
                f"Container {container.short_id} not ready after {timeout}s (status: {container.status})"
            )

        if not block_ssh:
            ssh_health_start = time.time()
            logger.info(f"Waiting for SSH server to be ready on localhost:{port}...")

            while time.time() - start_time < timeout:
                if self.is_ssh_server_ready(port):
                    ssh_ready_elapsed = time.time() - ssh_health_start
                    total_elapsed = time.time() - start_time
                    logger.info(
                        f"SSH server ready on port {port} after {ssh_ready_elapsed:.1f}s (total: {total_elapsed:.1f}s)"
                    )
                    break
                time.sleep(0.5)
            else:
                raise TimeoutError(
                    f"SSH server not responding on port {port} after {timeout}s"
                )

        if not block_ssh:
            logger.info(
                f"SSH container {container.name} ready at localhost:{port} with key {key_file}"
            )
            return port, key_file
        else:
            logger.info(
                f"SSH container {container.name} ready (blocked - no port mapping) with key {key_file}"
            )
            return None, key_file

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
