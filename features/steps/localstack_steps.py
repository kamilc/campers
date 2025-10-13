"""LocalStack-specific BDD step definitions."""

import logging
import os
import threading
import time

import boto3
import requests
from behave import given, then
from behave.runner import Context

from features.steps.docker_manager import EC2ContainerManager

logger = logging.getLogger(__name__)

LOCALSTACK_MONITOR_POLL_INTERVAL = 0.5


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


def monitor_localstack_instances(
    container_manager: EC2ContainerManager, stop_event: threading.Event
) -> None:
    """Monitor LocalStack for new EC2 instances and create SSH containers.

    Parameters
    ----------
    container_manager : EC2ContainerManager
        Container manager instance
    stop_event : threading.Event
        Event to signal thread should stop
    """
    logger.info("Monitor thread started and beginning to poll")
    ec2_client = create_localstack_ec2_client()
    seen_instances = set()

    while not stop_event.is_set():
        try:
            response = ec2_client.describe_instances()

            for reservation in response.get("Reservations", []):
                for instance in reservation.get("Instances", []):
                    instance_id = instance["InstanceId"]
                    state = instance["State"]["Name"]

                    if instance_id not in seen_instances and state in [
                        "pending",
                        "running",
                    ]:
                        logger.info(
                            f"Detected new instance {instance_id} (state: {state}), creating SSH container"
                        )
                        port, key_file = container_manager.create_instance_container(
                            instance_id
                        )
                        os.environ[f"SSH_PORT_{instance_id}"] = str(port)
                        os.environ[f"SSH_KEY_FILE_{instance_id}"] = str(key_file)
                        seen_instances.add(instance_id)
                        logger.info(
                            f"Created SSH container for {instance_id} on port {port} with key {key_file}"
                        )
                        logger.debug(
                            f"Environment vars set: SSH_PORT_{instance_id}={port}, SSH_KEY_FILE_{instance_id}={key_file}"
                        )
        except Exception as e:
            logger.error(f"Error monitoring LocalStack instances: {e}", exc_info=True)

        time.sleep(LOCALSTACK_MONITOR_POLL_INTERVAL)

    logger.info("Monitor thread stopped")


@given("LocalStack is healthy and responding")
def step_localstack_is_healthy(context: Context) -> None:
    """Verify that LocalStack is running and healthy.

    Parameters
    ----------
    context : Context
        Behave context object
    """
    wait_for_localstack_health()
    context.container_manager = EC2ContainerManager()
    ec2_client = create_localstack_ec2_client()
    ec2_client.register_image(
        Name="ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-20231201",
        Description="Ubuntu 22.04 LTS (test image for LocalStack)",
        Architecture="x86_64",
        RootDeviceName="/dev/sda1",
        VirtualizationType="hvm",
    )
    logger.info("Registered test Ubuntu AMI in LocalStack")

    stop_event = threading.Event()
    monitor_thread = threading.Thread(
        target=monitor_localstack_instances,
        args=(context.container_manager, stop_event),
        daemon=True,
    )
    monitor_thread.start()
    context.monitor_thread = monitor_thread
    context.monitor_stop_event = stop_event
    logger.info("Started LocalStack instance monitor thread")


@then(
    'an EC2 instance was created in LocalStack with tag "{tag_key}" equal to "{tag_value}"'
)
def step_ec2_instance_created_with_tag(
    context: Context, tag_key: str, tag_value: str
) -> None:
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
    logger.info(
        f"Found instance {context.localstack_instance_id} with tag {tag_key}={tag_value}"
    )


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

    response = ec2_client.describe_instances(
        InstanceIds=[context.localstack_instance_id]
    )

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

    logger.info(
        f"Instance {context.localstack_instance_id} has tag {tag_key}={tag_value}"
    )


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

    response = ec2_client.describe_instances(
        InstanceIds=[context.localstack_instance_id]
    )

    instances = []
    for reservation in response.get("Reservations", []):
        instances.extend(reservation.get("Instances", []))

    if not instances:
        raise AssertionError(
            f"Instance {context.localstack_instance_id} not found in LocalStack"
        )

    instance = instances[0]
    actual_state = instance["State"]["Name"]

    if actual_state != expected_state:
        raise AssertionError(
            f"Instance {context.localstack_instance_id} is in state '{actual_state}', expected '{expected_state}'"
        )

    logger.info(
        f"Instance {context.localstack_instance_id} is in state '{actual_state}'"
    )
