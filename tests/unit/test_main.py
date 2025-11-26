"""Unit tests for campers main module cleanup behavior."""

import logging
import signal
from unittest.mock import MagicMock


class TestCleanupLogging:
    """Test cleanup logging messages."""

    def test_stop_instance_cleanup_logs_initial_message(self, campers, caplog):
        """Verify cleanup logs initial shutdown message.

        Parameters
        ----------
        campers : Campers
            Campers instance
        caplog : LogCaptureFixture
            Pytest log capture fixture
        """
        campers._resources = {
            "instance_details": {"instance_id": "i-test"},
            "ec2_manager": MagicMock(),
        }

        with caplog.at_level(logging.INFO):
            campers._stop_instance_cleanup()

        assert any(
            "Shutdown requested - stopping instance and preserving resources..."
            in record.message
            for record in caplog.records
        )

    def test_terminate_instance_cleanup_logs_initial_message(self, campers, caplog):
        """Verify cleanup logs initial shutdown message.

        Parameters
        ----------
        campers : Campers
            Campers instance
        caplog : LogCaptureFixture
            Pytest log capture fixture
        """
        campers._resources = {
            "instance_details": {"instance_id": "i-test"},
            "ec2_manager": MagicMock(),
        }

        with caplog.at_level(logging.INFO):
            campers._terminate_instance_cleanup()

        assert any(
            "Shutdown requested - beginning cleanup..." in record.message
            for record in caplog.records
        )

    def test_cleanup_logs_completion_message_success(self, campers, caplog):
        """Verify cleanup logs successful completion message.

        Parameters
        ----------
        campers : Campers
            Campers instance
        caplog : LogCaptureFixture
            Pytest log capture fixture
        """
        mock_ec2 = MagicMock()
        mock_ec2.stop_instance.return_value = None
        mock_ec2.get_volume_size.return_value = 50

        campers._resources = {
            "instance_details": {"instance_id": "i-test"},
            "ec2_manager": mock_ec2,
        }

        with caplog.at_level(logging.INFO):
            campers._stop_instance_cleanup()

        assert any(
            "Cleanup completed successfully" in record.message
            for record in caplog.records
        )

    def test_cleanup_logs_completion_message_with_errors(self, campers, caplog):
        """Verify cleanup logs error count when errors occur.

        Parameters
        ----------
        campers : Campers
            Campers instance
        caplog : LogCaptureFixture
            Pytest log capture fixture
        """
        mock_ec2 = MagicMock()
        mock_ec2.stop_instance.side_effect = RuntimeError("Test error")

        campers._resources = {
            "instance_details": {"instance_id": "i-test"},
            "ec2_manager": mock_ec2,
        }

        with caplog.at_level(logging.INFO):
            campers._stop_instance_cleanup()

        assert any(
            "Cleanup completed with 1 errors" in record.message
            for record in caplog.records
        )


