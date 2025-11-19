"""Textual Pilot step definitions for TUI testing."""

import asyncio
import json
import logging
import os
import queue
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from behave import given, then, when
from behave.runner import Context
from textual.css.query import NoMatches
from textual.widgets import Log

from tests.integration.features.steps.utils import run_async_test
from tests.harness.utils.system_snapshot import gather_system_snapshot
from moondock.__main__ import Moondock, MoondockTUI

logger = logging.getLogger(__name__)


def get_tui_update_queue(context: Context | None = None) -> queue.Queue | None:
    """Get the TUI update queue for monitor thread communication.

    Accesses the TUI update queue from PilotExtension if available,
    otherwise returns None. This replaces the global _tui_update_queue.

    Parameters
    ----------
    context : Context | None
        Behave context object containing harness reference

    Returns
    -------
    queue.Queue | None
        The TUI update queue if TUI test is running, None otherwise
    """
    if not context or not hasattr(context, "harness"):
        return None

    pilot_ext = context.harness.extensions.pilot
    if not pilot_ext or not pilot_ext.tui_handle:
        return None

    return pilot_ext.tui_handle.event_queue


@given("a config file with defaults section")
def step_config_file_with_defaults_section(context: Context) -> None:
    """Create a config file with a defaults section.

    Parameters
    ----------
    context : Context
        Behave context object
    """
    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
                "ports": [],
            },
            "machines": {},
        }


@given('a config file with machine "{machine_name}" defined')
def step_config_file_with_machine(context: Context, machine_name: str) -> None:
    """Create a config file with a machine definition.

    Parameters
    ----------
    context : Context
        Behave context object
    machine_name : str
        Name of the machine to define
    """
    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {
            "defaults": {
                "region": "us-east-1",
                "instance_type": "t3.medium",
                "disk_size": 50,
                "ports": [],
            },
            "machines": {},
        }

    if "machines" not in context.config_data:
        context.config_data["machines"] = {}

    if machine_name not in context.config_data["machines"]:
        context.config_data["machines"][machine_name] = {}

    context.machine_name = machine_name


@when("I launch the Moondock TUI with the config file")
def step_launch_tui_with_config(context: Context) -> None:
    """Launch the Moondock TUI with the config file.

    Parameters
    ----------
    context : Context
        Behave context object
    """
    temp_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, dir=context.tmp_dir
    )
    yaml.dump(context.config_data, temp_file)
    temp_file.close()
    context.temp_config_file = temp_file.name
    context.config_path = temp_file.name
    logger.info(f"Created config file: {context.config_path}")


@when('I simulate running the "{machine_name}" in the TUI')
def step_simulate_running_machine_in_tui(context: Context, machine_name: str) -> None:
    """Simulate running a machine in the TUI using Textual Pilot.

    Parameters
    ----------
    context : Context
        Behave context object
    machine_name : str
        Name of the machine to run
    """
    if not hasattr(context, "config_path"):
        raise AssertionError(
            "No config path found. Run 'I launch the Moondock TUI with the config file' step first."
        )

    max_wait = derive_timeout_from_scenario(context)
    logger.info(f"=== STARTING TUI TEST FOR MACHINE: {machine_name} ===")
    logger.info(f"TUI timeout derived from scenario: {max_wait} seconds")
    result = run_tui_test_with_machine(
        machine_name, context.config_path, max_wait, context
    )
    context.tui_result = result

    if hasattr(context, "harness") and hasattr(context.harness, "current_instance_id"):
        try:
            instance_id = context.harness.current_instance_id()
        except Exception:  # pragma: no cover - defensive
            instance_id = None
        if instance_id:
            context.instance_id = instance_id

    logger.info(f"=== TUI TEST COMPLETED FOR MACHINE: {machine_name} ===")
    logger.info(f"TUI result status: {result.get('status', 'UNKNOWN')}")
    logger.info(f"TUI log length: {len(result.get('log_text', ''))} characters")

    logger.info(
        "NOTE: HTTP servers are started by LocalStackHarness before the TUI launches. "
        "Avoid starting HTTP servers in TUI steps because tunnels are managed by the harness."
    )


