"""Step definitions for doctor command feature."""

from behave import given, then
from behave.runner import Context


@given('region "{region}" has no default VPC')
def step_region_has_no_default_vpc(context: Context, region: str) -> None:
    """Configure mocked EC2 client to report no default VPC.

    Parameters
    ----------
    context : Context
        Behave context with patched_ec2_client
    region : str
        AWS region (currently only us-east-1 supported in tests)
    """
    ec2_client = getattr(context, "patched_ec2_client", None)

    if ec2_client is None:
        return

    ec2_client._original_describe_vpcs = getattr(
        ec2_client, "_original_describe_vpcs", ec2_client.describe_vpcs
    )
    ec2_client._original_create_default_vpc = getattr(
        ec2_client, "_original_create_default_vpc", ec2_client.create_default_vpc
    )

    ec2_client._has_default_vpc = False

    original_describe_vpcs = ec2_client._original_describe_vpcs
    original_create_default_vpc = ec2_client._original_create_default_vpc

    def mock_describe_vpcs(**kwargs):
        filters = kwargs.get("Filters", [])

        for f in filters:
            if f.get("Name") == "isDefault" and f.get("Values") == ["true"]:
                return {"Vpcs": []}

        if not ec2_client._has_default_vpc:
            response = original_describe_vpcs(**kwargs)
            vpcs = response.get("Vpcs", [])
            vpcs = [vpc for vpc in vpcs if not vpc.get("IsDefault")]
            response["Vpcs"] = vpcs
            return response

        return original_describe_vpcs(**kwargs)

    def mock_create_default_vpc(**kwargs):
        try:
            vpc_response = original_create_default_vpc(**kwargs)
            if not kwargs.get("DryRun", False):
                ec2_client._has_default_vpc = True
            return vpc_response
        except Exception:
            if kwargs.get("DryRun", False):
                raise
            if not ec2_client._has_default_vpc:
                ec2_client._has_default_vpc = True
                response = original_describe_vpcs()
                if response.get("Vpcs"):
                    return {"Vpc": response["Vpcs"][0]}
                return {
                    "Vpc": {
                        "VpcId": "vpc-12345",
                        "IsDefault": True,
                    }
                }
            raise

    ec2_client.describe_vpcs = mock_describe_vpcs
    ec2_client.create_default_vpc = mock_create_default_vpc
    actual_vpcs = ec2_client._original_describe_vpcs()
    context.vpcs_before_doctor = [vpc["VpcId"] for vpc in actual_vpcs.get("Vpcs", [])]


@given('region "{region}" has default VPC')
def step_region_has_default_vpc(context: Context, region: str) -> None:
    """Configure mocked EC2 client to report default VPC exists.

    Parameters
    ----------
    context : Context
        Behave context with patched_ec2_client
    region : str
        AWS region
    """
    import boto3

    ec2_client = getattr(context, "patched_ec2_client", None)
    is_dry_run = ec2_client is None or hasattr(context, "harness")

    if is_dry_run:
        ec2_client = boto3.client("ec2", region_name=region)

        vpcs = ec2_client.describe_vpcs().get("Vpcs", [])
        for vpc in vpcs:
            vpc_id = vpc["VpcId"]
            try:
                subnets = ec2_client.describe_subnets(
                    Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]
                )
                for subnet in subnets.get("Subnets", []):
                    ec2_client.delete_subnet(SubnetId=subnet["SubnetId"])

                ec2_client.delete_vpc(VpcId=vpc_id)
            except Exception:
                pass

        vpc_response = ec2_client.create_default_vpc()
        vpc_id = vpc_response["Vpc"]["VpcId"]
        context.default_vpc_id = vpc_id
        context.vpcs_before_doctor = [vpc_id]
        context.patched_ec2_client = ec2_client
        return

    ec2_client._original_describe_vpcs = getattr(
        ec2_client, "_original_describe_vpcs", ec2_client.describe_vpcs
    )

    ec2_client._has_default_vpc = True

    vpcs = ec2_client._original_describe_vpcs()
    has_default = any(vpc.get("IsDefault") for vpc in vpcs.get("Vpcs", []))

    if not has_default:
        if vpcs.get("Vpcs"):
            vpc_id = vpcs["Vpcs"][0]["VpcId"]
        else:
            try:
                vpc_response = ec2_client.create_default_vpc()
                vpc_id = vpc_response["Vpc"]["VpcId"]
            except Exception:
                vpc_response = ec2_client.create_vpc(CidrBlock="10.0.0.0/16")
                vpc_id = vpc_response["Vpc"]["VpcId"]
    else:
        vpc_id = next(
            vpc["VpcId"] for vpc in vpcs.get("Vpcs", []) if vpc.get("IsDefault")
        )

    context.default_vpc_id = vpc_id

    def mock_describe_vpcs(**kwargs):
        filters = kwargs.get("Filters", [])
        has_isdefault_filter = any(f.get("Name") == "isDefault" for f in filters)

        if has_isdefault_filter:
            kwargs_without_filter = {k: v for k, v in kwargs.items() if k != "Filters"}
            result = ec2_client._original_describe_vpcs(**kwargs_without_filter)
        else:
            result = ec2_client._original_describe_vpcs(**kwargs)

        for vpc in result.get("Vpcs", []):
            if vpc["VpcId"] == vpc_id:
                vpc["IsDefault"] = True

        if has_isdefault_filter:
            vpcs = result.get("Vpcs", [])
            result["Vpcs"] = [vpc for vpc in vpcs if vpc.get("IsDefault")]

        return result

    ec2_client.describe_vpcs = mock_describe_vpcs
    actual_vpcs = ec2_client._original_describe_vpcs()
    context.vpcs_before_doctor = [vpc["VpcId"] for vpc in actual_vpcs.get("Vpcs", [])]


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

    ec2_client = getattr(context, "patched_ec2_client", None)
    if ec2_client is None:
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