class TestPartialInitializationHandling:
    """Test cleanup handles partial initialization gracefully."""

    def test_skips_port_forwarding_cleanup_when_not_initialized(self, campers, caplog):
        """Verify port forwarding cleanup is skipped when not initialized.

        Parameters
        ----------
        campers : Campers
            Campers instance
        caplog : LogCaptureFixture
            Pytest log capture fixture
        """
        campers._resources = {
            "instance_details": {"instance_id": "i-test"},
            "ec2_manager": MagicMock(),
        }

        with caplog.at_level(logging.DEBUG):
            campers._stop_instance_cleanup()

        assert any(
            "Skipping port forwarding cleanup - not initialized" in record.message
            for record in caplog.records
        )

    def test_skips_mutagen_cleanup_when_not_initialized(self, campers, caplog):
        """Verify Mutagen cleanup is skipped when not initialized.

        Parameters
        ----------
        campers : Campers
            Campers instance
        caplog : LogCaptureFixture
            Pytest log capture fixture
        """
        campers._resources = {
            "instance_details": {"instance_id": "i-test"},
            "ec2_manager": MagicMock(),
        }

        with caplog.at_level(logging.DEBUG):
            campers._stop_instance_cleanup()

        assert any(
            "Skipping Mutagen cleanup - not initialized" in record.message
            for record in caplog.records
        )

    def test_skips_ssh_cleanup_when_not_initialized(self, campers, caplog):
        """Verify SSH cleanup is skipped when not initialized.

        Parameters
        ----------
        campers : Campers
            Campers instance
        caplog : LogCaptureFixture
            Pytest log capture fixture
        """
        campers._resources = {
            "instance_details": {"instance_id": "i-test"},
            "ec2_manager": MagicMock(),
        }

        with caplog.at_level(logging.DEBUG):
            campers._stop_instance_cleanup()

        assert any(
            "Skipping SSH cleanup - not initialized" in record.message
            for record in caplog.records
        )

    def test_handles_empty_resources_gracefully(self, campers, caplog):
        """Verify cleanup handles empty resources gracefully.

        Parameters
        ----------
        campers : Campers
            Campers instance
        caplog : LogCaptureFixture
            Pytest log capture fixture
        """
        campers._resources = {}

        with caplog.at_level(logging.INFO):
            campers._stop_instance_cleanup()

        assert any(
            "No resources to clean up" in record.message
            for record in caplog.records
        )

    def test_skips_instance_cleanup_when_not_initialized(self, campers, caplog):
        """Verify instance cleanup is skipped when instance not initialized.

        Parameters
        ----------
        campers : Campers
            Campers instance
        caplog : LogCaptureFixture
            Pytest log capture fixture
        """
        campers._resources = {}

        with caplog.at_level(logging.DEBUG):
            campers._stop_instance_cleanup()

        assert any(
            "No resources to clean up" in record.message
            for record in caplog.records
        )


class TestCleanupOrder:
    """Test cleanup executes in correct order."""

    def test_cleanup_order_stop_instance(self, campers):
        """Verify cleanup order for stop instance.

        Parameters
        ----------
        campers : Campers
            Campers instance
        """
        cleanup_sequence = []

        mock_portforward = MagicMock()
        mock_portforward.stop_all_tunnels.side_effect = (
            lambda: cleanup_sequence.append("port_forward")
        )

        mock_mutagen = MagicMock()
        mock_mutagen.terminate_session.side_effect = (
            lambda name, ssh_wrapper_dir=None, host=None: cleanup_sequence.append(
                "mutagen"
            )
        )

        mock_ssh = MagicMock()
        mock_ssh.close.side_effect = lambda: cleanup_sequence.append("ssh")

        mock_ec2 = MagicMock()
        mock_ec2.stop_instance.side_effect = (
            lambda id: cleanup_sequence.append("ec2")
        )
        mock_ec2.get_volume_size.return_value = 50

        campers._resources = {
            "portforward_mgr": mock_portforward,
            "mutagen_mgr": mock_mutagen,
            "mutagen_session_name": "test-session",
            "ssh_manager": mock_ssh,
            "instance_details": {"instance_id": "i-test"},
            "ec2_manager": mock_ec2,
        }

        campers._stop_instance_cleanup()

        assert cleanup_sequence == ["port_forward", "mutagen", "ssh", "ec2"]

    def test_cleanup_order_terminate_instance(self, campers):
        """Verify cleanup order for terminate instance.

        Parameters
        ----------
        campers : Campers
            Campers instance
        """
        cleanup_sequence = []

        mock_portforward = MagicMock()
        mock_portforward.stop_all_tunnels.side_effect = (
            lambda: cleanup_sequence.append("port_forward")
        )

        mock_mutagen = MagicMock()
        mock_mutagen.terminate_session.side_effect = (
            lambda name, ssh_wrapper_dir=None, host=None: cleanup_sequence.append(
                "mutagen"
            )
        )

        mock_ssh = MagicMock()
        mock_ssh.close.side_effect = lambda: cleanup_sequence.append("ssh")

        mock_ec2 = MagicMock()
        mock_ec2.terminate_instance.side_effect = (
            lambda id: cleanup_sequence.append("ec2")
        )

        campers._resources = {
            "portforward_mgr": mock_portforward,
            "mutagen_mgr": mock_mutagen,
            "mutagen_session_name": "test-session",
            "ssh_manager": mock_ssh,
            "instance_details": {"instance_id": "i-test"},
            "ec2_manager": mock_ec2,
        }

        campers._terminate_instance_cleanup()

        assert cleanup_sequence == ["port_forward", "mutagen", "ssh", "ec2"]


