"""Step definitions for doctor command feature."""

from behave import given, then
from behave.runner import Context


@given("required IAM permissions exist")
def step_required_iam_permissions_exist(context: Context) -> None:
    """Mock IAM permissions (all pass in moto)."""
    pass


@then("no AWS resources created")
def step_no_aws_resources_created(context: Context) -> None:
    """Verify no AWS resources were created during doctor command.

    Parameters
    ----------
    context : Context
        Behave context
    """
    import boto3

    ec2_client = boto3.client("ec2", region_name="us-east-1")

    instances = ec2_client.describe_instances()
    instance_count = sum(
        len(reservation["Instances"])
        for reservation in instances.get("Reservations", [])
    )

    vpcs_before = getattr(context, "vpcs_before_doctor", None)

    if vpcs_before is None:
        vpcs_before = []

    vpcs_after = ec2_client.describe_vpcs().get("Vpcs", [])

    assert instance_count == 0, f"Expected no instances, found {instance_count}"
    assert len(vpcs_after) == len(vpcs_before), (
        f"VPC count changed from {len(vpcs_before)} to {len(vpcs_after)}"
    )
