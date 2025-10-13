"""Textual Pilot step definitions for TUI testing."""

import logging
import os
import queue
import tempfile
import time
from typing import Any

import yaml
from behave import given, then, when
from behave.runner import Context
from textual.css.query import NoMatches
from textual.widgets import Log

from features.steps.utils import run_async_test
from moondock.__main__ import Moondock, MoondockTUI

logger = logging.getLogger(__name__)


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

    context.tui_max_wait = 90
    context.tui_machine_name = machine_name
    context.tui_config_path = context.config_path


def setup_test_environment(config_path: str) -> dict[str, str | None]:
    """Set up environment variables for TUI testing.

    Parameters
    ----------
    config_path : str
        Path to the config file

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
    os.environ["MOONDOCK_TEST_MODE"] = "0"
    os.environ["MOONDOCK_CONFIG"] = config_path

    if original_values["AWS_ENDPOINT_URL"]:
        os.environ["AWS_ENDPOINT_URL"] = original_values["AWS_ENDPOINT_URL"]

    return original_values


def restore_environment(original_values: dict[str, str | None]) -> None:
    """Restore original environment variables.

    Parameters
    ----------
    original_values : dict[str, str | None]
        Dictionary containing original environment variable values
    """
    for key, value in original_values.items():
        if value is not None:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)


async def poll_tui_status(app: MoondockTUI, pilot: Any, max_wait: int) -> None:
    """Poll TUI until status shows 'terminating'.

    Parameters
    ----------
    app : MoondockTUI
        The Moondock TUI application instance
    pilot : Any
        Textual Pilot instance for controlling the app
    max_wait : int
        Maximum time to wait in seconds
    """
    start_time = time.time()
    last_log_time = start_time
    last_status = ""

    while time.time() - start_time < max_wait:
        try:
            status_widget = app.query_one("#status-widget")
            status_text = str(status_widget.render())

            if status_text != last_status:
                logger.info(f"Status changed: {status_text}")
                last_status = status_text

            elapsed = time.time() - last_log_time
            if elapsed > 10:
                logger.info(
                    f"Still waiting for 'terminating' status... (current: {status_text})"
                )
                last_log_time = time.time()

            if "terminating" in status_text.lower():
                logger.info("Found 'terminating' status, pausing for 3 seconds")
                await pilot.pause(3.0)
                break
        except NoMatches:
            logger.debug("Status widget not found")
        except Exception as e:
            logger.debug(f"Error querying status widget: {e}")

        await pilot.pause(0.5)

    elapsed_total = time.time() - start_time
    logger.info(
        f"poll_tui_status completed after {elapsed_total:.1f}s (max_wait={max_wait}s)"
    )


async def poll_for_log_message(
    app: MoondockTUI, pilot: Any, expected_message: str, max_wait: int
) -> None:
    """Poll TUI logs until expected message appears.

    Parameters
    ----------
    app : MoondockTUI
        The Moondock TUI application instance
    pilot : Any
        Textual Pilot instance for controlling the app
    expected_message : str
        Log message to wait for
    max_wait : int
        Maximum time to wait in seconds
    """
    start_time = time.time()
    found = False

    while time.time() - start_time < max_wait:
        try:
            log_widget = app.query_one(Log)
            log_lines = [str(line) for line in log_widget.lines]
            log_text = "\n".join(log_lines)

            if expected_message in log_text:
                logging.info(f"Found expected log message: {expected_message}")
                found = True
                break
        except NoMatches:
            pass
        except Exception:
            pass

        await pilot.pause(0.5)

    if found:
        await pilot.pause(1.0)


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
    machine_name: str, config_path: str, max_wait: int = 90
) -> dict[str, Any]:
    """Run the TUI test asynchronously.

    Parameters
    ----------
    machine_name : str
        Name of the machine to run
    config_path : str
        Path to the config file
    max_wait : int
        Maximum time to wait for status change in seconds

    Returns
    -------
    dict[str, Any]
        Dictionary containing TUI state after execution
    """

    async def run_tui_test() -> dict[str, Any]:
        original_values = setup_test_environment(config_path)

        try:
            moondock = Moondock()
            update_queue: queue.Queue = queue.Queue(maxsize=100)

            app = MoondockTUI(
                moondock_instance=moondock,
                run_kwargs={"machine_name": machine_name, "json_output": False},
                update_queue=update_queue,
            )

            async with app.run_test() as pilot:
                await pilot.pause()

                await poll_tui_status(app, pilot, max_wait)
                await poll_for_log_message(
                    app, pilot, "Command completed successfully", max_wait
                )
                await poll_for_log_message(
                    app, pilot, "Cleanup completed successfully", max_wait
                )

                log_lines, log_text = extract_log_lines(app)
                status_widget = app.query_one("#status-widget")

                return {
                    "status": str(status_widget.render()),
                    "log_lines": log_lines,
                    "log_text": log_text,
                }
        finally:
            restore_environment(original_values)

    return run_async_test(run_tui_test)


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
    if not hasattr(context, "tui_machine_name"):
        raise AssertionError(
            "No TUI machine name found. Run the TUI simulation step first."
        )

    if not hasattr(context, "tui_config_path"):
        raise AssertionError(
            "No TUI config path found. Run the TUI simulation step first."
        )

    result = run_tui_test_with_machine(
        context.tui_machine_name, context.tui_config_path, timeout
    )
    context.tui_result = result
    logger.info(f"TUI result: {result}")

    status = result.get("status", "")
    log_text = result.get("log_text", "")

    if expected_status.lower() not in status.lower():
        raise AssertionError(
            f"Expected status to contain '{expected_status}', but got: {status}\n\nTUI Log:\n{log_text}"
        )

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
        raise AssertionError("No TUI result found. Run the TUI simulation step first.")

    log_text = context.tui_result.get("log_text", "")

    if expected_text not in log_text:
        raise AssertionError(
            f"Expected log to contain '{expected_text}', but log was:\n{log_text}"
        )

    logger.info(f"Log contains: {expected_text}")