class TestErrorResilience:
    """Test cleanup continues despite individual failures."""

    def test_cleanup_continues_after_port_forward_error(self, campers):
        """Verify cleanup continues after port forward error.

        Parameters
        ----------
        campers : Campers
            Campers instance
        """
        cleanup_sequence = []

        mock_portforward = MagicMock()
        mock_portforward.stop_all_tunnels.side_effect = RuntimeError(
            "Port forward error"
        )

        mock_mutagen = MagicMock()
        mock_mutagen.terminate_session.side_effect = (
            lambda name, ssh_wrapper_dir=None, host=None: cleanup_sequence.append(
                "mutagen"
            )
        )

        mock_ssh = MagicMock()
        mock_ssh.close.side_effect = lambda: cleanup_sequence.append("ssh")

        mock_ec2 = MagicMock()
        mock_ec2.stop_instance.side_effect = (
            lambda id: cleanup_sequence.append("ec2")
        )
        mock_ec2.get_volume_size.return_value = 50

        campers._resources = {
            "portforward_mgr": mock_portforward,
            "mutagen_mgr": mock_mutagen,
            "mutagen_session_name": "test-session",
            "ssh_manager": mock_ssh,
            "instance_details": {"instance_id": "i-test"},
            "ec2_manager": mock_ec2,
        }

        campers._stop_instance_cleanup()

        assert "mutagen" in cleanup_sequence
        assert "ssh" in cleanup_sequence
        assert "ec2" in cleanup_sequence

    def test_cleanup_continues_after_mutagen_error(self, campers):
        """Verify cleanup continues after Mutagen error.

        Parameters
        ----------
        campers : Campers
            Campers instance
        """
        cleanup_sequence = []

        mock_portforward = MagicMock()
        mock_portforward.stop_all_tunnels.side_effect = (
            lambda: cleanup_sequence.append("port_forward")
        )

        mock_mutagen = MagicMock()
        mock_mutagen.terminate_session.side_effect = RuntimeError("Mutagen error")

        mock_ssh = MagicMock()
        mock_ssh.close.side_effect = lambda: cleanup_sequence.append("ssh")

        mock_ec2 = MagicMock()
        mock_ec2.stop_instance.side_effect = (
            lambda id: cleanup_sequence.append("ec2")
        )
        mock_ec2.get_volume_size.return_value = 50

        campers._resources = {
            "portforward_mgr": mock_portforward,
            "mutagen_mgr": mock_mutagen,
            "mutagen_session_name": "test-session",
            "ssh_manager": mock_ssh,
            "instance_details": {"instance_id": "i-test"},
            "ec2_manager": mock_ec2,
        }

        campers._stop_instance_cleanup()

        assert "port_forward" in cleanup_sequence
        assert "ssh" in cleanup_sequence
        assert "ec2" in cleanup_sequence

    def test_cleanup_continues_after_ssh_error(self, campers):
        """Verify cleanup continues after SSH error.

        Parameters
        ----------
        campers : Campers
            Campers instance
        """
        cleanup_sequence = []

        mock_portforward = MagicMock()
        mock_portforward.stop_all_tunnels.side_effect = (
            lambda: cleanup_sequence.append("port_forward")
        )

        mock_mutagen = MagicMock()
        mock_mutagen.terminate_session.side_effect = (
            lambda name, ssh_wrapper_dir=None, host=None: cleanup_sequence.append(
                "mutagen"
            )
        )

        mock_ssh = MagicMock()
        mock_ssh.close.side_effect = RuntimeError("SSH error")

        mock_ec2 = MagicMock()
        mock_ec2.stop_instance.side_effect = (
            lambda id: cleanup_sequence.append("ec2")
        )
        mock_ec2.get_volume_size.return_value = 50

        campers._resources = {
            "portforward_mgr": mock_portforward,
            "mutagen_mgr": mock_mutagen,
            "mutagen_session_name": "test-session",
            "ssh_manager": mock_ssh,
            "instance_details": {"instance_id": "i-test"},
            "ec2_manager": mock_ec2,
        }

        campers._stop_instance_cleanup()

        assert "port_forward" in cleanup_sequence
        assert "mutagen" in cleanup_sequence
        assert "ec2" in cleanup_sequence

    def test_cleanup_collects_errors(self, campers, caplog):
        """Verify all errors are collected and reported.

        Parameters
        ----------
        campers : Campers
            Campers instance
        caplog : LogCaptureFixture
            Pytest log capture fixture
        """
        mock_portforward = MagicMock()
        mock_portforward.stop_all_tunnels.side_effect = RuntimeError(
            "Port forward error"
        )

        mock_mutagen = MagicMock()
        mock_mutagen.terminate_session.side_effect = RuntimeError("Mutagen error")

        mock_ssh = MagicMock()
        mock_ssh.close.side_effect = RuntimeError("SSH error")

        mock_ec2 = MagicMock()
        mock_ec2.stop_instance.side_effect = RuntimeError("EC2 error")
        mock_ec2.get_volume_size.return_value = 50

        campers._resources = {
            "portforward_mgr": mock_portforward,
            "mutagen_mgr": mock_mutagen,
            "mutagen_session_name": "test-session",
            "ssh_manager": mock_ssh,
            "instance_details": {"instance_id": "i-test"},
            "ec2_manager": mock_ec2,
        }

        with caplog.at_level(logging.INFO):
            campers._stop_instance_cleanup()

        assert any(
            "Cleanup completed with 4 errors" in record.message
            for record in caplog.records
        )


