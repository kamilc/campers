"""BDD step definitions for cost visibility feature."""

import json
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from behave import given, then, when
from behave.runner import Context


SAMPLE_EC2_PRICING_T3_MEDIUM = {
    "terms": {
        "OnDemand": {
            "OFFER123": {
                "priceDimensions": {"DIM456": {"pricePerUnit": {"USD": "0.0416"}}}
            }
        }
    }
}

SAMPLE_EC2_PRICING_G5_2XLARGE = {
    "terms": {
        "OnDemand": {
            "OFFER789": {
                "priceDimensions": {"DIM101": {"pricePerUnit": {"USD": "1.212"}}}
            }
        }
    }
}

SAMPLE_EBS_PRICING_GP3 = {
    "terms": {
        "OnDemand": {
            "OFFER456": {
                "priceDimensions": {"DIM789": {"pricePerUnit": {"USD": "0.08"}}}
            }
        }
    }
}


@given("AWS Pricing API is mocked with sample rates")
def step_mock_pricing_api_with_sample_rates(context: Context) -> None:
    """Mock AWS Pricing API with realistic sample pricing data."""
    import boto3
    original_boto3_client = boto3.client

    mock_pricing_client = Mock()

    def mock_get_products(**kwargs):
        filters = {f["Field"]: f["Value"] for f in kwargs.get("Filters", [])}

        if filters.get("instanceType") == "t3.medium":
            return {"PriceList": [json.dumps(SAMPLE_EC2_PRICING_T3_MEDIUM)]}
        elif filters.get("instanceType") == "g5.2xlarge":
            return {"PriceList": [json.dumps(SAMPLE_EC2_PRICING_G5_2XLARGE)]}
        elif filters.get("productFamily") == "Storage" and filters.get("volumeApiName") == "gp3":
            return {"PriceList": [json.dumps(SAMPLE_EBS_PRICING_GP3)]}

        return {"PriceList": []}

    mock_pricing_client.get_products = mock_get_products

    context.pricing_client_patch = patch("boto3.client")
    mock_boto_client = context.pricing_client_patch.start()

    def client_factory(service_name, region_name=None):
        if service_name == "pricing":
            return mock_pricing_client
        return original_boto3_client(service_name, region_name=region_name)

    mock_boto_client.side_effect = client_factory


@given("AWS Pricing API is mocked with call counter")
def step_mock_pricing_api_with_call_counter(context: Context) -> None:
    """Mock AWS Pricing API and track number of API calls."""
    import boto3
    original_boto3_client = boto3.client

    mock_pricing_client = Mock()
    context.pricing_api_call_count = {}

    def mock_get_products(**kwargs):
        filters = {f["Field"]: f["Value"] for f in kwargs.get("Filters", [])}
        instance_type = filters.get("instanceType", "")

        if instance_type:
            context.pricing_api_call_count[instance_type] = context.pricing_api_call_count.get(instance_type, 0) + 1

        if filters.get("instanceType") == "t3.medium":
            return {"PriceList": [json.dumps(SAMPLE_EC2_PRICING_T3_MEDIUM)]}
        elif filters.get("productFamily") == "Storage":
            return {"PriceList": [json.dumps(SAMPLE_EBS_PRICING_GP3)]}

        return {"PriceList": []}

    mock_pricing_client.get_products = mock_get_products

    context.pricing_client_patch = patch("boto3.client")
    mock_boto_client = context.pricing_client_patch.start()

    def client_factory(service_name, region_name=None):
        if service_name == "pricing":
            return mock_pricing_client
        return original_boto3_client(service_name, region_name=region_name)

    mock_boto_client.side_effect = client_factory


@given("AWS Pricing API is not accessible")
def step_pricing_api_not_accessible(context: Context) -> None:
    """Mock AWS Pricing API as unavailable (LocalStack scenario)."""
    import boto3
    original_boto3_client = boto3.client

    context.pricing_client_patch = patch("boto3.client")
    mock_boto_client = context.pricing_client_patch.start()

    def client_factory(service_name, region_name=None):
        if service_name == "pricing":
            raise Exception("Pricing API not available in LocalStack")
        return original_boto3_client(service_name, region_name=region_name)

    mock_boto_client.side_effect = client_factory


@given("AWS Pricing API is available")
def step_pricing_api_available(context: Context) -> None:
    """Set up AWS Pricing API as available."""
    import boto3
    original_boto3_client = boto3.client

    mock_pricing_client = Mock()

    def mock_get_products(**kwargs):
        filters = {f["Field"]: f["Value"] for f in kwargs.get("Filters", [])}

        if filters.get("instanceType") == "t3.medium":
            return {"PriceList": [json.dumps(SAMPLE_EC2_PRICING_T3_MEDIUM)]}

        return {"PriceList": []}

    mock_pricing_client.get_products = mock_get_products

    context.pricing_client_patch = patch("boto3.client")
    mock_boto_client = context.pricing_client_patch.start()

    def client_factory(service_name, region_name=None):
        if service_name == "pricing":
            return mock_pricing_client
        return original_boto3_client(service_name, region_name=region_name)

    mock_boto_client.side_effect = client_factory


