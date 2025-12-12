"""Manage Ansible playbook execution in push mode."""

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import yaml

from campers.constants import ANSIBLE_PLAYBOOK_TIMEOUT_SECONDS, DEFAULT_SSH_USERNAME
from campers.services.validation import (
    validate_ansible_host,
    validate_ansible_user,
    validate_port,
)

logger = logging.getLogger(__name__)


class AnsibleManager:
    """Manage Ansible playbook execution in push mode."""

    def __init__(self) -> None:
        """Initialize AnsibleManager.

        Notes
        -----
        Initializes an empty list of temporary files that may be created
        during playbook execution. These files should be cleaned up
        after playbook completion.
        """
        self._temp_files: list[Path] = []

    def check_ansible_installed(self) -> None:
        """Check if ansible-playbook is available locally.

        Raises
        ------
        RuntimeError
            If ansible-playbook is not found with installation instructions
        """
        if not shutil.which("ansible-playbook"):
            raise RuntimeError(
                "Ansible not installed locally.\n\n"
                "Campers uses 'push mode' where Ansible runs on your machine.\n"
                "Install Ansible with:\n\n"
                "  pip install ansible    # Using pip\n"
                "  brew install ansible   # Using Homebrew (macOS)\n"
                "  apt install ansible    # Using apt (Ubuntu)\n\n"
                "For more info: https://docs.ansible.com/ansible/latest/installation_guide/"
            )

    def execute_playbooks(
        self,
        playbook_names: list[str],
        playbooks_config: dict[str, Any],
        instance_ip: str,
        ssh_key_file: str,
        ssh_username: str = DEFAULT_SSH_USERNAME,
        ssh_port: int = 22,
    ) -> None:
        """Execute one or more Ansible playbooks.

        Parameters
        ----------
        playbook_names : list[str]
            Names of playbooks to execute (keys from playbooks_config)
        playbooks_config : dict[str, Any]
            The 'playbooks' section from campers.yaml
        instance_ip : str
            EC2 instance public IP address
        ssh_key_file : str
            Path to SSH private key
        ssh_username : str
            SSH username (default: ubuntu, can be ec2-user for Amazon Linux)
        ssh_port : int
            SSH port (default: 22)

        Raises
        ------
        ValueError
            If playbook name not found in config
        RuntimeError
            If ansible-playbook execution fails
        """
        self.check_ansible_installed()

        for name in playbook_names:
            if name not in playbooks_config:
                available = list(playbooks_config.keys())
                raise ValueError(
                    f"Playbook '{name}' not found in config. Available playbooks: {available}"
                )

        inventory_file = self._generate_inventory(
            host=instance_ip,
            user=ssh_username,
            key_file=ssh_key_file,
            port=ssh_port,
        )

        try:
            for playbook_name in playbook_names:
                playbook_yaml = playbooks_config[playbook_name]
                playbook_file = self._write_playbook_to_file(
                    name=playbook_name,
                    playbook_yaml=playbook_yaml,
                )

                self._run_ansible_playbook(
                    inventory=inventory_file,
                    playbook=playbook_file,
                )
        finally:
            self._cleanup_temp_files()

    def _generate_inventory(
        self,
        host: str,
        user: str,
        key_file: str,
        port: int,
    ) -> Path:
        """Generate Ansible inventory file.

        Parameters
        ----------
        host : str
            Target host IP address
        user : str
            SSH username
        key_file : str
            Path to SSH private key
        port : int
            SSH port number

        Returns
        -------
        Path
            Path to generated temporary inventory file
        """
        validate_ansible_host(host)
        validate_ansible_user(user)
        validate_port(port)

        inventory_content = (
            "[all]\n"
            f"ec2instance "
            f"ansible_host={host} "
            f"ansible_user={user} "
            f"ansible_ssh_private_key_file={key_file} "
            f"ansible_port={port} "
            "ansible_ssh_common_args='-o StrictHostKeyChecking=accept-new'\n"
        )

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".ini",
            prefix="campers-inventory-",
            delete=False,
        ) as f:
            f.write(inventory_content)
            inventory_file = Path(f.name)

        self._temp_files.append(inventory_file)

        logger.debug("Generated inventory: %s", inventory_file)
        return inventory_file

    def _write_playbook_to_file(
        self,
        name: str,
        playbook_yaml: list[dict],
    ) -> Path:
        """Write Ansible playbook YAML to temporary file.

        Parameters
        ----------
        name : str
            Playbook name for file naming
        playbook_yaml : list[dict]
            Playbook content as YAML structure

        Returns
        -------
        Path
            Path to generated temporary playbook file
        """
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yml",
            prefix=f"campers-playbook-{name}-",
            delete=False,
        ) as f:
            yaml.dump(playbook_yaml, f, default_flow_style=False)
            playbook_file = Path(f.name)

        self._temp_files.append(playbook_file)
        logger.debug("Wrote playbook '%s' to %s", name, playbook_file)
        return playbook_file

    def _run_ansible_playbook(
        self,
        inventory: Path,
        playbook: Path,
    ) -> None:
        """Execute Ansible playbook against target host.

        Parameters
        ----------
        inventory : Path
            Path to Ansible inventory file
        playbook : Path
            Path to Ansible playbook file
        """
        cmd = [
            "ansible-playbook",
            "-i",
            str(inventory),
            str(playbook),
            "-v",
        ]

        logger.info("Executing: %s", " ".join(cmd))

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        output_lines: list[str] = []
        try:
            for line in process.stdout:
                stripped_line = line.rstrip()
                logger.info(stripped_line)
                output_lines.append(stripped_line)
            process.wait(timeout=ANSIBLE_PLAYBOOK_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as e:
            if process.stdout and hasattr(process.stdout, "close"):
                process.stdout.close()
            process.kill()
            process.wait()
            raise RuntimeError("Ansible playbook execution timed out after 1 hour") from e
        finally:
            if process.stdout and hasattr(process.stdout, "close"):
                process.stdout.close()

        if process.returncode != 0:
            last_lines = output_lines[-50:] if len(output_lines) > 50 else output_lines
            error_output = "\n".join(last_lines)
            raise RuntimeError(
                f"Ansible playbook failed with exit code {process.returncode}\n\n"
                f"Ansible output:\n{error_output}"
            )

    def _cleanup_temp_files(self) -> None:
        """Clean up temporary inventory and playbook files.

        Removes all temporary files created during ansible execution.
        """
        for temp_file in self._temp_files:
            try:
                if temp_file.exists():
                    temp_file.unlink()
                    logger.debug("Cleaned up: %s", temp_file)
            except OSError as err:
                logger.warning("Failed to cleanup %s: %s", temp_file, err)

        self._temp_files.clear()
