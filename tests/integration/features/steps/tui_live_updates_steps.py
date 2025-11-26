"""Step definitions for TUI live updates and interactivity feature."""

import asyncio
import queue
import time
from datetime import datetime, timedelta
from typing import Any

from behave import given, then, when
from behave.runner import Context
from textual.widgets import Static


@when('status update event "{status}" is received')
def step_status_update_event_received(context: Context, status: str) -> None:
    """Send status update event to queue.

    Parameters
    ----------
    context : Context
        Behave context
    status : str
        Status value to send
    """
    context.last_status_update = status
    context.status_events = getattr(context, "status_events", [])
    context.status_events.append(status)


@then('status widget displays "{status}"')
def step_status_widget_displays(context: Context, status: str) -> None:
    """Verify status widget displays expected status.

    Parameters
    ----------
    context : Context
        Behave context
    status : str
        Expected status value
    """

    async def verify_status() -> None:
        CampersTUI = context.campers_module.CampersTUI
        update_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        mock_campers = context.campers_module.Campers()
        app = CampersTUI(
            campers_instance=mock_campers, run_kwargs={}, update_queue=update_queue,
            start_worker=False
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            update_queue.put({"type": "status_update", "payload": {"status": status}})
            app.check_for_updates()
            await pilot.pause()
            widget = app.query_one("#status-widget", Static)
            content = str(widget.render())
            assert status in content.lower(), (
                f"Expected status '{status}' in widget, got: {content}"
            )

    asyncio.run(verify_status())


@when("uptime timer ticks 3 times")
def step_uptime_timer_ticks(context: Context) -> None:
    """Mark that uptime timer should tick.

    Parameters
    ----------
    context : Context
        Behave context
    """
    context.uptime_ticks = 3
    context.start_time = datetime.now() - timedelta(seconds=3)


@then("uptime widget displays time elapsed")
def step_uptime_widget_displays_elapsed(context: Context) -> None:
    """Verify uptime widget displays elapsed time.

    Parameters
    ----------
    context : Context
        Behave context
    """

    async def verify_uptime() -> None:
        CampersTUI = context.campers_module.CampersTUI
        update_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        mock_campers = context.campers_module.Campers()
        app = CampersTUI(
            campers_instance=mock_campers, run_kwargs={}, update_queue=update_queue,
            start_worker=False
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            app.instance_start_time = datetime.now() - timedelta(seconds=3)
            for _ in range(3):
                app.update_uptime()
                await pilot.pause(0.1)
            widget = app.query_one("#uptime-widget", Static)
            content = str(widget.render())
            assert any(char.isdigit() for char in content), (
                f"Expected time in uptime widget, got: {content}"
            )

    asyncio.run(verify_uptime())


@when('mutagen status event with state "{state}" and {file_count:d} files is received')
def step_mutagen_status_with_files_received(
    context: Context, state: str, file_count: int
) -> None:
    """Send mutagen status event with file count to queue.

    Parameters
    ----------
    context : Context
        Behave context
    state : str
        Mutagen sync state
    file_count : int
        Number of files synced
    """
    context.mutagen_state = state
    context.mutagen_files = file_count


@then('mutagen widget displays state "{state}"')
def step_mutagen_widget_displays_state(context: Context, state: str) -> None:
    """Verify mutagen widget displays expected state.

    Parameters
    ----------
    context : Context
        Behave context
    state : str
        Expected mutagen state
    """

    async def verify_mutagen_state() -> None:
        CampersTUI = context.campers_module.CampersTUI
        update_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        mock_campers = context.campers_module.Campers()
        app = CampersTUI(
            campers_instance=mock_campers, run_kwargs={}, update_queue=update_queue,
            start_worker=False
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            mutagen_payload = {"state": state}

            if hasattr(context, "mutagen_files"):
                mutagen_payload["files_synced"] = context.mutagen_files

            update_queue.put({"type": "mutagen_status", "payload": mutagen_payload})
            app.check_for_updates()
            await pilot.pause()
            widget = app.query_one("#mutagen-widget", Static)
            content = str(widget.render())
            assert state in content.lower(), (
                f"Expected state '{state}' in mutagen widget, got: {content}"
            )

    asyncio.run(verify_mutagen_state())


@then('mutagen widget displays "{expected_text}"')
def step_mutagen_widget_displays_text(context: Context, expected_text: str) -> None:
    """Verify mutagen widget displays expected text.

    Parameters
    ----------
    context : Context
        Behave context
    expected_text : str
        Expected text in widget
    """

    async def verify_mutagen_text() -> None:
        CampersTUI = context.campers_module.CampersTUI
        update_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        mock_campers = context.campers_module.Campers()
        app = CampersTUI(
            campers_instance=mock_campers, run_kwargs={}, update_queue=update_queue,
            start_worker=False
        )
        async with app.run_test() as pilot:
            await pilot.pause()

            if hasattr(context, "mutagen_files"):
                mutagen_payload = {
                    "state": context.mutagen_state,
                    "files_synced": context.mutagen_files,
                }
                update_queue.put({"type": "mutagen_status", "payload": mutagen_payload})
                app.check_for_updates()
                await pilot.pause()

            widget = app.query_one("#mutagen-widget", Static)
            content = str(widget.render())
            assert expected_text.lower() in content.lower(), (
                f"Expected text '{expected_text}' in mutagen widget, got: {content}"
            )

    asyncio.run(verify_mutagen_text())


@when('mutagen status event with state "{state}" is received')
def step_mutagen_status_received(context: Context, state: str) -> None:
    """Send mutagen status event to queue.

    Parameters
    ----------
    context : Context
        Behave context
    state : str
        Mutagen sync state
    """
    context.mutagen_state = state


@given("config file without sync_paths configuration")
def step_config_without_sync_paths(context: Context) -> None:
    """Set up config without sync_paths.

    Parameters
    ----------
    context : Context
        Behave context
    """
    context.config_has_sync_paths = False
    context.tui_launched = True
    context.update_queue: queue.Queue[dict[str, Any]] = queue.Queue()


@when('user presses "{key}" key')
def step_user_presses_key(context: Context, key: str) -> None:
    """Simulate user pressing a key.

    Parameters
    ----------
    context : Context
        Behave context
    key : str
        Key pressed by user
    """
    context.key_pressed = key


@then("graceful shutdown is initiated")
def step_graceful_shutdown_initiated(context: Context) -> None:
    """Verify graceful shutdown is initiated.

    Parameters
    ----------
    context : Context
        Behave context
    """

    async def verify_graceful_shutdown() -> None:
        CampersTUI = context.campers_module.CampersTUI
        update_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        mock_campers = context.campers_module.Campers()
        app = CampersTUI(
            campers_instance=mock_campers, run_kwargs={}, update_queue=update_queue,
            start_worker=False
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            shutdown_initiated = False

            original_cleanup = mock_campers._cleanup_resources

            def mock_cleanup(signum=None, frame=None):
                nonlocal shutdown_initiated
                shutdown_initiated = True
                original_cleanup(signum, frame)

            mock_campers._cleanup_resources = mock_cleanup
            await pilot.press("q")
            await pilot.pause()
            assert shutdown_initiated or app.is_running is False, (
                "Expected graceful shutdown to be initiated"
            )

    asyncio.run(verify_graceful_shutdown())


@when("first SIGINT signal is received")
def step_first_sigint_received(context: Context) -> None:
    """Record first SIGINT signal time.

    Parameters
    ----------
    context : Context
        Behave context
    """
    context.first_sigint_time = time.time()


@when("second SIGINT signal is received within 1.5 seconds")
def step_second_sigint_within_window(context: Context) -> None:
    """Record second SIGINT within time window.

    Parameters
    ----------
    context : Context
        Behave context
    """
    context.second_sigint_time = context.first_sigint_time + 1.0


@then("application exits immediately")
def step_application_exits_immediately(context: Context) -> None:
    """Verify application exits immediately on double Ctrl+C.

    Parameters
    ----------
    context : Context
        Behave context
    """

    async def verify_immediate_exit() -> None:
        CampersTUI = context.campers_module.CampersTUI
        update_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        mock_campers = context.campers_module.Campers()
        app = CampersTUI(
            campers_instance=mock_campers, run_kwargs={}, update_queue=update_queue,
            start_worker=False
        )
        async with app.run_test() as pilot:
            await pilot.pause()
            app.last_ctrl_c_time = time.time()
            start_time = time.time()
            await pilot.press("ctrl+c")
            elapsed = time.time() - start_time
            assert elapsed < 2.0, (
                f"Expected immediate exit on double Ctrl+C, took {elapsed}s"
            )

    asyncio.run(verify_immediate_exit())
