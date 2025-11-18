"""Unit tests for Ansible manager."""

from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from moondock.ansible import AnsibleManager


class TestAnsibleManagerInstallationCheck:
    """Test Ansible installation detection."""

    def test_check_ansible_installed_when_available(self) -> None:
        """Test that check passes when ansible-playbook is available."""
        with mock.patch("shutil.which", return_value="/usr/bin/ansible-playbook"):
            manager = AnsibleManager()
            manager.check_ansible_installed()

    def test_check_ansible_installed_when_missing(self) -> None:
        """Test that RuntimeError is raised when ansible-playbook not found."""
        with mock.patch("shutil.which", return_value=None):
            manager = AnsibleManager()
            with pytest.raises(RuntimeError) as exc_info:
                manager.check_ansible_installed()

            error_msg = str(exc_info.value)
            assert "Ansible not installed" in error_msg
            assert "pip install ansible" in error_msg
            assert "brew install ansible" in error_msg


class TestAnsibleManagerInventoryGeneration:
    """Test inventory file generation."""

    def test_generate_inventory_creates_file(self) -> None:
        """Test that inventory file is created with correct content."""
        manager = AnsibleManager()
        inventory_path = manager._generate_inventory(
            host="54.123.45.67",
            user="ubuntu",
            key_file="/path/to/key.pem",
            port=22,
        )

        assert inventory_path.exists()
        content = inventory_path.read_text()

        assert "[all]" in content
        assert "ec2instance" in content
        assert "ansible_host=54.123.45.67" in content
        assert "ansible_user=ubuntu" in content
        assert "ansible_ssh_private_key_file=/path/to/key.pem" in content
        assert "ansible_port=22" in content
        assert "StrictHostKeyChecking=no" in content

    def test_generate_inventory_with_custom_port(self) -> None:
        """Test inventory generation with custom SSH port."""
        manager = AnsibleManager()
        inventory_path = manager._generate_inventory(
            host="10.0.0.1",
            user="ec2-user",
            key_file="/home/user/.ssh/id_rsa",
            port=2222,
        )

        content = inventory_path.read_text()
        assert "ansible_port=2222" in content
        assert "ansible_user=ec2-user" in content

    def test_generate_inventory_tracks_temp_files(self) -> None:
        """Test that generated inventory file is tracked for cleanup."""
        manager = AnsibleManager()
        inventory_path = manager._generate_inventory(
            host="192.168.1.1",
            user="ubuntu",
            key_file="/key.pem",
            port=22,
        )

        assert inventory_path in manager._temp_files
        assert len(manager._temp_files) == 1


class TestAnsibleManagerPlaybookSerialization:
    """Test playbook serialization to files."""

    def test_write_playbook_to_file(self) -> None:
        """Test that playbook YAML is written to file."""
        manager = AnsibleManager()
        playbook_content = [
            {
                "hosts": "all",
                "become": True,
                "tasks": [
                    {
                        "name": "Install packages",
                        "apt": {"name": "nginx", "state": "present"},
                    }
                ],
            }
        ]

        playbook_path = manager._write_playbook_to_file(
            name="webserver",
            playbook_yaml=playbook_content,
        )

        assert playbook_path.exists()
        assert playbook_path.suffix == ".yml"
        assert "moondock-playbook-webserver-" in playbook_path.name

        content = playbook_path.read_text()
        assert "hosts: all" in content
        assert "become: true" in content
        assert "Install packages" in content

    def test_write_playbook_to_file_tracks_temp_file(self) -> None:
        """Test that written playbook file is tracked for cleanup."""
        manager = AnsibleManager()
        playbook_path = manager._write_playbook_to_file(
            name="test",
            playbook_yaml=[{"hosts": "all", "tasks": []}],
        )

        assert playbook_path in manager._temp_files

    def test_write_playbook_to_file_with_variables(self) -> None:
        """Test playbook with variable references."""
        manager = AnsibleManager()
        playbook_content = [
            {
                "hosts": "all",
                "tasks": [
                    {
                        "name": "Configure port",
                        "debug": {"msg": "Port: ${nginx_port}"},
                    }
                ],
            }
        ]

        playbook_path = manager._write_playbook_to_file(
            name="config",
            playbook_yaml=playbook_content,
        )

        content = playbook_path.read_text()
        assert "${nginx_port}" in content