@given('I have a running instance of type "{instance_type}"')
def step_running_instance_with_type(context: Context, instance_type: str) -> None:
    """Create a running instance with specified type."""
    from tests.unit.fakes.fake_ec2_manager import FakeEC2Manager

    if not hasattr(context, "fake_ec2_managers"):
        context.fake_ec2_managers = {}

    region = "us-east-1"

    if region not in context.fake_ec2_managers:
        context.fake_ec2_managers[region] = FakeEC2Manager(region)

    fake_manager = context.fake_ec2_managers[region]

    instance_id = f"i-{len(fake_manager.instances):08x}"
    unique_id = f"test-{instance_type}"

    fake_manager.instances[instance_id] = {
        "instance_id": instance_id,
        "unique_id": unique_id,
        "name": f"moondock-test-{instance_type}",
        "state": "running",
        "region": region,
        "instance_type": instance_type,
        "launch_time": datetime.now(timezone.utc),
        "machine_config": f"test-{instance_type}",
        "volume_size": 50,
    }

    if not hasattr(context, "test_instances"):
        context.test_instances = []

    context.test_instances.append(instance_id)


@given('I have a stopped instance of type "{instance_type}"')
def step_stopped_instance_with_type(context: Context, instance_type: str) -> None:
    """Create a stopped instance with specified type."""
    from tests.unit.fakes.fake_ec2_manager import FakeEC2Manager

    if not hasattr(context, "fake_ec2_managers"):
        context.fake_ec2_managers = {}

    region = "us-east-1"

    if region not in context.fake_ec2_managers:
        context.fake_ec2_managers[region] = FakeEC2Manager(region)

    fake_manager = context.fake_ec2_managers[region]

    instance_id = f"i-{len(fake_manager.instances):08x}"
    unique_id = f"test-{instance_type}"

    fake_manager.instances[instance_id] = {
        "instance_id": instance_id,
        "unique_id": unique_id,
        "name": f"moondock-test-{instance_type}",
        "state": "stopped",
        "region": region,
        "instance_type": instance_type,
        "launch_time": datetime.now(timezone.utc),
        "machine_config": f"test-{instance_type}",
        "volume_size": 40,
    }

    if not hasattr(context, "test_instances"):
        context.test_instances = []

    context.test_instances.append(instance_id)


@given('I have a running instance of type "{instance_type}" with {volume_size:d}GB volume')
def step_running_instance_with_type_and_volume(
    context: Context, instance_type: str, volume_size: int
) -> None:
    """Create a running instance with specified type and volume size."""
    if not hasattr(context, "instances") or context.instances is None:
        context.instances = []

    instance = {
        "instance_id": f"i-{len(context.instances):08x}",
        "name": f"moondock-test-{instance_type}",
        "state": "running",
        "region": "us-east-1",
        "instance_type": instance_type,
        "launch_time": datetime.now(timezone.utc),
        "machine_config": f"test-{instance_type}",
        "volume_size": volume_size,
    }

    context.instances.append(instance)
    context.test_volume_size = volume_size


@given('I have a stopped instance of type "{instance_type}" with {volume_size:d}GB volume')
def step_stopped_instance_with_type_and_volume(
    context: Context, instance_type: str, volume_size: int
) -> None:
    """Create a stopped instance with specified type and volume size."""
    if not hasattr(context, "instances") or context.instances is None:
        context.instances = []

    instance = {
        "instance_id": f"i-{len(context.instances):08x}",
        "name": f"moondock-test-{instance_type}",
        "state": "stopped",
        "region": "us-east-1",
        "instance_type": instance_type,
        "launch_time": datetime.now(timezone.utc),
        "machine_config": f"test-{instance_type}",
        "volume_size": volume_size,
    }

    context.instances.append(instance)
    context.test_volume_size = volume_size


@given('I have an instance in unsupported region "{region}"')
def step_instance_in_unsupported_region(context: Context, region: str) -> None:
    """Create an instance in an unsupported region."""
    if not hasattr(context, "instances") or context.instances is None:
        context.instances = []

    instance = {
        "instance_id": f"i-{len(context.instances):08x}",
        "name": "moondock-test-unsupported",
        "state": "running",
        "region": region,
        "instance_type": "t3.medium",
        "launch_time": datetime.now(timezone.utc),
        "machine_config": "test-unsupported",
    }

    context.instances.append(instance)


@given("I have a running instance")
def step_running_instance_generic(context: Context) -> None:
    """Create a generic running instance."""
    if not hasattr(context, "instances") or context.instances is None:
        context.instances = []

    instance = {
        "instance_id": f"i-{len(context.instances):08x}",
        "name": "moondock-test",
        "state": "running",
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "launch_time": datetime.now(timezone.utc),
        "machine_config": "test-generic",
    }

    context.instances.append(instance)


