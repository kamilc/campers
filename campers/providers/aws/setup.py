"""Setup and infrastructure management for campers."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from campers.core.config import ConfigLoader

logger = logging.getLogger(__name__)


@dataclass
class InfrastructureCheckResult:
    """Result of infrastructure checks.

    Attributes
    ----------
    vpc_exists : bool
        Whether default VPC exists in the region
    missing_permissions : list[str]
        List of missing IAM permissions, empty if all required permissions exist
    """

    vpc_exists: bool
    missing_permissions: list[str]


class SetupManager:
    """Manager for AWS setup and diagnostic operations.

    Handles infrastructure validation, credentials checking, IAM permissions
    verification, and diagnostic reporting.

    Parameters
    ----------
    config_loader : ConfigLoader
        Configuration loader for accessing configuration settings
    """

    def __init__(
        self,
        config_loader: ConfigLoader,
    ) -> None:
        """Initialize SetupManager with required dependencies.

        Parameters
        ----------
        config_loader : ConfigLoader
            Configuration loader for accessing configuration settings
        """
        self._config_loader = config_loader

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
        sts_client = None
        try:
            sts_client = boto3.client("sts", region_name=effective_region)
            sts_client.get_caller_identity()
            logger.info("AWS credentials found", extra={"stream": "stdout"})
            return True
        except NoCredentialsError:
            logger.error("AWS credentials not found", extra={"stream": "stderr"})
            logger.error("Fix it:", extra={"stream": "stderr"})
            logger.error("  aws configure", extra={"stream": "stderr"})
            return False
        except ClientError:
            logger.info("AWS credentials found", extra={"stream": "stdout"})
            return True
        finally:
            if sts_client:
                sts_client.close()

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
                    logging.debug("DryRunOperation for %s", perm_name)
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
                    logger.info(
                        f"Cloud instance limit: {max_instances} instances",
                        extra={"stream": "stdout"},
                    )

            instances = ec2_client.describe_instances()
            running_count = sum(
                1
                for r in instances["Reservations"]
                for inst in r["Instances"]
                if inst["State"]["Name"] in ["running", "pending"]
            )
            logger.info(
                f"Currently running cloud instances: {running_count}",
                extra={"stream": "stdout"},
            )

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

            logger.info(
                f"Regional availability in {effective_region}:",
                extra={"stream": "stdout"},
            )
            for zone in zones:
                status = zone["State"]
                zone_name = zone["ZoneName"]
                logger.info(f"  {zone_name}: {status}", extra={"stream": "stdout"})

        except ClientError as e:
            logging.warning("Could not check regional availability: %s", e)

    def check_infrastructure(
        self, ec2_client: Any, effective_region: str
    ) -> InfrastructureCheckResult:
        """Check AWS infrastructure status.

        Parameters
        ----------
        ec2_client : Any
            boto3 EC2 client
        effective_region : str
            AWS region to check

        Returns
        -------
        InfrastructureCheckResult
            Infrastructure check result with VPC status and missing permissions
        """
        vpc_exists = self.check_vpc_status(ec2_client, effective_region)
        missing_perms = self.check_iam_permissions(ec2_client)

        return InfrastructureCheckResult(vpc_exists, missing_perms)

    def setup(self, region: str | None = None) -> None:
        """Validate and prepare AWS infrastructure prerequisites.

        Parameters
        ----------
        region : str | None
            AWS region to check (defaults to config or us-east-1)

        Raises
        ------
        SystemExit
            Exits with code 1 if AWS credentials are not found
        """
        effective_region = self.get_effective_region(region)

        logger.info(
            f"Checking AWS prerequisites for {effective_region}...",
            extra={"stream": "stdout"},
        )

        if not self.check_aws_credentials(effective_region):
            sys.exit(1)

        ec2_client = boto3.client("ec2", region_name=effective_region)

        try:
            check_result = self.check_infrastructure(ec2_client, effective_region)

            if not check_result.vpc_exists:
                logger.info(
                    f"No default VPC found in {effective_region}",
                    extra={"stream": "stdout"},
                )

                response = input("Create default VPC now? (y/n): ")

                if response.lower() == "y":
                    try:
                        ec2_client.create_default_vpc()
                        logger.info(
                            f"Default VPC created in {effective_region}",
                            extra={"stream": "stdout"},
                        )
                    except ClientError as e:
                        error_code = e.response.get("Error", {}).get("Code", "")
                        if error_code == "DefaultVpcAlreadyExists":
                            logger.info(
                                f"Default VPC created in {effective_region}",
                                extra={"stream": "stdout"},
                            )
                        else:
                            logger.error(f"Failed to create VPC: {e}", extra={"stream": "stderr"})
                            logger.error("Manual creation:", extra={"stream": "stderr"})
                            logger.error(
                                f"  aws ec2 create-default-vpc --region {effective_region}",
                                extra={"stream": "stderr"},
                            )
                            sys.exit(1)
                else:
                    logger.info("Skipping VPC creation.", extra={"stream": "stdout"})
                    logger.info("You can create it later with:", extra={"stream": "stdout"})
                    logger.info(
                        f"  aws ec2 create-default-vpc --region {effective_region}",
                        extra={"stream": "stdout"},
                    )
                    return
            else:
                logger.info(
                    f"Default VPC exists in {effective_region}",
                    extra={"stream": "stdout"},
                )

            if check_result.missing_permissions:
                missing_perms = ", ".join(check_result.missing_permissions)
                logger.info(
                    f"Missing IAM permissions: {missing_perms}",
                    extra={"stream": "stdout"},
                )
                logger.info(
                    "Some operations may fail without these permissions.",
                    extra={"stream": "stdout"},
                )
            else:
                logger.info("IAM permissions verified", extra={"stream": "stdout"})

            logger.info("Setup complete! Run: campers run", extra={"stream": "stdout"})
        finally:
            ec2_client.close()

    def doctor(self, region: str | None = None) -> None:
        """Diagnose AWS environment and report status.

        Parameters
        ----------
        region : str | None
            AWS region to check (defaults to config or us-east-1)

        Raises
        ------
        SystemExit
            Exits with code 1 if AWS credentials are not found
        """
        effective_region = self.get_effective_region(region)

        logger.info("Running diagnostics for %s...", effective_region, extra={"stream": "stdout"})

        if not self.check_aws_credentials(effective_region):
            sys.exit(1)

        ec2_client = boto3.client("ec2", region_name=effective_region)

        try:
            check_result = self.check_infrastructure(ec2_client, effective_region)

            if not check_result.vpc_exists:
                message = f"No default VPC in {effective_region}"
                logger.info(message, extra={"stream": "stdout"})
                logger.info("Fix it:", extra={"stream": "stdout"})
                logger.info("  campers setup", extra={"stream": "stdout"})
                logger.info("Or manually:", extra={"stream": "stdout"})
                logger.info(
                    f"  aws ec2 create-default-vpc --region {effective_region}",
                    extra={"stream": "stdout"},
                )
            else:
                message = f"Default VPC exists in {effective_region}"
                logger.info(message, extra={"stream": "stdout"})

            if check_result.missing_permissions:
                perms_str = ", ".join(check_result.missing_permissions)
                logger.info(
                    "Missing IAM permissions: %s",
                    perms_str,
                    extra={"stream": "stdout"},
                )
                logger.info("Required permissions:", extra={"stream": "stdout"})
                for perm in check_result.missing_permissions:
                    logger.info("  - %s", perm, extra={"stream": "stdout"})
            else:
                logger.info("IAM permissions verified", extra={"stream": "stdout"})

            self.check_service_quotas(ec2_client, effective_region)
            self.check_regional_availability(ec2_client, effective_region)

            logger.info("Diagnostics complete.", extra={"stream": "stdout"})
        finally:
            ec2_client.close()
