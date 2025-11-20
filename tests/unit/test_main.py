"""Unit tests for moondock main module cleanup behavior."""

import logging
import signal
from unittest.mock import MagicMock


class TestCleanupLogging:
    """Test cleanup logging messages."""

    def test_stop_instance_cleanup_logs_initial_message(self, moondock, caplog):
        """Verify cleanup logs initial shutdown message.

        Parameters
        ----------
        moondock : Moondock
            Moondock instance
        caplog : LogCaptureFixture
            Pytest log capture fixture
        """
        moondock._resources = {
            "instance_details": {"instance_id": "i-test"},
            "ec2_manager": MagicMock(),
        }

        with caplog.at_level(logging.INFO):
            moondock._stop_instance_cleanup()

        assert any(
            "Shutdown requested - stopping instance and preserving resources..."
            in record.message
            for record in caplog.records
        )

    def test_terminate_instance_cleanup_logs_initial_message(self, moondock, caplog):
        """Verify cleanup logs initial shutdown message.

        Parameters
        ----------
        moondock : Moondock
            Moondock instance
        caplog : LogCaptureFixture
            Pytest log capture fixture
        """
        moondock._resources = {
            "instance_details": {"instance_id": "i-test"},
            "ec2_manager": MagicMock(),
        }

        with caplog.at_level(logging.INFO):
            moondock._terminate_instance_cleanup()

        assert any(
            "Shutdown requested - beginning cleanup..." in record.message
            for record in caplog.records
        )

    def test_cleanup_logs_completion_message_success(self, moondock, caplog):
        """Verify cleanup logs successful completion message.

        Parameters
        ----------
        moondock : Moondock
            Moondock instance
        caplog : LogCaptureFixture
            Pytest log capture fixture
        """
        mock_ec2 = MagicMock()
        mock_ec2.stop_instance.return_value = None
        mock_ec2.get_volume_size.return_value = 50

        moondock._resources = {
            "instance_details": {"instance_id": "i-test"},
            "ec2_manager": mock_ec2,
        }

        with caplog.at_level(logging.INFO):
            moondock._stop_instance_cleanup()

        assert any(
            "Cleanup completed successfully" in record.message
            for record in caplog.records
        )

    def test_cleanup_logs_completion_message_with_errors(self, moondock, caplog):
        """Verify cleanup logs error count when errors occur.

        Parameters
        ----------
        moondock : Moondock
            Moondock instance
        caplog : LogCaptureFixture
            Pytest log capture fixture
        """
        mock_ec2 = MagicMock()
        mock_ec2.stop_instance.side_effect = RuntimeError("Test error")

        moondock._resources = {
            "instance_details": {"instance_id": "i-test"},
            "ec2_manager": mock_ec2,
        }

        with caplog.at_level(logging.INFO):
            moondock._stop_instance_cleanup()

        assert any(
            "Cleanup completed with 1 errors" in record.message
            for record in caplog.records
        )


