"""LocalStack-specific BDD step definitions."""

import logging
import os
import queue
import threading
import time

import boto3
import requests
from behave import given, then
from behave.runner import Context

from features.steps.docker_manager import EC2ContainerManager
from features.steps.pilot_steps import get_tui_update_queue

logger = logging.getLogger(__name__)

LOCALSTACK_MONITOR_POLL_INTERVAL = 0.5


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
    start = time.time()
    port_env_var = f"SSH_PORT_{instance_id}"
    key_file_env_var = f"SSH_KEY_FILE_{instance_id}"

    logger.info(f"Waiting for SSH container to be ready for {instance_id}...")

    while time.time() - start < timeout:
        if port_env_var in os.environ and key_file_env_var in os.environ:
            logger.info(
                f"SSH container ready for {instance_id} (port={os.environ[port_env_var]}, key={os.environ[key_file_env_var]})"
            )
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


def monitor_localstack_instances(
    container_manager: EC2ContainerManager,
    stop_event: threading.Event,
    context: Context,
    update_queue: queue.Queue | None = None,
) -> None:
    """Monitor LocalStack for new EC2 instances and create SSH containers.

    This monitor continuously polls LocalStack EC2 API for instances. It supports
    two detection modes:
    1. Target-specific: When instance IDs are registered via queue or environment
       variable (MOONDOCK_TARGET_INSTANCE_IDS), only those instances are monitored.
    2. Universal: When no target IDs are available, ALL instances in LocalStack
       are detected (since LocalStack is cleaned before each test).

    When an instance reaches 'pending' or 'running' state, it provisions a
    corresponding SSH container.

    Parameters
    ----------
    container_manager : EC2ContainerManager
        Container manager instance for creating Docker containers
    stop_event : threading.Event
        Event to signal thread should stop
    context : Context
        Behave context object for error reporting
    update_queue : queue.Queue | None
        Optional queue for receiving instance registrations from TUI (default: None)
    """
    logger.info("Monitor thread started and beginning to poll")
    ec2_client = create_localstack_ec2_client()
    seen_instances = set()
    target_instance_ids_from_queue = set()

    while not stop_event.is_set():
        try:
            if update_queue is not None:
                try:
                    while True:
                        msg = update_queue.get_nowait()
                        if msg.get("type") == "instance_registered":
                            instance_id = msg["payload"]["instance_id"]
                            target_instance_ids_from_queue.add(instance_id)
                            logger.info(
                                f"Monitor: Received instance {instance_id} from queue"
                            )
                except queue.Empty:
                    pass

            target_ids_env = os.environ.get("MOONDOCK_TARGET_INSTANCE_IDS", "")
            target_instance_ids = {
                id.strip() for id in target_ids_env.split(",") if id.strip()
            }
            target_instance_ids.update(target_instance_ids_from_queue)

            if target_instance_ids:
                logger.debug(
                    f"Monitor thread: Target IDs from env: '{target_ids_env}' -> parsed: {target_instance_ids}"
                )

            try:
                if target_instance_ids:
                    paginator = ec2_client.get_paginator("describe_instances")
                    page_iterator = paginator.paginate(
                        InstanceIds=list(target_instance_ids)
                    )
                else:
                    paginator = ec2_client.get_paginator("describe_instances")
                    page_iterator = paginator.paginate(
                        Filters=[
                            {
                                "Name": "instance-state-name",
                                "Values": ["pending", "running"],
                            }
                        ]
                    )
            except Exception as e:
                if "InvalidInstanceID.NotFound" in str(e):
                    time.sleep(LOCALSTACK_MONITOR_POLL_INTERVAL)
                    continue
                else:
                    logger.error(
                        f"Error querying instances: {e}",
                        exc_info=True,
                    )
                    time.sleep(LOCALSTACK_MONITOR_POLL_INTERVAL)
                    continue

            for page in page_iterator:
                for reservation in page.get("Reservations", []):
                    for instance in reservation.get("Instances", []):
                        instance_id = instance["InstanceId"]
                        state = instance["State"]["Name"]

                        if (
                            target_instance_ids
                            and instance_id not in target_instance_ids
                        ):
                            continue

                        if instance_id not in seen_instances and state in [
                            "pending",
                            "running",
                        ]:
                            logger.info(
                                f"Detected new instance {instance_id} (state: {state}), creating SSH container"
                            )

                            try:
                                port, key_file = (
                                    container_manager.create_instance_container(
                                        instance_id
                                    )
                                )

                                if port is not None:
                                    os.environ[f"SSH_PORT_{instance_id}"] = str(port)
                                    os.environ[f"SSH_KEY_FILE_{instance_id}"] = str(
                                        key_file
                                    )
                                    os.environ[f"SSH_READY_{instance_id}"] = "1"

                                    ec2_client.create_tags(
                                        Resources=[instance_id],
                                        Tags=[
                                            {
                                                "Key": "MoondockSSHHost",
                                                "Value": "localhost",
                                            },
                                            {
                                                "Key": "MoondockSSHPort",
                                                "Value": str(port),
                                            },
                                            {
                                                "Key": "MoondockSSHKeyFile",
                                                "Value": str(key_file),
                                            },
                                        ],
                                    )
                                    logger.info(
                                        f"Tagged instance {instance_id} with SSH connection info (localhost:{port})"
                                    )

                                    seen_instances.add(instance_id)

                                    context.instance_id = instance_id

                                    from features.steps.port_forwarding_steps import (
                                        start_http_servers_for_all_configured_ports,
                                    )

                                    logger.info(
                                        f"Monitor thread: Starting HTTP servers for all configured ports for {instance_id}"
                                    )
                                    start_http_servers_for_all_configured_ports(context)
                                    logger.info(
                                        f"Monitor thread: HTTP servers started successfully for {instance_id}"
                                    )

                                    os.environ[f"HTTP_SERVERS_READY_{instance_id}"] = (
                                        "1"
                                    )
                                    logger.info(
                                        f"SSH container ready for {instance_id} (port={port}), HTTP servers started"
                                    )
                                else:
                                    os.environ[f"SSH_PORT_{instance_id}"] = "65535"
                                    os.environ[f"SSH_KEY_FILE_{instance_id}"] = str(
                                        key_file
                                    )
                                    os.environ[f"SSH_READY_{instance_id}"] = "1"

                                    ec2_client.create_tags(
                                        Resources=[instance_id],
                                        Tags=[
                                            {
                                                "Key": "MoondockSSHHost",
                                                "Value": "blocked",
                                            },
                                            {
                                                "Key": "MoondockSSHPort",
                                                "Value": "65535",
                                            },
                                            {
                                                "Key": "MoondockSSHKeyFile",
                                                "Value": str(key_file),
                                            },
                                        ],
                                    )

                                    seen_instances.add(instance_id)
                                    logger.info(
                                        f"Monitor thread: Container for {instance_id} created WITHOUT port mapping (blocked)"
                                    )
                            except Exception as e:
                                logger.error(
                                    f"Monitor thread: Failed to create container for {instance_id}: {e}",
                                    exc_info=True,
                                )
                                logger.error(f"Instance state was: {state}")
                                logger.error(f"Instance details: {instance}")

                                os.environ[f"MONITOR_ERROR_{instance_id}"] = str(e)
                                if hasattr(context, "monitor_error"):
                                    context.monitor_error = str(e)
        except Exception as e:
            logger.error(f"Exception in monitor loop: {e}", exc_info=True)
            import traceback

            logger.error(f"Full traceback:\n{traceback.format_exc()}")

            if hasattr(context, "monitor_error"):
                context.monitor_error = str(e)

        time.sleep(LOCALSTACK_MONITOR_POLL_INTERVAL)

    logger.info("Monitor thread stopped")


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
    wait_for_localstack_health()

    ssh_port = 2222
    if not wait_for_ssh_ready("localhost", ssh_port, timeout=30):
        logger.warning(
            f"LocalStack SSH daemon not ready on port {ssh_port} after 30s - "
            f"tests may fail due to SSH connection timeouts"
        )

    context.container_manager = EC2ContainerManager()
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
            logger.info(
                f"Cleaning {len(instance_ids)} old instances from LocalStack (all states): {instance_ids}"
            )

            if non_terminated:
                ec2_client.terminate_instances(InstanceIds=non_terminated)
                logger.info(f"Terminated {len(non_terminated)} running instances")

            logger.info("LocalStack cleanup completed")
        else:
            logger.info("LocalStack already clean, no instances to terminate")
    except Exception as e:
        logger.warning(f"Failed to clean LocalStack: {e}")

    os.environ["MOONDOCK_TARGET_INSTANCE_IDS"] = ""
    context.target_instance_ids = set()
    context.monitor_error = None

    ec2_client.register_image(
        Name="ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-20231201",
        Description="Ubuntu 22.04 LTS (test image for LocalStack)",
        Architecture="x86_64",
        RootDeviceName="/dev/sda1",
        VirtualizationType="hvm",
    )
    logger.info("Registered test Ubuntu AMI in LocalStack")

    stop_event = threading.Event()

    tui_queue = get_tui_update_queue()
    if tui_queue is not None:
        logger.info("Found TUI update queue, will use for instance registration")

    monitor_thread = threading.Thread(
        target=monitor_localstack_instances,
        args=(context.container_manager, stop_event, context, tui_queue),
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
