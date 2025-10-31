"""Step definitions for setup command feature."""

import os
import subprocess
from pathlib import Path

from behave import given, then
from behave.runner import Context


@given('"moondock setup" completed successfully')
def step_setup_completed_successfully(context: Context) -> None:
    """Run moondock setup successfully.

    Parameters
    ----------
    context : Context
        Behave context
    """
    project_root = Path(__file__).parent.parent.parent
    moondock_script = project_root / "moondock" / "__main__.py"

    env = os.environ.copy()

    subprocess.run(
        ["uv", "run", "python", str(moondock_script), "setup"],
        env=env,
        capture_output=True,
        text=True,
        input="n\n",
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