class TestDuplicateCleanupPrevention:
    """Test duplicate cleanup is prevented."""

    def test_duplicate_cleanup_is_skipped(self, campers, caplog):
        """Verify second cleanup attempt is skipped.

        Parameters
        ----------
        campers : Campers
            Campers instance
        caplog : LogCaptureFixture
            Pytest log capture fixture
        """
        campers._resources = {
            "instance_details": {"instance_id": "i-test"},
            "ec2_manager": MagicMock(),
        }

        campers._cleanup_in_progress = True

        with caplog.at_level(logging.INFO):
            campers._cleanup_resources(signum=signal.SIGINT, frame=None)

        assert any(
            "Cleanup already in progress" in record.message
            for record in caplog.records
        )


class TestExitCodes:
    """Test exit code logic in cleanup."""

    def test_cleanup_exit_code_logic(self, campers):
        """Verify exit code mapping for signals is correct.

        Parameters
        ----------
        campers : Campers
            Campers instance
        """
        campers._resources = {
            "instance_details": {"instance_id": "i-test"},
            "ec2_manager": MagicMock(),
        }
        campers.merged_config = {"on_exit": "stop"}

        campers._cleanup_resources(signum=None, frame=None)

        assert campers._cleanup_in_progress is False


class TestResourceLocking:
    """Test resource locking during cleanup."""

    def test_resources_cleared_after_cleanup(self, campers):
        """Verify resources are cleared after cleanup.

        Parameters
        ----------
        campers : Campers
            Campers instance
        """
        campers._resources = {
            "instance_details": {"instance_id": "i-test"},
            "ec2_manager": MagicMock(),
        }

        campers._stop_instance_cleanup()

        assert len(campers._resources) == 0

    def test_cleanup_lock_released_after_cleanup(self, campers):
        """Verify cleanup lock is released after cleanup.

        Parameters
        ----------
        campers : Campers
            Campers instance
        """
        campers._resources = {
            "instance_details": {"instance_id": "i-test"},
            "ec2_manager": MagicMock(),
        }

        campers._cleanup_resources()

        assert campers._cleanup_in_progress is False