class TestPartialInitializationHandling:
    """Test cleanup handles partial initialization gracefully."""

    def test_skips_port_forwarding_cleanup_when_not_initialized(self, moondock, caplog):
        """Verify port forwarding cleanup is skipped when not initialized.

        Parameters
        ----------
        moondock : Moondock
            Moondock instance
        caplog : LogCaptureFixture
            Pytest log capture fixture
        """
        moondock._resources = {
            "instance_details": {"instance_id": "i-test"},
            "ec2_manager": MagicMock(),
        }

        with caplog.at_level(logging.DEBUG):
            moondock._stop_instance_cleanup()

        assert any(
            "Skipping port forwarding cleanup - not initialized" in record.message
            for record in caplog.records
        )

    def test_skips_mutagen_cleanup_when_not_initialized(self, moondock, caplog):
        """Verify Mutagen cleanup is skipped when not initialized.

        Parameters
        ----------
        moondock : Moondock
            Moondock instance
        caplog : LogCaptureFixture
            Pytest log capture fixture
        """
        moondock._resources = {
            "instance_details": {"instance_id": "i-test"},
            "ec2_manager": MagicMock(),
        }

        with caplog.at_level(logging.DEBUG):
            moondock._stop_instance_cleanup()

        assert any(
            "Skipping Mutagen cleanup - not initialized" in record.message
            for record in caplog.records
        )

    def test_skips_ssh_cleanup_when_not_initialized(self, moondock, caplog):
        """Verify SSH cleanup is skipped when not initialized.

        Parameters
        ----------
        moondock : Moondock
            Moondock instance
        caplog : LogCaptureFixture
            Pytest log capture fixture
        """
        moondock._resources = {
            "instance_details": {"instance_id": "i-test"},
            "ec2_manager": MagicMock(),
        }

        with caplog.at_level(logging.DEBUG):
            moondock._stop_instance_cleanup()

        assert any(
            "Skipping SSH cleanup - not initialized" in record.message
            for record in caplog.records
        )

    def test_handles_empty_resources_gracefully(self, moondock, caplog):
        """Verify cleanup handles empty resources gracefully.

        Parameters
        ----------
        moondock : Moondock
            Moondock instance
        caplog : LogCaptureFixture
            Pytest log capture fixture
        """
        moondock._resources = {}

        with caplog.at_level(logging.INFO):
            moondock._stop_instance_cleanup()

        assert any(
            "No resources to clean up" in record.message
            for record in caplog.records
        )

    def test_skips_instance_cleanup_when_not_initialized(self, moondock, caplog):
        """Verify instance cleanup is skipped when instance not initialized.

        Parameters
        ----------
        moondock : Moondock
            Moondock instance
        caplog : LogCaptureFixture
            Pytest log capture fixture
        """
        moondock._resources = {}

        with caplog.at_level(logging.DEBUG):
            moondock._stop_instance_cleanup()

        assert any(
            "No resources to clean up" in record.message
            for record in caplog.records
        )


class TestCleanupOrder:
    """Test cleanup executes in correct order."""

    def test_cleanup_order_stop_instance(self, moondock):
        """Verify cleanup order for stop instance.

        Parameters
        ----------
        moondock : Moondock
            Moondock instance
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

        moondock._resources = {
            "portforward_mgr": mock_portforward,
            "mutagen_mgr": mock_mutagen,
            "mutagen_session_name": "test-session",
            "ssh_manager": mock_ssh,
            "instance_details": {"instance_id": "i-test"},
            "ec2_manager": mock_ec2,
        }

        moondock._stop_instance_cleanup()

        assert cleanup_sequence == ["port_forward", "mutagen", "ssh", "ec2"]

    def test_cleanup_order_terminate_instance(self, moondock):
        """Verify cleanup order for terminate instance.

        Parameters
        ----------
        moondock : Moondock
            Moondock instance
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

        moondock._resources = {
            "portforward_mgr": mock_portforward,
            "mutagen_mgr": mock_mutagen,
            "mutagen_session_name": "test-session",
            "ssh_manager": mock_ssh,
            "instance_details": {"instance_id": "i-test"},
            "ec2_manager": mock_ec2,
        }

        moondock._terminate_instance_cleanup()

        assert cleanup_sequence == ["port_forward", "mutagen", "ssh", "ec2"]


