"""Unit tests for RunExecutor."""

import queue
import threading
from unittest.mock import Mock, patch

import pytest

from campers.core.run_executor import RunExecutor


@pytest.fixture
def config_loader():
    """Create mock config loader.

    Returns
    -------
    Mock
        Mock ConfigLoader instance
    """
    return Mock()


@pytest.fixture
def compute_provider_factory():
    """Create mock compute provider factory.

    Returns
    -------
    Mock
        Mock compute provider factory
    """
    return Mock()


@pytest.fixture
def ssh_manager_factory():
    """Create mock SSH manager factory.

    Returns
    -------
    Mock
        Mock SSH manager factory
    """
    return Mock()


@pytest.fixture
def resources():
    """Create resources dictionary.

    Returns
    -------
    dict
        Resources dictionary
    """
    return {}


@pytest.fixture
def resources_lock():
    """Create resources lock.

    Returns
    -------
    threading.Lock
        Thread lock for resources
    """
    return threading.Lock()


@pytest.fixture
def cleanup_in_progress_getter():
    """Create cleanup in progress getter.

    Returns
    -------
    Mock
        Mock cleanup getter that returns False
    """
    return Mock(return_value=False)


@pytest.fixture
def run_executor(
    config_loader,
    compute_provider_factory,
    ssh_manager_factory,
    resources,
    resources_lock,
    cleanup_in_progress_getter,
):
    """Create RunExecutor instance for testing.

    Parameters
    ----------
    config_loader : Mock
        Mock ConfigLoader instance
    compute_provider_factory : Mock
        Mock compute provider factory
    ssh_manager_factory : Mock
        Mock SSH manager factory
    resources : dict
        Resources dictionary
    resources_lock : threading.Lock
        Thread lock for resources
    cleanup_in_progress_getter : Mock
        Mock cleanup getter

    Returns
    -------
    RunExecutor
        RunExecutor instance for testing
    """
    return RunExecutor(
        config_loader=config_loader,
        compute_provider_factory=compute_provider_factory,
        ssh_manager_factory=ssh_manager_factory,
        resources=resources,
        resources_lock=resources_lock,
        cleanup_in_progress_getter=cleanup_in_progress_getter,
        update_queue=queue.Queue(),
    )


def test_phase_file_sync_sends_status_text_updates(run_executor):
    """Test polling loop sends status_text payloads to queue during sync.

    Parameters
    ----------
    run_executor : RunExecutor
        RunExecutor instance
    """
    mutagen_mgr = Mock()
    mutagen_mgr.cleanup_orphaned_session = Mock()
    mutagen_mgr.create_sync_session = Mock()
    mutagen_mgr.get_sync_status = Mock(
        side_effect=["Syncing: 10 files", "Syncing: 20 files", "watching"]
    )

    merged_config = {"sync_paths": [{"local": "/local", "remote": "/remote"}]}
    instance_details = {
        "unique_id": "test-id",
        "key_file": "/path/to/key",
        "public_ip": "192.168.1.1",
    }
    update_queue = queue.Queue()

    run_executor._phase_file_sync(
        merged_config=merged_config,
        instance_details=instance_details,
        mutagen_mgr=mutagen_mgr,
        ssh_host="example.com",
        ssh_port=22,
        disable_mutagen=False,
        update_queue=update_queue,
    )

    messages = []
    while not update_queue.empty():
        messages.append(update_queue.get())

    status_messages = [m for m in messages if m["type"] == "mutagen_status"]

    assert len(status_messages) >= 5
    assert status_messages[1]["payload"]["status_text"] == "Syncing: 10 files"
    assert status_messages[2]["payload"]["status_text"] == "Syncing: 20 files"
    assert status_messages[3]["payload"]["status_text"] == "watching"
    assert status_messages[-1]["payload"]["status_text"] == "idle"