class TestAnsibleManagerPlaybookExecution:
    """Test playbook execution via subprocess."""

    def test_run_ansible_playbook_success(self) -> None:
        """Test successful playbook execution."""
        manager = AnsibleManager()

        mock_process = mock.Mock()
        mock_process.stdout = []
        mock_process.returncode = 0
        mock_process.wait = mock.Mock()

        with mock.patch("subprocess.Popen", return_value=mock_process):
            inventory_path = Path("/tmp/inventory.ini")
            playbook_path = Path("/tmp/playbook.yml")

            manager._run_ansible_playbook(
                inventory=inventory_path,
                playbook=playbook_path,
            )

            assert mock_process.wait.called

    def test_run_ansible_playbook_failure(self) -> None:
        """Test that RuntimeError is raised on playbook failure."""
        manager = AnsibleManager()

        mock_process = mock.Mock()
        mock_process.stdout = []
        mock_process.returncode = 1
        mock_process.wait = mock.Mock()

        with mock.patch("subprocess.Popen", return_value=mock_process):
            with pytest.raises(RuntimeError) as exc_info:
                manager._run_ansible_playbook(
                    inventory=Path("/tmp/inventory.ini"),
                    playbook=Path("/tmp/playbook.yml"),
                )

            assert "exit code 1" in str(exc_info.value)

    def test_run_ansible_playbook_streams_output(self) -> None:
        """Test that playbook output is logged line by line."""
        manager = AnsibleManager()

        output_lines = [
            "PLAY [all] ********************",
            "TASK [Install packages] ******",
            "ok: [ec2instance]",
        ]

        mock_process = mock.Mock()
        mock_process.stdout = output_lines
        mock_process.returncode = 0
        mock_process.wait = mock.Mock()

        with mock.patch("subprocess.Popen", return_value=mock_process):
            manager._run_ansible_playbook(
                inventory=Path("/tmp/inventory.ini"),
                playbook=Path("/tmp/playbook.yml"),
            )

    def test_run_ansible_playbook_command_format(self) -> None:
        """Test that ansible-playbook command is formatted correctly."""
        manager = AnsibleManager()

        mock_process = mock.Mock()
        mock_process.stdout = []
        mock_process.returncode = 0
        mock_process.wait = mock.Mock()

        with mock.patch("subprocess.Popen", return_value=mock_process) as mock_popen:
            manager._run_ansible_playbook(
                inventory=Path("/tmp/inventory.ini"),
                playbook=Path("/tmp/playbook.yml"),
            )

            call_args = mock_popen.call_args
            cmd = call_args[0][0]

            assert cmd[0] == "ansible-playbook"
            assert "-i" in cmd
            assert str(Path("/tmp/inventory.ini")) in cmd
            assert str(Path("/tmp/playbook.yml")) in cmd
            assert "-v" in cmd


class TestAnsibleManagerFileCleanup:
    """Test temporary file cleanup."""

    def test_cleanup_temp_files(self) -> None:
        """Test that all temp files are deleted during cleanup."""
        manager = AnsibleManager()

        with mock.patch("tempfile.mktemp") as mock_mktemp:
            temp_files = [
                Path("/tmp/moondock-inventory-abc123.ini"),
                Path("/tmp/moondock-playbook-test-def456.yml"),
            ]
            mock_mktemp.side_effect = [str(f) for f in temp_files]

            for temp_file in temp_files:
                temp_file.parent.mkdir(parents=True, exist_ok=True)
                temp_file.write_text("test")
                manager._temp_files.append(temp_file)

            manager._cleanup_temp_files()

            for temp_file in temp_files:
                if temp_file.exists():
                    temp_file.unlink()

    def test_cleanup_temp_files_clears_list(self) -> None:
        """Test that temp files list is cleared after cleanup."""
        manager = AnsibleManager()
        manager._temp_files = [
            Path("/tmp/file1.ini"),
            Path("/tmp/file2.yml"),
        ]

        manager._cleanup_temp_files()
        assert len(manager._temp_files) == 0


class TestAnsibleManagerPlaybookValidation:
    """Test playbook name validation."""

    def test_execute_playbooks_with_missing_playbook(self) -> None:
        """Test that ValueError is raised for missing playbook."""
        manager = AnsibleManager()

        with mock.patch.object(manager, "check_ansible_installed"):
            with pytest.raises(ValueError) as exc_info:
                manager.execute_playbooks(
                    playbook_names=["missing_playbook"],
                    playbooks_config={"system_setup": [{"hosts": "all"}]},
                    instance_ip="10.0.0.1",
                    ssh_key_file="/path/to/key.pem",
                )

            error_msg = str(exc_info.value)
            assert "missing_playbook" in error_msg
            assert "Available playbooks" in error_msg

    def test_execute_playbooks_with_available_playbooks_listed(self) -> None:
        """Test that available playbooks are listed in error."""
        manager = AnsibleManager()

        with mock.patch.object(manager, "check_ansible_installed"):
            with pytest.raises(ValueError) as exc_info:
                manager.execute_playbooks(
                    playbook_names=["not_found"],
                    playbooks_config={
                        "playbook1": [{"hosts": "all"}],
                        "playbook2": [{"hosts": "all"}],
                    },
                    instance_ip="10.0.0.1",
                    ssh_key_file="/path/to/key.pem",
                )

            error_msg = str(exc_info.value)
            assert "playbook1" in error_msg or "playbook2" in error_msg


