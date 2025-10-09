"""Step definitions for setup command feature."""

import subprocess
from pathlib import Path

from behave import given, then
from behave.runner import Context


@given('region "{region}" has no default VPC')
def step_region_has_no_default_vpc(context: Context, region: str) -> None:
    """Ensure region has no default VPC.

    Parameters
    ----------
    context : Context
        Behave context
    region : str
        AWS region
    """
    import boto3
    from botocore.exceptions import ClientError

    ec2_client = boto3.client("ec2", region_name=region)

    vpcs = ec2_client.describe_vpcs()
    for vpc in vpcs.get("Vpcs", []):
        if vpc.get("IsDefault"):
            vpc_id = vpc["VpcId"]

            try:
                subnets = ec2_client.describe_subnets(
                    Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]
                )

                for subnet in subnets.get("Subnets", []):
                    try:
                        ec2_client.delete_subnet(SubnetId=subnet["SubnetId"])
                    except ClientError:
                        pass

                igws = ec2_client.describe_internet_gateways(
                    Filters=[{"Name": "attachment.vpc-id", "Values": [vpc_id]}]
                )

                for igw in igws.get("InternetGateways", []):
                    try:
                        ec2_client.detach_internet_gateway(
                            InternetGatewayId=igw["InternetGatewayId"], VpcId=vpc_id
                        )
                        ec2_client.delete_internet_gateway(
                            InternetGatewayId=igw["InternetGatewayId"]
                        )
                    except ClientError:
                        pass

                ec2_client.delete_vpc(VpcId=vpc_id)
            except ClientError:
                pass


@given('region "{region}" has default VPC')
def step_region_has_default_vpc(context: Context, region: str) -> None:
    """Ensure region has a default VPC.

    Parameters
    ----------
    context : Context
        Behave context
    region : str
        AWS region
    """
    import boto3

    ec2_client = boto3.client("ec2", region_name=region)

    vpcs = ec2_client.describe_vpcs()
    has_default = any(vpc.get("IsDefault") for vpc in vpcs.get("Vpcs", []))

    if not has_default:
        ec2_client.create_default_vpc()


@given('"moondock setup" completed successfully')
def step_setup_completed_successfully(context: Context) -> None:
    """Run moondock setup successfully.

    Parameters
    ----------
    context : Context
        Behave context
    """
    import os

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