def derive_timeout_from_scenario(context: Context) -> int:
    """Extract timeout value from scenario's @timeout_X tag.

    Derives the TUI polling timeout from the scenario's @timeout_X tag.
    This ensures the timeout aligns with the scenario's expected duration.

    Parameters
    ----------
    context : Context
        Behave context object containing scenario information

    Returns
    -------
    int
        Timeout in seconds, defaults to 90 if no tag present
    """
    if hasattr(context, "scenario") and context.scenario.tags:
        for tag in context.scenario.tags:
            if tag.startswith("timeout_"):
                try:
                    return int(tag.split("_")[1])
                except (ValueError, IndexError):
                    pass
    return 90


def setup_test_environment(
    config_path: str, behave_context: Context | None = None
) -> dict[str, str | None]:
    """Set up environment variables for TUI testing.

    Parameters
    ----------
    config_path : str
        Path to the config file
    behave_context : Context | None
        Optional Behave context for harness access

    Returns
    -------
    dict[str, str | None]
        Dictionary containing original environment variable values
    """
    original_values = {
        "MOONDOCK_TEST_MODE": os.environ.get("MOONDOCK_TEST_MODE"),
        "MOONDOCK_CONFIG": os.environ.get("MOONDOCK_CONFIG"),
        "AWS_ENDPOINT_URL": os.environ.get("AWS_ENDPOINT_URL"),
    }

    behave_context.harness.services.configuration_env.set("MOONDOCK_TEST_MODE", "0")
    behave_context.harness.services.configuration_env.set(
        "MOONDOCK_CONFIG", config_path
    )
    if original_values["AWS_ENDPOINT_URL"]:
        behave_context.harness.services.configuration_env.set(
            "AWS_ENDPOINT_URL", original_values["AWS_ENDPOINT_URL"]
        )

    return original_values


def restore_environment(
    original_values: dict[str, str | None], behave_context: Context | None = None
) -> None:
    """Restore original environment variables.

    Parameters
    ----------
    original_values : dict[str, str | None]
        Dictionary containing original environment variable values
    behave_context : Context | None
        Optional Behave context for harness access
    """
    for key, value in original_values.items():
        if value is not None:
            behave_context.harness.services.configuration_env.set(key, value)
        else:
            behave_context.harness.services.configuration_env.delete(key)