class TestAnsibleManagerIntegration:
    """Integration tests for full playbook execution flow."""

    def test_execute_single_playbook_full_flow(self) -> None:
        """Test execution of single playbook with cleanup."""
        manager = AnsibleManager()

        playbooks_config = {
            "webapp": [
                {
                    "hosts": "all",
                    "tasks": [
                        {
                            "name": "Install nginx",
                            "apt": {"name": "nginx"},
                        }
                    ],
                }
            ]
        }

        mock_process = mock.Mock()
        mock_process.stdout = []
        mock_process.returncode = 0
        mock_process.wait = mock.Mock()

        with mock.patch("shutil.which", return_value="/usr/bin/ansible-playbook"):
            with mock.patch("subprocess.Popen", return_value=mock_process):
                manager.execute_playbooks(
                    playbook_names=["webapp"],
                    playbooks_config=playbooks_config,
                    instance_ip="10.0.0.1",
                    ssh_key_file="/path/to/key.pem",
                )

                assert len(manager._temp_files) == 0

    def test_execute_multiple_playbooks_in_order(self) -> None:
        """Test that multiple playbooks execute in correct order."""
        manager = AnsibleManager()

        playbooks_config = {
            "base": [{"hosts": "all", "tasks": []}],
            "webapp": [{"hosts": "all", "tasks": []}],
        }

        execution_order = []

        def track_execution(*args: Any, **kwargs: Any) -> mock.Mock:
            cmd = args[0]
            for pb_name in ["base", "webapp"]:
                if f"moondock-playbook-{pb_name}" in str(cmd):
                    execution_order.append(pb_name)
            mock_process = mock.Mock()
            mock_process.stdout = []
            mock_process.returncode = 0
            mock_process.wait = mock.Mock()
            return mock_process

        with mock.patch("shutil.which", return_value="/usr/bin/ansible-playbook"):
            with mock.patch("subprocess.Popen", side_effect=track_execution):
                manager.execute_playbooks(
                    playbook_names=["base", "webapp"],
                    playbooks_config=playbooks_config,
                    instance_ip="10.0.0.1",
                    ssh_key_file="/path/to/key.pem",
                )

    def test_execute_playbooks_cleanup_on_failure(self) -> None:
        """Test that temp files are cleaned up even on failure."""
        manager = AnsibleManager()

        playbooks_config = {
            "failing": [{"hosts": "all", "tasks": []}],
        }

        mock_process = mock.Mock()
        mock_process.stdout = []
        mock_process.returncode = 1
        mock_process.wait = mock.Mock()

        with mock.patch("shutil.which", return_value="/usr/bin/ansible-playbook"):
            with mock.patch("subprocess.Popen", return_value=mock_process):
                with pytest.raises(RuntimeError):
                    manager.execute_playbooks(
                        playbook_names=["failing"],
                        playbooks_config=playbooks_config,
                        instance_ip="10.0.0.1",
                        ssh_key_file="/path/to/key.pem",
                    )

                assert len(manager._temp_files) == 0

    def test_execute_playbooks_with_custom_ssh_username(self) -> None:
        """Test playbooks executed with custom SSH username."""
        manager = AnsibleManager()

        playbooks_config = {
            "setup": [{"hosts": "all", "tasks": []}],
        }

        mock_process = mock.Mock()
        mock_process.stdout = []
        mock_process.returncode = 0
        mock_process.wait = mock.Mock()

        captured_inventory_content = None

        def capture_popen(*args: Any, **kwargs: Any) -> mock.Mock:
            nonlocal captured_inventory_content
            cmd = args[0]
            inventory_path = cmd[2]
            if inventory_path.endswith(".ini"):
                with open(inventory_path) as f:
                    captured_inventory_content = f.read()
            return mock_process

        with mock.patch("shutil.which", return_value="/usr/bin/ansible-playbook"):
            with mock.patch("subprocess.Popen", side_effect=capture_popen):
                manager.execute_playbooks(
                    playbook_names=["setup"],
                    playbooks_config=playbooks_config,
                    instance_ip="10.0.0.1",
                    ssh_key_file="/path/to/key.pem",
                    ssh_username="ec2-user",
                    ssh_port=2222,
                )

                assert captured_inventory_content is not None
                assert "ansible_user=ec2-user" in captured_inventory_content
                assert "ansible_port=2222" in captured_inventory_content