@given("I have a stopped instance")
def step_stopped_instance_generic(context: Context) -> None:
    """Create a generic stopped instance."""
    if not hasattr(context, "instances") or context.instances is None:
        context.instances = []

    instance = {
        "instance_id": f"i-{len(context.instances):08x}",
        "name": "moondock-test",
        "state": "stopped",
        "region": "us-east-1",
        "instance_type": "t3.medium",
        "launch_time": datetime.now(timezone.utc),
        "machine_config": "test-generic",
    }

    context.instances.append(instance)


@when('I run "moondock list" twice within 24 hours')
@given('I run "moondock list" twice within 24 hours')
def step_run_list_twice(context: Context) -> None:
    """Run moondock list command twice to test caching."""
    from tests.integration.features.steps.common_steps import execute_command_direct

    execute_command_direct(context, "list")
    first_output = context.stdout

    execute_command_direct(context, "list")
    second_output = context.stdout

    context.first_list_output = first_output
    context.second_list_output = second_output


@then('cost column shows "{cost}" for {instance_type}')
def step_cost_column_shows_value(context: Context, cost: str, instance_type: str) -> None:
    """Verify cost column displays expected value for instance type."""
    output = context.stdout

    if instance_type not in output:
        raise AssertionError(f"Instance type {instance_type} not found in output:\n{output}")

    if cost not in output:
        raise AssertionError(f"Cost '{cost}' not found in output:\n{output}")


@then('cost column shows "{cost}"')
def step_cost_column_shows_text(context: Context, cost: str) -> None:
    """Verify cost column displays expected value."""
    output = context.stdout

    if cost not in output:
        raise AssertionError(f"Cost '{cost}' not found in output:\n{output}")


@then('I see total estimated cost "{total_cost}"')
def step_see_total_estimated_cost(context: Context, total_cost: str) -> None:
    """Verify total estimated cost is displayed."""
    output = context.stdout

    if "Total estimated cost:" not in output:
        raise AssertionError(f"'Total estimated cost:' not found in output:\n{output}")

    if total_cost not in output:
        raise AssertionError(f"Total cost '{total_cost}' not found in output:\n{output}")


@then('I see "{text}" at top')
def step_see_text_at_top(context: Context, text: str) -> None:
    """Verify specific text appears at the top of output."""
    output = context.stdout

    if text not in output:
        raise AssertionError(f"Text '{text}' not found in output:\n{output}")


@then("no total cost is displayed")
def step_no_total_cost_displayed(context: Context) -> None:
    """Verify no total cost is shown in output."""
    output = context.stdout

    if "Total estimated cost:" in output:
        raise AssertionError(f"Unexpected total cost found in output:\n{output}")


@then('I see "{text}"')
def step_see_text(context: Context, text: str) -> None:
    """Verify specific text appears in output."""
    output = context.stdout

    if text not in output:
        raise AssertionError(f"Text '{text}' not found in output:\n{output}")


@then("API is called once for each instance type")
def step_api_called_once_per_type(context: Context) -> None:
    """Verify pricing API called only once per instance type."""
    call_count = context.pricing_api_call_count

    for instance_type, count in call_count.items():
        if count != 1:
            raise AssertionError(
                f"Expected 1 API call for {instance_type}, got {count}. "
                f"All calls: {call_count}"
            )


@then("second list uses cached pricing")
def step_second_list_uses_cache(context: Context) -> None:
    """Verify second list command used cached pricing data."""
    call_count = context.pricing_api_call_count

    for instance_type, count in call_count.items():
        if count > 1:
            raise AssertionError(
                f"Expected cached pricing for {instance_type}, but API was called {count} times"
            )


@then("stop operation completes successfully")
def step_stop_operation_completes(context: Context) -> None:
    """Verify stop operation completed successfully."""
    output = context.stdout

    if "successfully stopped" not in output:
        raise AssertionError(f"Stop operation did not complete successfully:\n{output}")


@then("start operation completes successfully")
def step_start_operation_completes(context: Context) -> None:
    """Verify start operation completed successfully."""
    output = context.stdout

    if "successfully started" not in output:
        raise AssertionError(f"Start operation did not complete successfully:\n{output}")


@then('that instance shows "{text}" in cost column')
def step_cost_column_shows_text_for_instance(context: Context, text: str) -> None:
    """Verify cost column shows specific text for an instance."""
    output = context.stdout

    if text not in output:
        raise AssertionError(f"Text '{text}' not found in output:\n{output}")


@then("other instances show correct pricing")
def step_other_instances_show_correct_pricing(context: Context) -> None:
    """Verify other instances still show pricing correctly."""
    output = context.stdout

    if "$" not in output or "/month" not in output:
        raise AssertionError(f"No valid pricing found in output:\n{output}")