def test_phase_file_sync_terminates_when_watching_detected(run_executor):
    """Test polling loop terminates when 'watching' is detected in status.

    Parameters
    ----------
    run_executor : RunExecutor
        RunExecutor instance
    """
    mutagen_mgr = Mock()
    mutagen_mgr.cleanup_orphaned_session = Mock()
    mutagen_mgr.create_sync_session = Mock()
    mutagen_mgr.get_sync_status = Mock(return_value="Syncing, watching for changes")

    merged_config = {"sync_paths": [{"local": "/local", "remote": "/remote"}]}
    instance_details = {
        "unique_id": "test-id",
        "key_file": "/path/to/key",
        "public_ip": "192.168.1.1",
    }
    update_queue = queue.Queue()

    with patch("campers.core.run_executor.logging") as mock_logging:
        run_executor._phase_file_sync(
            merged_config=merged_config,
            instance_details=instance_details,
            mutagen_mgr=mutagen_mgr,
            ssh_host="example.com",
            ssh_port=22,
            disable_mutagen=False,
            update_queue=update_queue,
        )

        info_messages = [call[0][0] for call in mock_logging.info.call_args_list]
        assert any("reached watching state" in msg for msg in info_messages)


def test_phase_file_sync_aborts_on_cleanup_requested(run_executor, cleanup_in_progress_getter):
    """Test polling loop aborts when cleanup is requested.

    Parameters
    ----------
    run_executor : RunExecutor
        RunExecutor instance
    cleanup_in_progress_getter : Mock
        Mock cleanup getter
    """
    mutagen_mgr = Mock()
    mutagen_mgr.cleanup_orphaned_session = Mock()
    mutagen_mgr.create_sync_session = Mock()

    call_count = [0]

    def status_getter_with_cleanup(session_name):
        """Return status but trigger cleanup on third call."""
        call_count[0] += 1
        if call_count[0] >= 2:
            cleanup_in_progress_getter.return_value = True
        return "Syncing: 10 files"

    mutagen_mgr.get_sync_status = Mock(side_effect=status_getter_with_cleanup)

    merged_config = {"sync_paths": [{"local": "/local", "remote": "/remote"}]}
    instance_details = {
        "unique_id": "test-id",
        "key_file": "/path/to/key",
        "public_ip": "192.168.1.1",
    }
    update_queue = queue.Queue()

    with patch("campers.core.run_executor.logging") as mock_logging:
        run_executor._phase_file_sync(
            merged_config=merged_config,
            instance_details=instance_details,
            mutagen_mgr=mutagen_mgr,
            ssh_host="example.com",
            ssh_port=22,
            disable_mutagen=False,
            update_queue=update_queue,
        )

        call_args = [str(call[0][0]) for call in mock_logging.info.call_args_list]
        assert any("Cleanup requested" in msg for msg in call_args), "Should log cleanup request"


def test_phase_file_sync_timeout_warning(run_executor, cleanup_in_progress_getter):
    """Test polling loop logs warning when sync doesn't complete within timeout.

    Parameters
    ----------
    run_executor : RunExecutor
        RunExecutor instance
    cleanup_in_progress_getter : Mock
        Mock cleanup getter
    """
    mutagen_mgr = Mock()
    mutagen_mgr.cleanup_orphaned_session = Mock()
    mutagen_mgr.create_sync_session = Mock()
    mutagen_mgr.get_sync_status = Mock(return_value="Still syncing")

    merged_config = {"sync_paths": [{"local": "/local", "remote": "/remote"}]}
    instance_details = {
        "unique_id": "test-id",
        "key_file": "/path/to/key",
        "public_ip": "192.168.1.1",
    }
    update_queue = queue.Queue()

    with (
        patch("campers.core.run_executor.SYNC_TIMEOUT", 0.1),
        patch("campers.core.run_executor.time.time") as mock_time,
    ):
        start_time = 1000.0
        call_count = [0]

        def mock_time_func():
            call_count[0] += 1
            if call_count[0] <= 5:
                return start_time
            else:
                return start_time + 0.15

        mock_time.side_effect = mock_time_func

        with pytest.raises(RuntimeError) as exc_info:
            run_executor._phase_file_sync(
                merged_config=merged_config,
                instance_details=instance_details,
                mutagen_mgr=mutagen_mgr,
                ssh_host="example.com",
                ssh_port=22,
                disable_mutagen=False,
                update_queue=update_queue,
            )
        assert "Mutagen sync timed out" in str(exc_info.value)
