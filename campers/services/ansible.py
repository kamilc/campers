"""Manage Ansible playbook execution in push mode."""

import logging
import shutil
import subprocess
import tempfile
import yaml
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class AnsibleManager:
    """Manage Ansible playbook execution in push mode."""

    def __init__(self):
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
        ssh_username: str = "ubuntu",
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
                    f"Playbook '{name}' not found in config. "
                    f"Available playbooks: {available}"
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
        inventory_content = (
            "[all]\n"
            f"ec2instance "
            f"ansible_host={host} "
            f"ansible_user={user} "
            f"ansible_ssh_private_key_file={key_file} "
            f"ansible_port={port} "
            "ansible_ssh_common_args='-o StrictHostKeyChecking=no'\n"
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

        for line in process.stdout:
            logger.info(line.rstrip())

        try:
            process.wait(timeout=3600)
        except subprocess.TimeoutExpired:
            process.kill()
            raise RuntimeError("Ansible playbook execution timed out after 1 hour")

        if process.returncode != 0:
            raise RuntimeError(
                f"Ansible playbook failed with exit code {process.returncode}"
            )

    def _cleanup_temp_files(self):
        for temp_file in self._temp_files:
            try:
                if temp_file.exists():
                    temp_file.unlink()
                    logger.debug("Cleaned up: %s", temp_file)
            except OSError as err:
                logger.warning("Failed to cleanup %s: %s", temp_file, err)

        self._temp_files.clear()
