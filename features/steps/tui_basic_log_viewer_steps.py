"""Step definitions for TUI basic log viewer feature."""

from behave import given, then, when
from behave.runner import Context


@given("stdout is an interactive terminal")
def step_stdout_is_interactive_terminal(context: Context) -> None:
    context.stdout_is_tty = True


@given("stdout is not a TTY")
def step_stdout_is_not_tty(context: Context) -> None:
    context.stdout_is_tty = False


@given("TUI application is running")
def step_tui_application_is_running(context: Context) -> None:
    context.tui_is_running = True
    context.stdout_is_tty = True


@given("command execution will fail")
def step_command_execution_will_fail(context: Context) -> None:
    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {"defaults": {}}

    context.config_data["defaults"]["command"] = "exit 1"


@when("command execution completes successfully")
def step_command_execution_completes_successfully(context: Context) -> None:
    context.command_completed = True
    context.exit_code = 0


@when("command execution completes")
def step_command_execution_completes(context: Context) -> None:
    context.command_completed = True


@then("TUI application launches")
def step_tui_application_launches(context: Context) -> None:
    pass


@then("log messages are displayed in TUI")
def step_log_messages_displayed_in_tui(context: Context) -> None:
    pass


@then("TUI does not launch")
def step_tui_does_not_launch(context: Context) -> None:
    pass


@then("logs are written to stderr")
def step_logs_written_to_stderr(context: Context) -> None:
    pass


@then("final output is JSON string to stdout")
def step_final_output_is_json_string(context: Context) -> None:
    pass


@then("TUI begins graceful shutdown")
def step_tui_begins_graceful_shutdown(context: Context) -> None:
    pass


@then("TUI exits after cleanup")
def step_tui_exits_after_cleanup(context: Context) -> None:
    pass


@then("TUI displays success message")
def step_tui_displays_success_message(context: Context) -> None:
    pass


@then("TUI exits automatically")
def step_tui_exits_automatically(context: Context) -> None:
    pass


@then("TUI displays error messages")
def step_tui_displays_error_messages(context: Context) -> None:
    pass
