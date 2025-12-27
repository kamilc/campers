"""Unit tests for campers main module cleanup behavior."""

import logging
import signal
from datetime import UTC, datetime, timedelta
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
            "Shutdown requested - stopping instance and preserving resources..." in record.message
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
            "compute_provider": mock_ec2,
        }

        with caplog.at_level(logging.INFO):
            campers._stop_instance_cleanup()

        assert any("Cleanup completed successfully" in record.message for record in caplog.records)

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
            "compute_provider": mock_ec2,
        }

        with caplog.at_level(logging.INFO):
            campers._stop_instance_cleanup()

        assert any("Cleanup completed with 1 errors" in record.message for record in caplog.records)


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
            "Skipping SSH cleanup - not initialized" in record.message for record in caplog.records
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

        assert any("No resources to clean up" in record.message for record in caplog.records)

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

        assert any("No resources to clean up" in record.message for record in caplog.records)


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
        mock_portforward.stop_all_tunnels.side_effect = lambda: cleanup_sequence.append(
            "port_forward"
        )

        mock_mutagen = MagicMock()
        mock_mutagen.terminate_session.side_effect = (
            lambda name, ssh_wrapper_dir=None, host=None: cleanup_sequence.append("mutagen")
        )

        mock_ssh = MagicMock()
        mock_ssh.close.side_effect = lambda: cleanup_sequence.append("ssh")

        mock_ec2 = MagicMock()
        mock_ec2.stop_instance.side_effect = lambda id: cleanup_sequence.append("ec2")
        mock_ec2.get_volume_size.return_value = 50

        campers._resources = {
            "portforward_mgr": mock_portforward,
            "mutagen_mgr": mock_mutagen,
            "mutagen_session_name": "test-session",
            "ssh_manager": mock_ssh,
            "instance_details": {"instance_id": "i-test"},
            "compute_provider": mock_ec2,
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
        mock_portforward.stop_all_tunnels.side_effect = lambda: cleanup_sequence.append(
            "port_forward"
        )

        mock_mutagen = MagicMock()
        mock_mutagen.terminate_session.side_effect = (
            lambda name, ssh_wrapper_dir=None, host=None: cleanup_sequence.append("mutagen")
        )

        mock_ssh = MagicMock()
        mock_ssh.close.side_effect = lambda: cleanup_sequence.append("ssh")

        mock_ec2 = MagicMock()
        mock_ec2.terminate_instance.side_effect = lambda id: cleanup_sequence.append("ec2")

        campers._resources = {
            "portforward_mgr": mock_portforward,
            "mutagen_mgr": mock_mutagen,
            "mutagen_session_name": "test-session",
            "ssh_manager": mock_ssh,
            "instance_details": {"instance_id": "i-test"},
            "compute_provider": mock_ec2,
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
        mock_portforward.stop_all_tunnels.side_effect = RuntimeError("Port forward error")

        mock_mutagen = MagicMock()
        mock_mutagen.terminate_session.side_effect = (
            lambda name, ssh_wrapper_dir=None, host=None: cleanup_sequence.append("mutagen")
        )

        mock_ssh = MagicMock()
        mock_ssh.close.side_effect = lambda: cleanup_sequence.append("ssh")

        mock_ec2 = MagicMock()
        mock_ec2.stop_instance.side_effect = lambda id: cleanup_sequence.append("ec2")
        mock_ec2.get_volume_size.return_value = 50

        campers._resources = {
            "portforward_mgr": mock_portforward,
            "mutagen_mgr": mock_mutagen,
            "mutagen_session_name": "test-session",
            "ssh_manager": mock_ssh,
            "instance_details": {"instance_id": "i-test"},
            "compute_provider": mock_ec2,
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
        mock_portforward.stop_all_tunnels.side_effect = lambda: cleanup_sequence.append(
            "port_forward"
        )

        mock_mutagen = MagicMock()
        mock_mutagen.terminate_session.side_effect = RuntimeError("Mutagen error")

        mock_ssh = MagicMock()
        mock_ssh.close.side_effect = lambda: cleanup_sequence.append("ssh")

        mock_ec2 = MagicMock()
        mock_ec2.stop_instance.side_effect = lambda id: cleanup_sequence.append("ec2")
        mock_ec2.get_volume_size.return_value = 50

        campers._resources = {
            "portforward_mgr": mock_portforward,
            "mutagen_mgr": mock_mutagen,
            "mutagen_session_name": "test-session",
            "ssh_manager": mock_ssh,
            "instance_details": {"instance_id": "i-test"},
            "compute_provider": mock_ec2,
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
        mock_portforward.stop_all_tunnels.side_effect = lambda: cleanup_sequence.append(
            "port_forward"
        )

        mock_mutagen = MagicMock()
        mock_mutagen.terminate_session.side_effect = (
            lambda name, ssh_wrapper_dir=None, host=None: cleanup_sequence.append("mutagen")
        )

        mock_ssh = MagicMock()
        mock_ssh.close.side_effect = RuntimeError("SSH error")

        mock_ec2 = MagicMock()
        mock_ec2.stop_instance.side_effect = lambda id: cleanup_sequence.append("ec2")
        mock_ec2.get_volume_size.return_value = 50

        campers._resources = {
            "portforward_mgr": mock_portforward,
            "mutagen_mgr": mock_mutagen,
            "mutagen_session_name": "test-session",
            "ssh_manager": mock_ssh,
            "instance_details": {"instance_id": "i-test"},
            "compute_provider": mock_ec2,
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
        mock_portforward.stop_all_tunnels.side_effect = RuntimeError("Port forward error")

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
            "compute_provider": mock_ec2,
        }

        with caplog.at_level(logging.INFO):
            campers._stop_instance_cleanup()

        assert any("Cleanup completed with 4 errors" in record.message for record in caplog.records)


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

        assert any("Cleanup already in progress" in record.message for record in caplog.records)


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
        campers.merged_config = {}

        campers._cleanup_resources(action="stop", signum=None, frame=None)

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


class TestMultipleSessionCleanup:
    """Test cleanup with multiple Mutagen sessions."""

    def test_cleanup_multiple_sessions(self, campers):
        """Verify all Mutagen sessions are terminated when multiple exist.

        Parameters
        ----------
        campers : Campers
            Campers instance
        """
        cleanup_sequence = []

        mock_mutagen = MagicMock()
        mock_mutagen.terminate_session.side_effect = (
            lambda name, ssh_wrapper_dir=None, host=None: cleanup_sequence.append(name)
        )

        mock_ec2 = MagicMock()
        mock_ec2.stop_instance.side_effect = lambda id: cleanup_sequence.append("ec2")
        mock_ec2.get_volume_size.return_value = 50

        campers._resources = {
            "mutagen_mgr": mock_mutagen,
            "mutagen_session_names": ["session-0", "session-1", "session-2"],
            "instance_details": {"instance_id": "i-test"},
            "compute_provider": mock_ec2,
        }

        campers._stop_instance_cleanup()

        assert "session-0" in cleanup_sequence
        assert "session-1" in cleanup_sequence
        assert "session-2" in cleanup_sequence
        assert mock_mutagen.terminate_session.call_count == 3

    def test_cleanup_continues_when_one_session_fails(self, campers):
        """Verify cleanup continues when one session termination fails.

        Parameters
        ----------
        campers : Campers
            Campers instance
        """
        terminated_sessions = []

        def terminate_with_error(name, ssh_wrapper_dir=None, host=None):
            if name == "session-1":
                raise RuntimeError(f"Failed to terminate {name}")
            terminated_sessions.append(name)

        mock_mutagen = MagicMock()
        mock_mutagen.terminate_session.side_effect = terminate_with_error

        mock_ec2 = MagicMock()
        mock_ec2.stop_instance.side_effect = lambda id: None
        mock_ec2.get_volume_size.return_value = 50

        campers._resources = {
            "mutagen_mgr": mock_mutagen,
            "mutagen_session_names": ["session-0", "session-1", "session-2"],
            "instance_details": {"instance_id": "i-test"},
            "compute_provider": mock_ec2,
        }

        campers._stop_instance_cleanup()

        assert "session-0" in terminated_sessions
        assert "session-2" in terminated_sessions
        assert mock_ec2.stop_instance.called

    def test_cleanup_with_multiple_sessions_and_all_fail(self, campers, caplog):
        """Verify resilience when all session terminations fail.

        Parameters
        ----------
        campers : Campers
            Campers instance
        caplog : LogCaptureFixture
            Pytest log capture fixture
        """
        mock_mutagen = MagicMock()
        mock_mutagen.terminate_session.side_effect = RuntimeError("Session termination failed")

        mock_ec2 = MagicMock()
        mock_ec2.stop_instance.side_effect = lambda id: None
        mock_ec2.get_volume_size.return_value = 50

        campers._resources = {
            "mutagen_mgr": mock_mutagen,
            "mutagen_session_names": ["session-0", "session-1"],
            "instance_details": {"instance_id": "i-test"},
            "compute_provider": mock_ec2,
        }

        with caplog.at_level(logging.INFO):
            campers._stop_instance_cleanup()

        assert any("Cleanup completed with 2 errors" in record.message for record in caplog.records)
        assert mock_ec2.stop_instance.called

    def test_cleanup_uses_plural_session_names_when_available(self, campers):
        """Verify cleanup uses mutagen_session_names (plural) when available.

        Parameters
        ----------
        campers : Campers
            Campers instance
        """
        terminated_sessions = []

        mock_mutagen = MagicMock()
        mock_mutagen.terminate_session.side_effect = (
            lambda name, ssh_wrapper_dir=None, host=None: terminated_sessions.append(name)
        )

        mock_ec2 = MagicMock()
        mock_ec2.stop_instance.side_effect = lambda id: None
        mock_ec2.get_volume_size.return_value = 50

        campers._resources = {
            "mutagen_mgr": mock_mutagen,
            "mutagen_session_names": ["new-session-1", "new-session-2"],
            "mutagen_session_name": "old-session",
            "instance_details": {"instance_id": "i-test"},
            "compute_provider": mock_ec2,
        }

        campers._stop_instance_cleanup()

        assert "new-session-1" in terminated_sessions
        assert "new-session-2" in terminated_sessions
        assert "old-session" not in terminated_sessions

    def test_cleanup_falls_back_to_singular_session_name(self, campers):
        """Verify cleanup falls back to mutagen_session_name when plural not available.

        Parameters
        ----------
        campers : Campers
            Campers instance
        """
        terminated_sessions = []

        mock_mutagen = MagicMock()
        mock_mutagen.terminate_session.side_effect = (
            lambda name, ssh_wrapper_dir=None, host=None: terminated_sessions.append(name)
        )

        mock_ec2 = MagicMock()
        mock_ec2.stop_instance.side_effect = lambda id: None
        mock_ec2.get_volume_size.return_value = 50

        campers._resources = {
            "mutagen_mgr": mock_mutagen,
            "mutagen_session_name": "fallback-session",
            "instance_details": {"instance_id": "i-test"},
            "compute_provider": mock_ec2,
        }

        campers._stop_instance_cleanup()

        assert "fallback-session" in terminated_sessions


class TestUptimeCalculation:
    """Test uptime calculation in CampersTUI."""

    def test_update_uptime_clamps_negative_values_to_zero(self, campers_tui):
        """Verify negative uptime is clamped to zero when start_time is in future.

        Parameters
        ----------
        campers_tui : CampersTUI
            CampersTUI instance
        """
        from campers.tui.widgets.labeled_value import LabeledValue

        future_time = datetime.now(UTC) + timedelta(hours=1)
        campers_tui.instance_start_time = future_time.replace(tzinfo=None)

        campers_tui.update_uptime()

        queried_widget = campers_tui.query_one("#uptime-widget", LabeledValue)
        assert "0s" in queried_widget.value

    def test_update_uptime_formats_correctly_with_hours(self, campers_tui):
        """Verify uptime formats correctly as HH:MM:SS with 1+ hours.

        Parameters
        ----------
        campers_tui : CampersTUI
            CampersTUI instance
        """
        from campers.tui.widgets.labeled_value import LabeledValue

        past_time = datetime.now(UTC) - timedelta(hours=3, minutes=45, seconds=30)
        campers_tui.instance_start_time = past_time.replace(tzinfo=None)

        campers_tui.update_uptime()

        queried_widget = campers_tui.query_one("#uptime-widget", LabeledValue)
        value = queried_widget.value
        assert "03:" in value and "45:" in value

    def test_update_uptime_handles_none_instance_start_time(self, campers_tui):
        """Verify update_uptime returns early when instance_start_time is None.

        Parameters
        ----------
        campers_tui : CampersTUI
            CampersTUI instance
        """
        campers_tui.instance_start_time = None

        campers_tui.update_uptime()

        queried_widget = campers_tui.query_one("#uptime-widget")
        assert queried_widget.update.call_count == 0