class TestErrorResilience:
    """Test cleanup continues despite individual failures."""

    def test_cleanup_continues_after_port_forward_error(self, moondock):
        """Verify cleanup continues after port forward error.

        Parameters
        ----------
        moondock : Moondock
            Moondock instance
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

        moondock._resources = {
            "portforward_mgr": mock_portforward,
            "mutagen_mgr": mock_mutagen,
            "mutagen_session_name": "test-session",
            "ssh_manager": mock_ssh,
            "instance_details": {"instance_id": "i-test"},
            "ec2_manager": mock_ec2,
        }

        moondock._stop_instance_cleanup()

        assert "mutagen" in cleanup_sequence
        assert "ssh" in cleanup_sequence
        assert "ec2" in cleanup_sequence

    def test_cleanup_continues_after_mutagen_error(self, moondock):
        """Verify cleanup continues after Mutagen error.

        Parameters
        ----------
        moondock : Moondock
            Moondock instance
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

        moondock._resources = {
            "portforward_mgr": mock_portforward,
            "mutagen_mgr": mock_mutagen,
            "mutagen_session_name": "test-session",
            "ssh_manager": mock_ssh,
            "instance_details": {"instance_id": "i-test"},
            "ec2_manager": mock_ec2,
        }

        moondock._stop_instance_cleanup()

        assert "port_forward" in cleanup_sequence
        assert "ssh" in cleanup_sequence
        assert "ec2" in cleanup_sequence

    def test_cleanup_continues_after_ssh_error(self, moondock):
        """Verify cleanup continues after SSH error.

        Parameters
        ----------
        moondock : Moondock
            Moondock instance
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

        moondock._resources = {
            "portforward_mgr": mock_portforward,
            "mutagen_mgr": mock_mutagen,
            "mutagen_session_name": "test-session",
            "ssh_manager": mock_ssh,
            "instance_details": {"instance_id": "i-test"},
            "ec2_manager": mock_ec2,
        }

        moondock._stop_instance_cleanup()

        assert "port_forward" in cleanup_sequence
        assert "mutagen" in cleanup_sequence
        assert "ec2" in cleanup_sequence

    def test_cleanup_collects_errors(self, moondock, caplog):
        """Verify all errors are collected and reported.

        Parameters
        ----------
        moondock : Moondock
            Moondock instance
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

        moondock._resources = {
            "portforward_mgr": mock_portforward,
            "mutagen_mgr": mock_mutagen,
            "mutagen_session_name": "test-session",
            "ssh_manager": mock_ssh,
            "instance_details": {"instance_id": "i-test"},
            "ec2_manager": mock_ec2,
        }

        with caplog.at_level(logging.INFO):
            moondock._stop_instance_cleanup()

        assert any(
            "Cleanup completed with 4 errors" in record.message
            for record in caplog.records
        )


class TestDuplicateCleanupPrevention:
    """Test duplicate cleanup is prevented."""

    def test_duplicate_cleanup_is_skipped(self, moondock, caplog):
        """Verify second cleanup attempt is skipped.

        Parameters
        ----------
        moondock : Moondock
            Moondock instance
        caplog : LogCaptureFixture
            Pytest log capture fixture
        """
        moondock._resources = {
            "instance_details": {"instance_id": "i-test"},
            "ec2_manager": MagicMock(),
        }

        moondock._cleanup_in_progress = True

        with caplog.at_level(logging.INFO):
            moondock._cleanup_resources(signum=signal.SIGINT, frame=None)

        assert any(
            "Cleanup already in progress" in record.message
            for record in caplog.records
        )


class TestExitCodes:
    """Test exit code logic in cleanup."""

    def test_cleanup_exit_code_logic(self, moondock):
        """Verify exit code mapping for signals is correct.

        Parameters
        ----------
        moondock : Moondock
            Moondock instance
        """
        moondock._resources = {
            "instance_details": {"instance_id": "i-test"},
            "ec2_manager": MagicMock(),
        }
        moondock.merged_config = {"on_exit": "stop"}

        moondock._cleanup_resources(signum=None, frame=None)

        assert moondock._cleanup_in_progress is False


class TestResourceLocking:
    """Test resource locking during cleanup."""

    def test_resources_cleared_after_cleanup(self, moondock):
        """Verify resources are cleared after cleanup.

        Parameters
        ----------
        moondock : Moondock
            Moondock instance
        """
        moondock._resources = {
            "instance_details": {"instance_id": "i-test"},
            "ec2_manager": MagicMock(),
        }

        moondock._stop_instance_cleanup()

        assert len(moondock._resources) == 0

    def test_cleanup_lock_released_after_cleanup(self, moondock):
        """Verify cleanup lock is released after cleanup.

        Parameters
        ----------
        moondock : Moondock
            Moondock instance
        """
        moondock._resources = {
            "instance_details": {"instance_id": "i-test"},
            "ec2_manager": MagicMock(),
        }

        moondock._cleanup_resources()

        assert moondock._cleanup_in_progress is False
