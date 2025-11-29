"""Setup and infrastructure management for campers."""

from __future__ import annotations

import logging
import sys
from typing import Any

from botocore.exceptions import ClientError, NoCredentialsError

from campers.core.config import ConfigLoader


class SetupManager:
    """Manager for AWS setup and diagnostic operations.

    Handles infrastructure validation, credentials checking, IAM permissions
    verification, and diagnostic reporting.

    Parameters
    ----------
    config_loader : ConfigLoader
        Configuration loader for accessing configuration settings
    boto3_client_factory : Callable[..., Any]
        Factory function for creating boto3 clients
    """

    def __init__(
        self,
        config_loader: ConfigLoader,
        boto3_client_factory: Any,
    ) -> None:
        """Initialize SetupManager with required dependencies.

        Parameters
        ----------
        config_loader : ConfigLoader
            Configuration loader for accessing configuration settings
        boto3_client_factory : Callable[..., Any]
            Factory function for creating boto3 clients
        """
        self._config_loader = config_loader
        self._boto3_client_factory = boto3_client_factory

    def get_effective_region(self, region: str | None) -> str:
        """Get effective region from parameter or config.

        Parameters
        ----------
        region : str | None
            Region parameter from command line

        Returns
        -------
        str
            Effective region to use
        """
        effective_region = region or self._config_loader.BUILT_IN_DEFAULTS["region"]

        config = self._config_loader.load_config()

        if config.get("defaults", {}).get("region") and not region:
            effective_region = config["defaults"]["region"]

        return effective_region

    def check_aws_credentials(self, effective_region: str) -> bool:
        """Check if AWS credentials are configured and functional.

        Parameters
        ----------
        effective_region : str
            AWS region to check

        Returns
        -------
        bool
            True if credentials are valid, False otherwise
        """
        try:
            sts_client = self._boto3_client_factory("sts", region_name=effective_region)
            sts_client.get_caller_identity()
            print("AWS credentials found")
            return True
        except NoCredentialsError:
            print("AWS credentials not found\n")
            print("Fix it:")
            print("  aws configure")
            return False
        except ClientError:
            print("AWS credentials found")
            return True

    def check_vpc_status(self, ec2_client: Any, effective_region: str) -> bool:
        """Check if default VPC exists in region.

        Parameters
        ----------
        ec2_client : Any
            boto3 EC2 client
        effective_region : str
            AWS region to check

        Returns
        -------
        bool
            True if default VPC exists, False otherwise
        """
        vpcs = ec2_client.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])

        return bool(vpcs["Vpcs"])

    def check_iam_permissions(self, ec2_client: Any) -> list[str]:
        """Check IAM permissions for campers operations.

        Parameters
        ----------
        ec2_client : Any
            boto3 EC2 client

        Returns
        -------
        list[str]
            List of missing permissions
        """
        missing = []

        read_checks = [
            ("DescribeInstances", lambda: ec2_client.describe_instances(MaxResults=5)),
            ("DescribeVpcs", lambda: ec2_client.describe_vpcs(MaxResults=5)),
            ("DescribeKeyPairs", lambda: ec2_client.describe_key_pairs()),
            (
                "DescribeSecurityGroups",
                lambda: ec2_client.describe_security_groups(MaxResults=5),
            ),
        ]

        for perm_name, check_func in read_checks:
            try:
                check_func()
            except ClientError as e:
                if "UnauthorizedOperation" in str(e) or "AccessDenied" in str(e):
                    missing.append(perm_name)

        write_checks = [
            (
                "RunInstances",
                lambda: ec2_client.run_instances(
                    ImageId="ami-12345678",
                    InstanceType="t2.micro",
                    MinCount=1,
                    MaxCount=1,
                    DryRun=True,
                ),
            ),
            (
                "TerminateInstances",
                lambda: ec2_client.terminate_instances(InstanceIds=["i-12345678"], DryRun=True),
            ),
            (
                "CreateDefaultVpc",
                lambda: ec2_client.create_default_vpc(DryRun=True),
            ),
            (
                "CreateKeyPair",
                lambda: ec2_client.create_key_pair(KeyName="test-key-dry-run", DryRun=True),
            ),
            (
                "DeleteKeyPair",
                lambda: ec2_client.delete_key_pair(KeyName="test-key-dry-run", DryRun=True),
            ),
        ]

        for perm_name, check_func in write_checks:
            try:
                check_func()
            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "")

                if error_code == "DryRunOperation":
                    pass
                elif error_code in ["UnauthorizedOperation", "AccessDenied"]:
                    missing.append(perm_name)

        return missing

    def check_service_quotas(self, ec2_client: Any, effective_region: str) -> None:
        """Check EC2 service quotas for instance limits.

        Parameters
        ----------
        ec2_client : Any
            boto3 EC2 client
        effective_region : str
            AWS region to check
        """
        try:
            response = ec2_client.describe_account_attributes(AttributeNames=["max-instances"])

            for attr in response.get("AccountAttributes", []):
                if attr["AttributeName"] == "max-instances":
                    max_instances = attr["AttributeValues"][0]["AttributeValue"]
                    print(f"Cloud instance limit: {max_instances} instances")

            instances = ec2_client.describe_instances()
            running_count = sum(
                1
                for r in instances["Reservations"]
                for inst in r["Instances"]
                if inst["State"]["Name"] in ["running", "pending"]
            )
            print(f"Currently running cloud instances: {running_count}")

        except ClientError as e:
            logging.warning("Could not check service quotas: %s", e)

    def check_regional_availability(self, ec2_client: Any, effective_region: str) -> None:
        """Check if region is available and operational.

        Parameters
        ----------
        ec2_client : Any
            boto3 EC2 client
        effective_region : str
            AWS region to check
        """
        try:
            response = ec2_client.describe_availability_zones()
            zones = response.get("AvailabilityZones", [])

            print(f"\nRegional availability in {effective_region}:")
            for zone in zones:
                status = zone["State"]
                zone_name = zone["ZoneName"]
                print(f"  {zone_name}: {status}")

        except ClientError as e:
            logging.warning("Could not check regional availability: %s", e)

    def check_infrastructure(
        self, ec2_client: Any, effective_region: str
    ) -> tuple[bool, list[str]]:
        """Check AWS infrastructure status.

        Parameters
        ----------
        ec2_client : Any
            boto3 EC2 client
        effective_region : str
            AWS region to check

        Returns
        -------
        tuple[bool, list[str]]
            Tuple of (vpc_exists, missing_permissions)
        """
        vpc_exists = self.check_vpc_status(ec2_client, effective_region)
        missing_perms = self.check_iam_permissions(ec2_client)

        return vpc_exists, missing_perms

    def setup(self, region: str | None = None, ec2_client: Any = None) -> None:
        """Validate and prepare AWS infrastructure prerequisites.

        Parameters
        ----------
        region : str | None
            AWS region to check (defaults to config or us-east-1)
        ec2_client : Any
            boto3 EC2 client (for testing purposes)

        Raises
        ------
        SystemExit
            Exits with code 1 if AWS credentials are not found
        """
        effective_region = self.get_effective_region(region)

        print(f"Checking AWS prerequisites for {effective_region}...\n")

        if not self.check_aws_credentials(effective_region):
            sys.exit(1)

        if ec2_client is None:
            ec2_client = self._boto3_client_factory("ec2", region_name=effective_region)

        vpc_exists, missing_perms = self.check_infrastructure(ec2_client, effective_region)

        if not vpc_exists:
            print(f"No default VPC found in {effective_region}\n")

            response = input("Create default VPC now? (y/n): ")

            if response.lower() == "y":
                try:
                    ec2_client.create_default_vpc()
                    print(f"Default VPC created in {effective_region}")
                except ClientError as e:
                    print(f"\nFailed to create VPC: {e}")
                    print("\nManual creation:")
                    print(f"  aws ec2 create-default-vpc --region {effective_region}")
                    sys.exit(1)
            else:
                print("\nSkipping VPC creation.")
                print("You can create it later with:")
                print(f"  aws ec2 create-default-vpc --region {effective_region}")
                return
        else:
            print(f"Default VPC exists in {effective_region}")

        if missing_perms:
            print(f"Missing IAM permissions: {', '.join(missing_perms)}")
            print("\nSome operations may fail without these permissions.")
        else:
            print("IAM permissions verified")

        print("\nSetup complete! Run: campers run")

    def doctor(self, region: str | None = None, ec2_client: Any = None) -> None:
        """Diagnose AWS environment and report status.

        Parameters
        ----------
        region : str | None
            AWS region to check (defaults to config or us-east-1)
        ec2_client : Any
            boto3 EC2 client (for testing purposes)

        Raises
        ------
        SystemExit
            Exits with code 1 if AWS credentials are not found
        """
        effective_region = self.get_effective_region(region)

        print(f"Running diagnostics for {effective_region}...\n")

        if not self.check_aws_credentials(effective_region):
            sys.exit(1)

        if ec2_client is None:
            ec2_client = self._boto3_client_factory("ec2", region_name=effective_region)

        vpc_exists, missing_perms = self.check_infrastructure(ec2_client, effective_region)

        if not vpc_exists:
            print(f"No default VPC in {effective_region}\n")
            print("Fix it:")
            print("  campers setup")
            print("Or manually:")
            print(f"  aws ec2 create-default-vpc --region {effective_region}")
        else:
            print(f"Default VPC exists in {effective_region}")

        if missing_perms:
            print(f"Missing IAM permissions: {', '.join(missing_perms)}")
            print("\nRequired permissions:")
            for perm in missing_perms:
                print(f"  - {perm}")
        else:
            print("IAM permissions verified")

        if ec2_client is not None:
            print()
            self.check_service_quotas(ec2_client, effective_region)
            self.check_regional_availability(ec2_client, effective_region)

        print("\nDiagnostics complete.")
