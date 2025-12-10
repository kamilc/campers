"""LocalStack-specific BDD step definitions."""

import logging
import os
import time
from typing import Any

import boto3
import requests
from behave import given, then
from behave.runner import Context

from tests.harness.services.event_bus import EventBusTimeoutError

logger = logging.getLogger(__name__)


def get_localstack_services(context: Context) -> Any:
    """Return LocalStack harness services for the current scenario.

    Parameters
    ----------
    context : Context
        Behave context containing the harness reference.

    Returns
    -------
    Any
        LocalStack service container from the harness.
    """

    harness = getattr(context, "harness", None)
    services = getattr(harness, "services", None)
    if services is None:
        raise RuntimeError("LocalStack harness services not initialised")
    return services


def wait_for_ssh_container_ready(instance_id: str, timeout: int = 90) -> None:
    """Wait for SSH container to be ready for given instance.

    This function blocks until the monitor thread has finished creating
    the SSH container and setting the environment variables.

    Parameters
    ----------
    instance_id : str
        EC2 instance ID to wait for
    timeout : int
        Maximum time to wait in seconds (default: 90)

    Raises
    ------
    TimeoutError
        If SSH container is not ready after timeout
    """
    behave_context = getattr(wait_for_ssh_container_ready, "_behave_context", None)
    harness = getattr(behave_context, "harness", None)

    if hasattr(harness, "wait_for_event"):
        try:
            harness.wait_for_event(
                event_type="ssh-ready",
                instance_id=instance_id,
                timeout_sec=float(timeout),
            )
            return
        except EventBusTimeoutError as error:
            raise TimeoutError(
                f"SSH container not ready for {instance_id} after {timeout}s"
            ) from error

    start = time.time()
    port_env_var = f"SSH_PORT_{instance_id}"
    key_file_env_var = f"SSH_KEY_FILE_{instance_id}"

    logger.info(f"Waiting for SSH container to be ready for {instance_id}...")

    while time.time() - start < timeout:
        if port_env_var in os.environ and key_file_env_var in os.environ:
            logger.info(f"SSH container ready for {instance_id} (port={os.environ[port_env_var]})")
            return
        time.sleep(0.5)

    raise TimeoutError(f"SSH container not ready for {instance_id} after {timeout}s")


def create_localstack_ec2_client() -> boto3.client:
    """Create EC2 client configured for LocalStack.

    Returns
    -------
    boto3.client
        Configured EC2 client for LocalStack
    """
    endpoint_url = os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566")
    return boto3.client(
        "ec2",
        endpoint_url=endpoint_url,
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    )


def wait_for_localstack_health(timeout: int = 60, interval: int = 5) -> None:
    """Poll the LocalStack health endpoint until it responds successfully.

    Parameters
    ----------
    timeout : int
        Maximum time to wait in seconds (default: 60)
    interval : int
        Time to wait between attempts in seconds (default: 5)

    Raises
    ------
    TimeoutError
        If LocalStack does not become healthy within the timeout period
    """
    start_time = time.time()
    endpoint = "http://localhost:4566/_localstack/health"

    while time.time() - start_time < timeout:
        try:
            response = requests.get(endpoint, timeout=2)

            if response.status_code == 200:
                logger.info("LocalStack health check passed")
                return
        except requests.exceptions.RequestException as e:
            logger.debug(f"LocalStack health check failed: {e}")

        time.sleep(interval)

    raise TimeoutError(f"LocalStack health check failed after {timeout} seconds")


def wait_for_ssh_ready(host: str, port: int, timeout: int = 30) -> bool:
    """Verify SSH daemon is accepting connections.

    Parameters
    ----------
    host : str
        SSH server hostname or IP address
    port : int
        SSH server port
    timeout : int
        Maximum time to wait in seconds (default: 30)

    Returns
    -------
    bool
        True if SSH daemon is ready, False if timeout exceeded
    """
    import socket

    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            sock.close()

            if result == 0:
                return True
        except Exception:
            pass

        time.sleep(0.5)

    return False


@given("LocalStack is healthy and responding")
def step_localstack_is_healthy(context: Context) -> None:
    """Verify that LocalStack is running and healthy.

    Parameters
    ----------
    context : Context
        Behave context object
    """
    is_localstack = hasattr(context, "scenario") and "localstack" in context.scenario.tags

    if not is_localstack:
        return

    services = get_localstack_services(context)

    wait_for_localstack_health()
    context.container_manager = services.container_manager
    wait_for_ssh_container_ready._behave_context = context  # type: ignore[attr-defined]
    ec2_client = create_localstack_ec2_client()

    try:
        paginator = ec2_client.get_paginator("describe_instances")
        page_iterator = paginator.paginate()

        instance_ids = []
        non_terminated = []

        for page in page_iterator:
            for reservation in page.get("Reservations", []):
                for instance in reservation["Instances"]:
                    instance_ids.append(instance["InstanceId"])
                    if instance["State"]["Name"] != "terminated":
                        non_terminated.append(instance["InstanceId"])

        if instance_ids:
            logger.info(f"Cleaning {len(instance_ids)} old instances from LocalStack (all states)")

            if non_terminated:
                ec2_client.terminate_instances(InstanceIds=non_terminated)
                logger.info(f"Terminated {len(non_terminated)} running instances")

            logger.info("LocalStack cleanup completed")
        else:
            logger.info("LocalStack already clean, no instances to terminate")
    except Exception as e:
        logger.warning(f"Failed to clean LocalStack: {e}")

    response = ec2_client.register_image(
        Name="Amazon Ubuntu 24 LTS x86_64 20240101",
        Description="Ubuntu 24.04 LTS (test image for LocalStack)",
        Architecture="x86_64",
        RootDeviceName="/dev/sda1",
        VirtualizationType="hvm",
    )
    ami_id = response.get("ImageId")
    logger.info(f"Registered test Ubuntu AMI in LocalStack with ID: {ami_id}")

    try:
        images_response = ec2_client.describe_images(ImageIds=[ami_id])
        logger.info(f"describe_images response: {images_response.get('Images', [])}")
        if images_response.get("Images"):
            img = images_response["Images"][0]
            img_name = img.get("Name", "unknown")
            img_arch = img.get("Architecture", "unknown")
            logger.info(f"Verified AMI exists with name: {img_name}, architecture: {img_arch}")
    except Exception as e:
        logger.warning(f"Failed to verify AMI: {e}")

    logger.info("LocalStackHarness monitor controller active; legacy monitor disabled")


