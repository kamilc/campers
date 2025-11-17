"""Step definitions for setup command feature."""

from behave import given, then
from behave.runner import Context

from tests.integration.features.steps.common_steps import execute_command_direct


@given('"moondock setup" completed successfully')
def step_setup_completed_successfully(context: Context) -> None:
    """Run moondock setup successfully.

    Parameters
    ----------
    context : Context
        Behave context
    """
    if not hasattr(context, "patched_ec2_client"):
        raise AssertionError(
            '"moondock setup" precondition requires patched_ec2_client'
        )

    context.setup_user_input = "n"
    execute_command_direct(context, "setup")

    if getattr(context, "exit_code", 0) != 0:
        raise AssertionError(
            f'Expected "moondock setup" to succeed, exit code {context.exit_code}'
        )

    context.initial_vpc_count = len(
        context.patched_ec2_client.describe_vpcs().get("Vpcs", [])
    )


@then('VPC count in "{region}" is unchanged')
def step_vpc_count_unchanged(context: Context, region: str) -> None:
    """Verify VPC count is unchanged.

    Parameters
    ----------
    context : Context
        Behave context
    region : str
        AWS region
    """
    current_count = len(context.patched_ec2_client.describe_vpcs().get("Vpcs", []))

    assert current_count == context.initial_vpc_count, (
        f"VPC count changed from {context.initial_vpc_count} to {current_count}"
    )
