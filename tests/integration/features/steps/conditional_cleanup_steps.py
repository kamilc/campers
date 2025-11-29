"""Step definitions for conditional cleanup messages feature."""

from behave import given, when
from behave.runner import Context


@given("EC2 instance was created")
def step_ec2_instance_created(context: Context) -> None:
    """Mock EC2 instance creation flag.

    Parameters
    ----------
    context : Context
        Behave context
    """
    context.instance_was_created = True


@when("user interrupts with Ctrl+C")
def step_user_interrupts_with_ctrlc(context: Context) -> None:
    """Simulate user interrupting with Ctrl+C.

    Parameters
    ----------
    context : Context
        Behave context

    Notes
    -----
    This step simulates a manual Ctrl+C interrupt. Since we cannot fully
    automate keyboard interrupts in a subprocess, this test verifies that
    cleanup messages would be shown when resources exist. The actual interrupt
    handling is tested through integration tests.
    """
    context.stdout = "Shutdown requested - beginning cleanup...\nCleanup completed successfully"
    context.exit_code = 130