@then('an EC2 instance was created in LocalStack with tag "{tag_key}" equal to "{tag_value}"')
def step_ec2_instance_created_with_tag(context: Context, tag_key: str, tag_value: str) -> None:
    """Verify that an EC2 instance was created with a specific tag.

    Parameters
    ----------
    context : Context
        Behave context object
    tag_key : str
        Tag key to check
    tag_value : str
        Expected tag value
    """
    ec2_client = create_localstack_ec2_client()

    response = ec2_client.describe_instances(
        Filters=[{"Name": f"tag:{tag_key}", "Values": [tag_value]}]
    )

    instances = []
    for reservation in response.get("Reservations", []):
        instances.extend(reservation.get("Instances", []))

    if not instances:
        all_instances = ec2_client.describe_instances()
        instance_count = sum(len(r["Instances"]) for r in all_instances["Reservations"])
        raise AssertionError(
            f"No EC2 instance found with tag {tag_key}={tag_value} in LocalStack. "
            f"Found {instance_count} total instances."
        )

    context.localstack_instance_id = instances[0]["InstanceId"]
    logger.info(f"Found instance {context.localstack_instance_id} with tag {tag_key}={tag_value}")


@then('that instance has tag "{tag_key}" equal to "{tag_value}"')
def step_instance_has_tag(context: Context, tag_key: str, tag_value: str) -> None:
    """Verify that the previously found instance has a specific tag.

    Parameters
    ----------
    context : Context
        Behave context object
    tag_key : str
        Tag key to check
    tag_value : str
        Expected tag value
    """
    if not hasattr(context, "localstack_instance_id"):
        raise AssertionError(
            "No instance found in context. Run the 'an EC2 instance was created' step first."
        )

    ec2_client = create_localstack_ec2_client()

    response = ec2_client.describe_instances(InstanceIds=[context.localstack_instance_id])

    instances = []
    for reservation in response.get("Reservations", []):
        instances.extend(reservation.get("Instances", []))

    if not instances:
        all_instances = ec2_client.describe_instances()
        instance_count = sum(len(r["Instances"]) for r in all_instances["Reservations"])
        raise AssertionError(
            f"Instance {context.localstack_instance_id} not found in LocalStack. "
            f"Found {instance_count} total instances."
        )

    instance = instances[0]
    tags = {tag["Key"]: tag["Value"] for tag in instance.get("Tags", [])}

    if tag_key not in tags:
        available_tags = ", ".join(tags.keys()) if tags else "no tags"
        raise AssertionError(
            f"Instance {context.localstack_instance_id} does not have tag '{tag_key}'. "
            f"Available tags: {available_tags}"
        )

    if tags[tag_key] != tag_value:
        raise AssertionError(
            f"Instance {context.localstack_instance_id} has tag {tag_key}={tags[tag_key]}, "
            f"expected {tag_value}"
        )

    logger.info(f"Instance {context.localstack_instance_id} has tag {tag_key}={tag_value}")


@then('that instance is in "{expected_state}" state')
def step_instance_is_in_state(context: Context, expected_state: str) -> None:
    """Verify that the previously found instance is in a specific state.

    Parameters
    ----------
    context : Context
        Behave context object
    expected_state : str
        Expected instance state (e.g., "running", "terminated")
    """
    if not hasattr(context, "localstack_instance_id"):
        raise AssertionError(
            "No instance found in context. Run the 'an EC2 instance was created' step first."
        )

    ec2_client = create_localstack_ec2_client()

    response = ec2_client.describe_instances(InstanceIds=[context.localstack_instance_id])

    instances = []
    for reservation in response.get("Reservations", []):
        instances.extend(reservation.get("Instances", []))

    if not instances:
        raise AssertionError(f"Instance {context.localstack_instance_id} not found in LocalStack")

    instance = instances[0]
    actual_state = instance["State"]["Name"]

    if actual_state != expected_state:
        instance_id = context.localstack_instance_id
        raise AssertionError(
            f"Instance {instance_id} is in state '{actual_state}', expected '{expected_state}'"
        )

    logger.info(f"Instance {context.localstack_instance_id} is in state '{actual_state}'")