async def poll_tui_with_unified_timeout(
    app: MoondockTUI, pilot: Any, max_wait: int, behave_context: Context | None = None
) -> None:
    """Poll TUI with unified timeout budget for all conditions.

    All conditions share a single timeout budget instead of independent timeouts.
    This prevents timeout accumulation where sequential polling operations could
    exceed the scenario timeout limit. When error status is detected, applies
    extended post-error handling with additional polling iterations.

    Parameters
    ----------
    app : MoondockTUI
        The Moondock TUI application instance
    pilot : Any
        Textual Pilot instance for controlling the app
    max_wait : int
        Maximum time to wait for all conditions in seconds
    """
    start_time = time.time()
    last_log_time = start_time
    last_status = ""

    terminating_found = False
    command_completed_found = False
    cleanup_completed_found = False
    error_found = False
    error_detection_time = None

    while time.time() - start_time < max_wait:
        if (
            behave_context is not None
            and getattr(behave_context, "monitor_error", None) is not None
        ):
            error_message = getattr(behave_context, "monitor_error")
            logger.error("Monitor reported error during TUI polling: %s", error_message)
            raise AssertionError(
                f"Monitor error detected while waiting for TUI: {error_message}"
            )

        try:
            status_widget = app.query_one("#status-widget")
            status_text = str(status_widget.render())

            if status_text != last_status:
                logger.info(f"Status changed: {status_text}")
                last_status = status_text

            elapsed = time.time() - last_log_time
            if elapsed > 10:
                logger.info(
                    f"Still polling (terminating: {terminating_found}, "
                    f"command: {command_completed_found}, "
                    f"cleanup: {cleanup_completed_found}, "
                    f"error: {error_found})"
                )
                last_log_time = time.time()

            if "terminating" in status_text.lower() or "stopping" in status_text.lower():
                if not terminating_found:
                    logger.info("Found 'terminating' or 'stopping' status")
                terminating_found = True

            if "error" in status_text.lower():
                if not error_found:
                    logger.info("Found 'error' status")
                    error_found = True
                    error_detection_time = time.time()
        except NoMatches:
            logger.debug("Status widget not found")
        except Exception as e:
            logger.debug(f"Error querying status widget: {e}")

        try:
            log_widget = app.query_one(Log)
            log_lines = [str(line) for line in log_widget.lines]
            log_text = "\n".join(log_lines)

            if "Command completed" in log_text:
                if not command_completed_found:
                    logger.info("Found command completion message in logs")
                command_completed_found = True

            if "Cleanup completed successfully" in log_text:
                if not cleanup_completed_found:
                    logger.info("Found 'Cleanup completed successfully' in logs")
                cleanup_completed_found = True
        except NoMatches:
            pass
        except Exception:
            pass

        if error_found:
            if error_detection_time and time.time() - error_detection_time > 10:
                logger.info(
                    "Extended post-error pause completed - performing final polling iterations"
                )
                for iteration in range(5):
                    logger.info(
                        f"Final polling iteration {iteration + 1}/5 after error detection"
                    )
                    await pilot.pause(1.0)
                    try:
                        status_widget = app.query_one("#status-widget")
                        status_text = str(status_widget.render())
                        if status_text != last_status:
                            logger.info(
                                f"Status updated during final iteration: {status_text}"
                            )
                            last_status = status_text
                    except Exception:
                        pass
                logger.info(
                    "Error status detected with extended post-error handling - breaking from polling"
                )
                break
            elif not error_detection_time:
                await pilot.pause(0.5)
                continue

        if terminating_found and command_completed_found and cleanup_completed_found:
            logger.info("All TUI conditions met")
            await pilot.pause(3.0)
            break

        await pilot.pause(0.5)

    elapsed = time.time() - start_time
    logger.info(
        f"TUI polling completed after {elapsed:.1f}s "
        f"(terminating: {terminating_found}, "
        f"command: {command_completed_found}, "
        f"cleanup: {cleanup_completed_found}, "
        f"error: {error_found})"
    )


def extract_log_lines(app: MoondockTUI) -> tuple[list[str], str]:
    """Extract log content from TUI.

    Parameters
    ----------
    app : MoondockTUI
        The Moondock TUI application instance

    Returns
    -------
    tuple[list[str], str]
        Tuple containing list of log lines and concatenated log text
    """
    try:
        log_widget = app.query_one(Log)
        log_lines = [str(line) for line in log_widget.lines]
    except NoMatches:
        log_lines = []
    except Exception:
        log_lines = []

    return log_lines, "\n".join(log_lines)


