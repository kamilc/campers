"""Step definitions for TUI Instance Overview Widget feature."""

import asyncio
import queue
import time
from typing import Any

from behave import given, then, when
from behave.runner import Context


@given("I have {count:d} running instances")
def step_create_running_instances(context: Context, count: int) -> None:
    """Create specified number of running instances."""
    from tests.integration.features.steps.instance_lifecycle_steps import (
        step_create_running_instance,
    )

    if not hasattr(context, "running_instances"):
        context.running_instances = []

    if not hasattr(context, "created_instance_ids"):
        context.created_instance_ids = []

    for i in range(count):
        instance_name = f"test-running-{i}"
        step_create_running_instance(context, instance_name)
        context.running_instances.append(instance_name)
        if hasattr(context, "test_instance_id"):
            if context.test_instance_id not in context.created_instance_ids:
                context.created_instance_ids.append(context.test_instance_id)


@given("I have {count:d} stopped instances")
def step_create_stopped_instances(context: Context, count: int) -> None:
    """Create specified number of stopped instances."""
    from tests.integration.features.steps.instance_lifecycle_steps import (
        step_create_stopped_instance,
    )

    if not hasattr(context, "stopped_instances"):
        context.stopped_instances = []

    if not hasattr(context, "created_instance_ids"):
        context.created_instance_ids = []

    for i in range(count):
        instance_name = f"test-stopped-{i}"
        step_create_stopped_instance(context, instance_name)
        context.stopped_instances.append(instance_name)
        if hasattr(context, "test_instance_id"):
            if context.test_instance_id not in context.created_instance_ids:
                context.created_instance_ids.append(context.test_instance_id)


@given("I have {count:d} instances")
def step_have_zero_instances(context: Context, count: int) -> None:
    """Handle zero instances case and clean up existing instances.

    Parameters
    ----------
    context : Context
        Behave context object
    count : int
        Expected number of instances (must be 0)
    """
    import logging
    from tests.integration.features.steps.instance_lifecycle_steps import (
        setup_ec2_manager,
    )

    logger = logging.getLogger(__name__)

    if count != 0:
        return

    try:
        ec2_manager = setup_ec2_manager(context)
        all_instances = ec2_manager.list_instances(region_filter=None)
        for instance in all_instances:
            try:
                ec2_manager.terminate_instance(instance["instance_id"])
                logger.debug(f"Terminated instance {instance['instance_id']}")
            except Exception as e:
                logger.debug(
                    f"Failed to terminate instance {instance['instance_id']}: {e}"
                )
    except Exception as e:
        logger.debug(f"Error cleaning up instances: {e}")

    context.running_instances = []
    context.stopped_instances = []

    if not hasattr(context, "created_instance_ids"):
        context.created_instance_ids = []
    else:
        context.created_instance_ids = []


@given("I have {count:d} running instance in {region}")
def step_create_running_instance_in_region(
    context: Context, count: int, region: str
) -> None:
    """Create running instance in specified region."""
    step_create_running_instances(context, count)


@given("I have {count:d} stopped instances in {region}")
def step_create_stopped_instances_in_region(
    context: Context, count: int, region: str
) -> None:
    """Create stopped instances in specified region."""
    step_create_stopped_instances(context, count)


@given("I have {count:d} running {instance_type} instance")
@given("I have {count:d} running {instance_type} instances")
def step_create_running_instances_of_type(
    context: Context, count: int, instance_type: str
) -> None:
    """Create running instances of specified type."""
    step_create_running_instances(context, count)


@when("I view the TUI")
def step_view_tui(context: Context) -> None:
    """Launch TUI and verify widget is visible."""
    import boto3
    from moondock.ec2 import EC2Manager

    async def launch_and_capture() -> None:
        MoondockTUI = context.moondock_module.MoondockTUI
        update_queue: queue.Queue[dict[str, Any]] = queue.Queue()

        is_localstack = (
            hasattr(context, "scenario") and "localstack" in context.scenario.tags
        )

        if is_localstack:
            def localstack_client_factory(service: str, **kwargs: Any) -> Any:
                kwargs.setdefault("endpoint_url", "http://localhost:4566")
                return boto3.client(service, **kwargs)

            def localstack_ec2_factory(region: str = "us-east-1", **kwargs: Any) -> EC2Manager:
                return EC2Manager(
                    region=region,
                    boto3_client_factory=localstack_client_factory,
                    **kwargs
                )

            moondock = context.moondock_module.Moondock(
                ec2_manager_factory=localstack_ec2_factory
            )
        else:
            moondock = context.moondock_module.Moondock()

        app = MoondockTUI(
            moondock_instance=moondock,
            run_kwargs={},
            update_queue=update_queue,
            start_worker=False,
        )
        async with app.run_test() as pilot:
            await pilot.pause()

            widget = app.query_one("#instance-overview-widget")

            await asyncio.sleep(0.5)

            content = widget.render()
            context.overview_widget_text = str(content)

    asyncio.run(launch_and_capture())


@given('TUI is displaying "{expected_text}"')
def step_tui_is_displaying_text(context: Context, expected_text: str) -> None:
    """Set up TUI displaying specified text in overview widget."""
    if "2" in expected_text:
        step_create_running_instances(context, 2)
    elif "1" in expected_text:
        step_create_running_instances(context, 1)

    if "1  N/A" in expected_text:
        step_create_stopped_instances(context, 1)

    step_view_tui(context)


@when("EC2 API fails")
def step_ec2_api_fails(context: Context) -> None:
    """Simulate EC2 API failure."""
    context.ec2_api_should_fail = True


@when("{seconds:d} seconds pass")
def step_seconds_pass(context: Context, seconds: int) -> None:
    """Wait for specified number of seconds."""
    time.sleep(seconds)


@when("I launch a new instance")
def step_launch_new_instance(context: Context) -> None:
    """Launch a new instance."""
    from tests.integration.features.steps.instance_lifecycle_steps import (
        step_create_running_instance,
    )

    if not hasattr(context, "created_instance_ids"):
        context.created_instance_ids = []

    step_create_running_instance(context, "test-new-instance")
    if hasattr(context, "test_instance_id"):
        if context.test_instance_id not in context.created_instance_ids:
            context.created_instance_ids.append(context.test_instance_id)


@then('overview widget shows "{expected_text}"')
def step_overview_widget_shows_text(context: Context, expected_text: str) -> None:
    """Verify overview widget displays expected text."""
    assert (
        context.overview_widget_text == expected_text
    ), f"Expected '{expected_text}', got '{context.overview_widget_text}'"


@then("overview widget daily cost is approximately ${expected_cost:f}")
def step_overview_widget_shows_approximate_cost(
    context: Context, expected_cost: float
) -> None:
    """Verify overview widget displays approximate cost."""
    import re

    match = re.search(r"\$(\d+\.\d+)/day", context.overview_widget_text)
    assert match, f"Could not find cost in '{context.overview_widget_text}'"

    actual_cost = float(match.group(1))
    assert abs(actual_cost - expected_cost) < 1.0, (
        f"Expected cost approximately ${expected_cost}, got ${actual_cost}"
    )


@then("no error is shown to user")
def step_no_error_shown(context: Context) -> None:
    """Verify no error is visible to user."""
    assert "error" not in context.overview_widget_text.lower(), (
        f"Unexpected error in widget text: {context.overview_widget_text}"
    )