def run_tui_test_with_machine(
    machine_name: str,
    config_path: str,
    max_wait: int = 90,
    behave_context: Context | None = None,
) -> dict[str, Any]:
    """Run the TUI test asynchronously with unified timeout budget.

    Uses a single unified timeout budget for all polling operations to prevent
    timeout accumulation that could exceed scenario limits. Applies Mutagen
    mocking for LocalStack scenarios to avoid real AWS connections.

    Parameters
    ----------
    machine_name : str
        Name of the machine to run
    config_path : str
        Path to the config file
    max_wait : int
        Maximum time to wait for all conditions in seconds
    behave_context : Context | None
        Optional Behave context containing test fixtures for Mutagen mocking

    Returns
    -------
    dict[str, Any]
        Dictionary containing TUI state after execution
    """
    timeout_triggered = threading.Event()
    test_completed = threading.Event()
    loop_holder: dict[str, asyncio.AbstractEventLoop] = {}
    app_holder: dict[str, MoondockTUI] = {}

    def timeout_handler():
        timeout_triggered.set()
        logger.error(
            f"[TIMEOUT-ENFORCER] Test exceeded {max_wait}s timeout - marking as failed"
        )
        snapshot = gather_system_snapshot(include_thread_stacks=True)
        recorded = False
        harness = None
        if behave_context is not None:
            harness = getattr(behave_context, "harness", None)
        if harness is not None and getattr(harness, "services", None) is not None:
            try:
                harness.services.diagnostics.record(
                    "system-snapshot", "tui-timeout-handler", snapshot
                )
                recorded = True
            except Exception:  # pragma: no cover - diagnostics best effort
                logger.debug(
                    "Failed to record timeout snapshot via harness diagnostics",
                    exc_info=True,
                )
        if not recorded:
            try:
                fallback_dir = (
                    Path.cwd() / "tmp" / "behave" / "_diagnostics" / "_tui-timeouts"
                )
                fallback_dir.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
                fallback_path = fallback_dir / f"{timestamp}.json"
                fallback_path.write_text(
                    json.dumps(
                        {"description": "tui-timeout-handler", "snapshot": snapshot},
                        indent=2,
                    )
                )
            except Exception:  # pragma: no cover - best effort
                logger.debug("Failed to persist timeout snapshot", exc_info=True)
        loop = loop_holder.get("loop")
        app = app_holder.get("app")

        if loop and app:
            loop.call_soon_threadsafe(app.exit)

    timer = threading.Timer(max_wait, timeout_handler)

    async def run_tui_test() -> dict[str, Any]:
        logger.info("=== TUI TEST START === (machine: %s)", machine_name)
        logger.info(f"[TIMEOUT-ENFORCER] Starting test with {max_wait}s timeout")
        loop_holder["loop"] = asyncio.get_running_loop()
        timer.start()

        original_values = setup_test_environment(config_path, behave_context)

        try:
            from contextlib import asynccontextmanager

            from tests.integration.features.steps.mutagen_mocking import mutagen_mocked

            @asynccontextmanager
            async def mocking_context_manager():
                if behave_context is not None:
                    with mutagen_mocked(behave_context):
                        yield
                else:
                    logger.warning(
                        "No Behave context provided for Mutagen mocking - "
                        "real Mutagen will be used"
                    )
                    yield

            try:
                async with mocking_context_manager():
                    moondock = Moondock()
                    update_queue: queue.Queue = queue.Queue(maxsize=100)

                    app = MoondockTUI(
                        moondock_instance=moondock,
                        run_kwargs={"machine_name": machine_name, "json_output": False},
                        update_queue=update_queue,
                    )
                    app_holder["app"] = app

                    try:
                        async with asyncio.timeout(max_wait):
                            async with app.run_test() as pilot:
                                await pilot.pause()

                                await poll_tui_with_unified_timeout(
                                    app, pilot, max_wait, behave_context
                                )

                                if timeout_triggered.is_set():
                                    logger.error(
                                        "[TIMEOUT-CHECK] Timeout triggered during test execution"
                                    )
                                    raise AssertionError(
                                        f"Test exceeded {max_wait}s timeout during execution"
                                    )

                                await pilot.pause(3.0)
                                log_lines, log_text = extract_log_lines(app)
                                status_widget = app.query_one("#status-widget")
                                final_status = str(status_widget.render())

                                logger.info(
                                    "=== TUI TEST END === (machine: %s, status: %s, log_length: %d)",
                                    machine_name,
                                    final_status,
                                    len(log_text),
                                )

                                return {
                                    "status": final_status,
                                    "log_lines": log_lines,
                                    "log_text": log_text,
                                }
                    except asyncio.TimeoutError:
                        raise AssertionError(
                            f"TUI test exceeded {max_wait}s timeout. "
                            f"Check logs for container boot delays or SSH issues."
                        )
            except Exception as e:
                logger.error(f"Exception during TUI result extraction: {e}")
                log_lines, log_text = (
                    extract_log_lines(app) if "app" in locals() else ([], "")
                )
                exit_code = (
                    getattr(app, "worker_exit_code", None)
                    if "app" in locals()
                    else None
                )

                return {
                    "status": "extraction_failed",
                    "error": str(e),
                    "log_lines": log_lines,
                    "log_text": log_text,
                    "exit_code": exit_code,
                }
        finally:
            test_completed.set()
            restore_environment(original_values, behave_context)
            app_holder.pop("app", None)
            loop_holder.pop("loop", None)

    async def guarded_run() -> dict[str, Any]:
        return await asyncio.wait_for(run_tui_test(), timeout=max_wait + 30)

    try:
        test_result = run_async_test(guarded_run)

        if timeout_triggered.is_set():
            logger.error(
                f"[TIMEOUT-ENFORCER] Test exceeded {max_wait}s timeout - raising AssertionError"
            )
            raise AssertionError(
                f"TUI test exceeded {max_wait}s timeout. "
                f"Check logs for container boot delays or SSH issues. "
                f"Test may still be running in background."
            )

        return test_result
    except asyncio.TimeoutError as exc:
        timeout_triggered.set()
        logger.error(
            f"[TIMEOUT-ENFORCER] wait_for exceeded {max_wait + 30}s - raising AssertionError"
        )
        raise AssertionError(
            f"TUI test exceeded {max_wait}s timeout. "
            f"Check logs for container boot delays or SSH issues. "
            "Test may still be running in background."
        ) from exc

    finally:
        timer.cancel()

        if not test_completed.is_set():
            logger.warning(
                "[TIMEOUT-ENFORCER] Test incomplete - worker may still be running"
            )


@then('the TUI status widget shows "{expected_status}" within {timeout:d} seconds')
def step_tui_status_shows(context: Context, expected_status: str, timeout: int) -> None:
    """Verify that the TUI status widget shows expected text.

    Parameters
    ----------
    context : Context
        Behave context object
    expected_status : str
        Expected status text
    timeout : int
        Timeout in seconds for waiting
    """
    if not hasattr(context, "tui_result"):
        raise AssertionError(
            "No TUI result found. The TUI simulation step must run first and complete successfully."
        )

    result = context.tui_result
    status = result.get("status", "")
    log_text = result.get("log_text", "")

    status_in_logs = f"Status changed: {expected_status}" in log_text
    status_in_widget = expected_status.lower() in status.lower()

    if not (status_in_logs or status_in_widget):
        raise AssertionError(
            f"Expected status '{expected_status}' not found.\n"
            f"Final widget status: {status}\n"
            f"Checked logs for: 'Status changed: {expected_status}'\n\n"
            f"TUI Log:\n{log_text}"
        )

    if status_in_logs:
        logger.info(f"Status '{expected_status}' found in logs")
    else:
        logger.info(f"Status widget shows: {status}")


@then('the TUI log panel contains "{expected_text}"')
def step_tui_log_contains(context: Context, expected_text: str) -> None:
    """Verify that the TUI log panel contains expected text.

    Parameters
    ----------
    context : Context
        Behave context object
    expected_text : str
        Expected text in log panel
    """
    if not hasattr(context, "tui_result"):
        raise AssertionError(
            "No TUI result found. The TUI simulation step must run first and complete successfully."
        )

    log_text = context.tui_result.get("log_text", "")

    if expected_text not in log_text:
        raise AssertionError(
            f"Expected log to contain '{expected_text}', but log was:\n{log_text}"
        )

    logger.info(f"Log contains: {expected_text}")


@then('the TUI log panel does not contain "{text}"')
def step_tui_log_does_not_contain(context: Context, text: str) -> None:
    """Verify text is NOT in TUI log panel.

    Parameters
    ----------
    context : Context
        Behave context object
    text : str
        Text that should NOT be in log panel
    """
    if not hasattr(context, "tui_result"):
        raise AssertionError(
            "No TUI result found. The TUI simulation step must run first and complete successfully."
        )

    log_text = context.tui_result.get("log_text", "")

    if text in log_text:
        raise AssertionError(
            f"Found '{text}' in log (should not be present):\n{log_text}"
        )

    logger.info(f"Verified log does not contain: {text}")
