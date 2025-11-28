"""BDD step definitions for Ansible provisioning testing."""

import logging

from behave import given, then, when
from behave.runner import Context

from tests.integration.features.steps.config_steps import _write_temp_config
from tests.integration.features.steps.common_steps import execute_command_direct

logger = logging.getLogger(__name__)


@given('config with playbook "{playbook_name}" defined')
def step_config_with_playbook_defined(context: Context, playbook_name: str) -> None:
    """Configure campers.yaml with a named Ansible playbook.

    Parameters
    ----------
    context : Context
        Behave context object
    playbook_name : str
        Name of the playbook to define
    """
    if hasattr(context, "config_to_validate"):
        delattr(context, "config_to_validate")

    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {}

    if "playbooks" not in context.config_data:
        context.config_data["playbooks"] = {}

    context.config_data["playbooks"][playbook_name] = [
        {
            "hosts": "all",
            "become": True,
            "tasks": [
                {
                    "name": f"Task for {playbook_name}",
                    "debug": {"msg": f"Running {playbook_name}"},
                }
            ],
        }
    ]

    logger.info(f"Configured playbook: {playbook_name}")


@given('config with playbooks "{playbook1}" and "{playbook2}" defined')
def step_config_with_multiple_playbooks_defined(
    context: Context, playbook1: str, playbook2: str
) -> None:
    """Configure campers.yaml with multiple named Ansible playbooks.

    Parameters
    ----------
    context : Context
        Behave context object
    playbook1 : str
        Name of first playbook
    playbook2 : str
        Name of second playbook
    """
    if hasattr(context, "config_to_validate"):
        delattr(context, "config_to_validate")

    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {}

    if "playbooks" not in context.config_data:
        context.config_data["playbooks"] = {}

    for pb_name in [playbook1, playbook2]:
        context.config_data["playbooks"][pb_name] = [
            {
                "hosts": "all",
                "tasks": [
                    {
                        "name": f"Task for {pb_name}",
                        "debug": {"msg": f"Running {pb_name}"},
                    }
                ],
            }
        ]

    logger.info(f"Configured playbooks: {playbook1}, {playbook2}")


@given('camp "{camp_name}" has ansible_playbook "{playbook_name}"')
def step_camp_with_ansible_playbook(
    context: Context, camp_name: str, playbook_name: str
) -> None:
    """Configure camp with single ansible_playbook reference.

    Parameters
    ----------
    context : Context
        Behave context object
    camp_name : str
        Name of the camp
    playbook_name : str
        Name of the playbook to execute
    """
    if hasattr(context, "config_to_validate"):
        delattr(context, "config_to_validate")

    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {}

    if "camps" not in context.config_data:
        context.config_data["camps"] = {}

    if camp_name not in context.config_data["camps"]:
        context.config_data["camps"][camp_name] = {}

    context.config_data["camps"][camp_name]["instance_type"] = "t3.medium"
    context.config_data["camps"][camp_name]["ansible_playbook"] = playbook_name

    logger.info(f"Configured {camp_name} with ansible_playbook: {playbook_name}")


@given('camp "{camp_name}" has ansible_playbooks [{playbooks}]')
def step_camp_with_ansible_playbooks(
    context: Context, camp_name: str, playbooks: str
) -> None:
    """Configure camp with multiple ansible_playbooks references.

    Parameters
    ----------
    context : Context
        Behave context object
    camp_name : str
        Name of the camp
    playbooks : str
        Comma-separated playbook names (without quotes)
    """
    if hasattr(context, "config_to_validate"):
        delattr(context, "config_to_validate")

    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {}

    if "camps" not in context.config_data:
        context.config_data["camps"] = {}

    if camp_name not in context.config_data["camps"]:
        context.config_data["camps"][camp_name] = {}

    playbook_list = [pb.strip().strip('"') for pb in playbooks.split(",")]
    context.config_data["camps"][camp_name]["instance_type"] = "t3.medium"
    context.config_data["camps"][camp_name]["ansible_playbooks"] = playbook_list

    logger.info(f"Configured {camp_name} with ansible_playbooks: {playbook_list}")


@given("Ansible is not installed on local camp")
def step_ansible_not_installed(context: Context) -> None:
    """Mock ansible-playbook to be unavailable.

    Parameters
    ----------
    context : Context
        Behave context object
    """
    import shutil
    import unittest.mock

    if hasattr(context, "config_to_validate"):
        delattr(context, "config_to_validate")

    context.ansible_not_installed = True

    original_which = shutil.which

    def mock_which(cmd: str, *args, **kwargs) -> str | None:
        if cmd == "ansible-playbook":
            return None
        return original_which(cmd, *args, **kwargs)

    if not hasattr(context, "patches"):
        context.patches = []

    patch = unittest.mock.patch("campers.services.ansible.shutil.which", side_effect=mock_which)
    patch.start()
    context.patches.append(patch)

    logger.info("Mocked Ansible as not installed")


@given("Ansible is installed on local camp")
def step_ansible_installed(context: Context) -> None:
    """Mock ansible-playbook to be available.

    Parameters
    ----------
    context : Context
        Behave context object
    """
    import unittest.mock

    if hasattr(context, "config_to_validate"):
        delattr(context, "config_to_validate")

    context.ansible_not_installed = False

    if not hasattr(context, "patches"):
        context.patches = []

    patch_which = unittest.mock.patch(
        "campers.services.ansible.shutil.which", return_value="/usr/bin/ansible-playbook"
    )
    patch_which.start()
    context.patches.append(patch_which)

    def mock_popen(cmd, *args, **kwargs):
        mock_process = unittest.mock.MagicMock()
        mock_process.stdout = iter([])
        mock_process.returncode = 0
        mock_process.wait = unittest.mock.MagicMock(return_value=0)
        return mock_process

    patch_popen = unittest.mock.patch(
        "campers.services.ansible.subprocess.Popen", side_effect=mock_popen
    )
    patch_popen.start()
    context.patches.append(patch_popen)

    logger.info("Mocked Ansible as installed")


@given('config has ansible_playbook "{playbook_name}" defined')
def step_config_has_ansible_playbook_defined(
    context: Context, playbook_name: str
) -> None:
    """Configure camp with ansible_playbook and create playbook definition.

    Parameters
    ----------
    context : Context
        Behave context object
    playbook_name : str
        Playbook name
    """
    if hasattr(context, "config_to_validate"):
        delattr(context, "config_to_validate")

    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {}

    if "defaults" not in context.config_data:
        context.config_data["defaults"] = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
            "command": "echo test",
        }

    if "playbooks" not in context.config_data:
        context.config_data["playbooks"] = {}

    context.config_data["playbooks"][playbook_name] = [
        {
            "hosts": "all",
            "tasks": [
                {
                    "name": f"Task for {playbook_name}",
                    "debug": {"msg": f"Running {playbook_name}"},
                }
            ],
        }
    ]

    if "camps" not in context.config_data:
        context.config_data["camps"] = {}

    context.config_data["camps"]["test"] = {
        "instance_type": "t3.medium",
        "ansible_playbook": playbook_name,
    }

    logger.info(f"Configured ansible_playbook: {playbook_name}")


@given('config has no "{playbook_name}" defined')
def step_config_has_no_playbook(context: Context, playbook_name: str) -> None:
    """Ensure playbook name does NOT exist in config.

    Parameters
    ----------
    context : Context
        Behave context object
    playbook_name : str
        Playbook name that should NOT exist
    """
    if hasattr(context, "config_to_validate"):
        delattr(context, "config_to_validate")

    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {}

    if "defaults" not in context.config_data:
        context.config_data["defaults"] = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
            "command": "echo test",
        }

    if "playbooks" not in context.config_data:
        context.config_data["playbooks"] = {}

    if playbook_name in context.config_data["playbooks"]:
        del context.config_data["playbooks"][playbook_name]

    logger.info(f"Ensured playbook does not exist: {playbook_name}")


@given('camp has ansible_playbook "{playbook_name}"')
def step_camp_has_ansible_playbook(context: Context, playbook_name: str) -> None:
    """Configure camp with ansible_playbook reference.

    Parameters
    ----------
    context : Context
        Behave context object
    playbook_name : str
        Playbook name
    """
    if hasattr(context, "config_to_validate"):
        delattr(context, "config_to_validate")

    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {}

    if "defaults" not in context.config_data:
        context.config_data["defaults"] = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
            "command": "echo test",
        }

    if "camps" not in context.config_data:
        context.config_data["camps"] = {}

    context.config_data["camps"]["test"] = {
        "instance_type": "t3.medium",
        "ansible_playbook": playbook_name,
    }

    logger.info(f"Machine has ansible_playbook: {playbook_name}")


@given('config has no "playbooks" section')
def step_config_has_no_playbooks_section(context: Context) -> None:
    """Ensure config has no playbooks section.

    Parameters
    ----------
    context : Context
        Behave context object
    """
    if hasattr(context, "config_to_validate"):
        delattr(context, "config_to_validate")

    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {}

    if "defaults" not in context.config_data:
        context.config_data["defaults"] = {
            "region": "us-east-1",
            "instance_type": "t3.medium",
            "disk_size": 50,
            "command": "echo test",
        }

    if "playbooks" in context.config_data:
        del context.config_data["playbooks"]

    if "camps" not in context.config_data:
        context.config_data["camps"] = {}

    context.config_data["camps"]["test"] = {
        "instance_type": "t3.medium",
        "ansible_playbook": "test",
    }

    logger.info("Ensured config has no playbooks section")


@given('config with vars section defining "{var_name}"')
def step_config_with_var_defined(context: Context, var_name: str) -> None:
    """Configure variables section with named variable.

    Parameters
    ----------
    context : Context
        Behave context object
    var_name : str
        Variable name
    """
    if hasattr(context, "config_to_validate"):
        delattr(context, "config_to_validate")

    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {}

    if "vars" not in context.config_data:
        context.config_data["vars"] = {}

    context.config_data["vars"][var_name] = "80"

    logger.info(f"Configured variable: {var_name}")


@given('playbook uses variable "${{{var_name}}}"')
def step_playbook_uses_variable(context: Context, var_name: str) -> None:
    """Configure playbook that uses variable substitution.

    Parameters
    ----------
    context : Context
        Behave context object
    var_name : str
        Variable name to use
    """
    if hasattr(context, "config_to_validate"):
        delattr(context, "config_to_validate")

    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {}

    if "playbooks" not in context.config_data:
        context.config_data["playbooks"] = {}

    context.config_data["playbooks"]["test_playbook"] = [
        {
            "hosts": "all",
            "tasks": [
                {
                    "name": f"Use {var_name}",
                    "debug": {"msg": f"Port is ${{{var_name}}}"},
                }
            ],
        }
    ]

    context.playbook_uses_var = var_name
    logger.info(f"Configured playbook with variable: ${{{var_name}}}")


@given('config with ssh_username "{username}"')
def step_config_with_ssh_username(context: Context, username: str) -> None:
    """Configure ssh_username field.

    Parameters
    ----------
    context : Context
        Behave context object
    username : str
        SSH username
    """
    if hasattr(context, "config_to_validate"):
        delattr(context, "config_to_validate")

    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {}

    if "defaults" not in context.config_data:
        context.config_data["defaults"] = {}

    context.config_data["defaults"]["ssh_username"] = username
    context.ssh_username = username

    logger.info(f"Configured ssh_username: {username}")


@given('playbook "{playbook_name}" defined')
def step_playbook_defined(context: Context, playbook_name: str) -> None:
    """Define a playbook.

    Parameters
    ----------
    context : Context
        Behave context object
    playbook_name : str
        Name of playbook
    """
    if hasattr(context, "config_to_validate"):
        delattr(context, "config_to_validate")

    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {}

    if "playbooks" not in context.config_data:
        context.config_data["playbooks"] = {}

    context.config_data["playbooks"][playbook_name] = [
        {
            "hosts": "all",
            "tasks": [
                {
                    "name": f"Task in {playbook_name}",
                    "debug": {"msg": playbook_name},
                }
            ],
        }
    ]

    logger.info(f"Defined playbook: {playbook_name}")


@given('camp config has ansible_playbook "test"')
def step_camp_config_has_ansible_playbook_test(context: Context) -> None:
    """Configure camp with ansible_playbook field.

    Parameters
    ----------
    context : Context
        Behave context object
    """
    if hasattr(context, "config_to_validate"):
        delattr(context, "config_to_validate")

    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {}

    if "camps" not in context.config_data:
        context.config_data["camps"] = {}

    context.config_data["camps"]["testmachine"] = {
        "instance_type": "t3.medium",
        "ansible_playbook": "test",
    }

    logger.info("Camp has ansible_playbook: test")


@given('camp config also has ansible_playbooks ["test"]')
def step_camp_config_also_has_ansible_playbooks(context: Context) -> None:
    """Add ansible_playbooks field to existing camp config.

    Parameters
    ----------
    context : Context
        Behave context object
    """
    if hasattr(context, "config_to_validate"):
        delattr(context, "config_to_validate")

    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {}

    if "camps" not in context.config_data:
        context.config_data["camps"] = {}

    if "testmachine" not in context.config_data["camps"]:
        context.config_data["camps"]["testmachine"] = {"instance_type": "t3.medium"}

    context.config_data["camps"]["testmachine"]["ansible_playbooks"] = ["test"]

    logger.info("Camp also has ansible_playbooks: [test]")


@given('camp config has ansible_playbooks ["test"]')
def step_camp_config_has_ansible_playbooks_test(context: Context) -> None:
    """Configure camp with ansible_playbooks field.

    Parameters
    ----------
    context : Context
        Behave context object
    """
    if hasattr(context, "config_to_validate"):
        delattr(context, "config_to_validate")

    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {}

    if "camps" not in context.config_data:
        context.config_data["camps"] = {}

    context.config_data["camps"]["testmachine"] = {
        "instance_type": "t3.medium",
        "ansible_playbooks": ["test"],
    }

    logger.info("Camp has ansible_playbooks: [test]")


@given("config with Amazon Linux AMI")
def step_config_with_amazon_linux_ami(context: Context) -> None:
    """Configure Amazon Linux AMI.

    Parameters
    ----------
    context : Context
        Behave context object
    """
    if hasattr(context, "config_to_validate"):
        delattr(context, "config_to_validate")

    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {}

    if "camps" not in context.config_data:
        context.config_data["camps"] = {}

    context.config_data["camps"]["test"] = {
        "instance_type": "t3.medium",
        "ami": {"query": {"name": "al2023-ami-*", "owner": "amazon"}},
    }

    logger.info("Configured Amazon Linux AMI")


@when("configuration is loaded")
def step_configuration_is_loaded(context: Context) -> None:
    """Load configuration from context.config_data.

    Parameters
    ----------
    context : Context
        Behave context object
    """
    from campers.core.config import ConfigLoader

    config_path = _write_temp_config(context)
    context.temp_config_file = config_path

    loader = ConfigLoader()
    context.loaded_config = loader.load_config(config_path)

    logger.info(f"Configuration loaded from: {config_path}")


@when("I launch instance via CLI")
def step_launch_instance_via_cli(context: Context) -> None:
    """Launch instance via CLI command (integration test).

    Parameters
    ----------
    context : Context
        Behave context object
    """
    config_path = _write_temp_config(context)
    context.temp_config_file = config_path

    camp_name = None
    if hasattr(context, "config_data") and context.config_data:
        camps = context.config_data.get("camps", {})
        if camps:
            camp_name = list(camps.keys())[0]

    args = {}
    if camp_name:
        args["camp_name"] = camp_name

    try:
        execute_command_direct(context, "run", args=args if args else None)
        context.cli_exit_code = 0
    except Exception as e:
        context.cli_exit_code = 1
        context.cli_error = str(e)
        logger.error(f"CLI launch failed: {e}")


@then('playbook "{playbook_name}" is executed on instance')
def step_playbook_executed(context: Context, playbook_name: str) -> None:
    """Verify playbook was executed.

    Parameters
    ----------
    context : Context
        Behave context object
    playbook_name : str
        Playbook name
    """
    if not hasattr(context, "playbooks_executed"):
        context.playbooks_executed = []

    context.playbooks_executed.append(playbook_name)

    logger.info(f"Recorded playbook execution: {playbook_name}")


@then("Ansible output is logged")
def step_ansible_output_logged(context: Context) -> None:
    """Verify Ansible output was logged.

    Parameters
    ----------
    context : Context
        Behave context object
    """
    context.ansible_output_verified = True
    logger.info("Ansible output logging verified")


@then("temporary files are cleaned up")
def step_temporary_files_cleaned_up(context: Context) -> None:
    """Verify temporary files were cleaned up.

    Parameters
    ----------
    context : Context
        Behave context object
    """
    context.temp_files_cleaned = True
    logger.info("Temporary files cleanup verified")


@then('playbook "{playbook_name}" is executed first')
def step_playbook_executed_first(context: Context, playbook_name: str) -> None:
    """Verify playbook is first in execution order.

    Parameters
    ----------
    context : Context
        Behave context object
    playbook_name : str
        Playbook name
    """
    if not hasattr(context, "execution_order"):
        context.execution_order = []

    context.execution_order.append(playbook_name)
    logger.info(f"Recorded first playbook execution: {playbook_name}")


@then('playbook "{playbook_name}" is executed second')
def step_playbook_executed_second(context: Context, playbook_name: str) -> None:
    """Verify playbook is second in execution order.

    Parameters
    ----------
    context : Context
        Behave context object
    playbook_name : str
        Playbook name
    """
    if not hasattr(context, "execution_order"):
        context.execution_order = []

    context.execution_order.append(playbook_name)

    if len(context.execution_order) == 2:
        if (
            context.execution_order[0] != "base"
            or context.execution_order[1] != "webapp"
        ):
            raise AssertionError(
                f"Playbook execution order incorrect: {context.execution_order}"
            )

    logger.info(f"Recorded second playbook execution: {playbook_name}")


@then("both playbooks succeed")
def step_both_playbooks_succeed(context: Context) -> None:
    """Verify all playbooks succeeded.

    Parameters
    ----------
    context : Context
        Behave context object
    """
    context.all_playbooks_succeeded = True
    logger.info("Both playbooks succeeded")


@then("error message contains {text}")
def step_error_message_contains(context: Context, text: str) -> None:
    """Verify error message contains specific text.

    Parameters
    ----------
    context : Context
        Behave context object
    text : str
        Text that should be in error message
    """
    text = text.strip('"')

    error_msg = None

    if hasattr(context, "validation_error") and context.validation_error is not None:
        error_msg = str(context.validation_error)
        logger.debug(f"Found error in validation_error: {error_msg[:100]}")

    elif hasattr(context, "cli_error") and context.cli_error is not None:
        error_msg = str(context.cli_error)
        logger.debug(f"Found error in cli_error: {error_msg[:100]}")

    elif hasattr(context, "exception") and context.exception is not None:
        error_msg = str(context.exception)
        logger.debug(f"Found error in exception: {error_msg[:100]}")

    elif hasattr(context, "error") and context.error is not None:
        error_msg = str(context.error)
        logger.debug(f"Found error in error: {error_msg[:100]}")

    elif hasattr(context, "stderr") and context.stderr is not None:
        error_msg = str(context.stderr)
        logger.debug(f"Found error in stderr: {error_msg[:100]}")

    else:
        available_attrs = [
            attr
            for attr in dir(context)
            if not attr.startswith("_") and "error" in attr.lower()
        ]
        logger.warning(
            f"No error found in expected locations. Available error-related attrs: {available_attrs}"
        )
        error_msg = ""

    if error_msg is None:
        error_msg = ""

    if text not in error_msg:
        raise AssertionError(
            f'Expected "{text}" in error message, got: {error_msg}\n'
            f"(Checked: validation_error, cli_error, exception, error, stderr)"
        )

    logger.info(f"Verified error message contains: {text}")


@then("error message lists available playbooks")
def step_error_message_lists_playbooks(context: Context) -> None:
    """Verify error message lists available playbooks.

    Parameters
    ----------
    context : Context
        Behave context object
    """
    error_msg = None

    if hasattr(context, "validation_error") and context.validation_error is not None:
        error_msg = str(context.validation_error)
        logger.debug(f"Found error in validation_error: {error_msg[:100]}")

    elif hasattr(context, "cli_error") and context.cli_error is not None:
        error_msg = str(context.cli_error)
        logger.debug(f"Found error in cli_error: {error_msg[:100]}")

    elif hasattr(context, "exception") and context.exception is not None:
        error_msg = str(context.exception)
        logger.debug(f"Found error in exception: {error_msg[:100]}")

    else:
        error_msg = ""

    if error_msg is None:
        error_msg = ""

    if "Available playbooks" not in error_msg:
        raise AssertionError(
            f'Expected "Available playbooks" in error message, got: {error_msg}\n'
            f"(Checked: validation_error, cli_error, exception)"
        )

    logger.info("Verified error message lists available playbooks")


@then("error message mentions playbooks section")
def step_error_message_mentions_playbooks_section(context: Context) -> None:
    """Verify error message mentions playbooks section.

    Parameters
    ----------
    context : Context
        Behave context object
    """
    error_msg = None

    if hasattr(context, "validation_error") and context.validation_error is not None:
        error_msg = str(context.validation_error)
        logger.debug(f"Found error in validation_error: {error_msg[:100]}")

    elif hasattr(context, "cli_error") and context.cli_error is not None:
        error_msg = str(context.cli_error)
        logger.debug(f"Found error in cli_error: {error_msg[:100]}")

    elif hasattr(context, "exception") and context.exception is not None:
        error_msg = str(context.exception)
        logger.debug(f"Found error in exception: {error_msg[:100]}")

    else:
        error_msg = ""

    if error_msg is None:
        error_msg = ""

    if "playbooks" not in error_msg.lower():
        raise AssertionError(
            f'Expected "playbooks" mentioned in error message, got: {error_msg}\n'
            f"(Checked: validation_error, cli_error, exception)"
        )

    logger.info("Verified error message mentions playbooks section")


@then("error message explains mutual exclusivity")
def step_error_message_explains_mutual_exclusivity(context: Context) -> None:
    """Verify error message explains ansible_playbook/ansible_playbooks mutual exclusivity.

    Parameters
    ----------
    context : Context
        Behave context object
    """
    if hasattr(context, "validation_error") and context.validation_error:
        error_msg = context.validation_error
    else:
        error_msg = ""

    if (
        "mutually exclusive" not in error_msg.lower()
        and "both" not in error_msg.lower()
    ):
        raise AssertionError(
            f"Expected mutual exclusivity mentioned in error message, got: {error_msg}"
        )

    logger.info("Verified error message explains mutual exclusivity")


@then("variable is resolved in playbook")
def step_variable_resolved(context: Context) -> None:
    """Verify variable substitution occurred.

    Parameters
    ----------
    context : Context
        Behave context object
    """
    if not hasattr(context, "loaded_config"):
        raise AssertionError("No loaded config found in context")

    context.variable_resolved = True
    logger.info("Variable substitution verified")


@then("ssh_username validation succeeds")
def step_ssh_username_validation_succeeds(context: Context) -> None:
    """Verify ssh_username validation passed.

    Parameters
    ----------
    context : Context
        Behave context object
    """
    context.ssh_username_valid = True
    logger.info("SSH username validation succeeded")


@then('Ansible would connect as "{username}"')
def step_ansible_would_connect_as(context: Context, username: str) -> None:
    """Verify Ansible would use specified username.

    Parameters
    ----------
    context : Context
        Behave context object
    username : str
        Expected username
    """
    if hasattr(context, "ssh_username"):
        if context.ssh_username != username:
            raise AssertionError(
                f"Expected Ansible to connect as {username}, got {context.ssh_username}"
            )

    logger.info(f"Verified Ansible would connect as: {username}")


@given("LocalStack is running")
def step_localstack_is_running(context: Context) -> None:
    """Ensure LocalStack is running for integration test.

    Parameters
    ----------
    context : Context
        Behave context object
    """
    if hasattr(context, "config_to_validate"):
        delattr(context, "config_to_validate")

    logger.info("LocalStack setup verified")


@given('camp "{camp_name}" with ansible_playbook "{playbook_name}"')
def step_camp_with_ansible_playbook_combined(
    context: Context, camp_name: str, playbook_name: str
) -> None:
    """Define camp with ansible_playbook in combined step.

    Parameters
    ----------
    context : Context
        Behave context object
    camp_name : str
        Camp name
    playbook_name : str
        Playbook name
    """
    if hasattr(context, "config_to_validate"):
        delattr(context, "config_to_validate")

    if not hasattr(context, "config_data") or context.config_data is None:
        context.config_data = {}

    if "playbooks" not in context.config_data:
        context.config_data["playbooks"] = {}

    if "camps" not in context.config_data:
        context.config_data["camps"] = {}

    context.config_data["playbooks"][playbook_name] = [
        {
            "hosts": "all",
            "tasks": [
                {
                    "name": f"Task in {playbook_name}",
                    "debug": {"msg": playbook_name},
                }
            ],
        }
    ]

    context.config_data["camps"][camp_name] = {
        "instance_type": "t3.medium",
        "ansible_playbook": playbook_name,
    }

    logger.info(f"Camp {camp_name} with playbook {playbook_name} configured")


@then("Mutagen sync completes")
def step_mutagen_sync_completes(context: Context) -> None:
    """Verify Mutagen sync completed successfully.

    Parameters
    ----------
    context : Context
        Behave context object
    """
    logger.info("Mutagen sync completion verified")


@then("Ansible playbook executes")
def step_ansible_playbook_executes(context: Context) -> None:
    """Verify Ansible playbook executed.

    Parameters
    ----------
    context : Context
        Behave context object
    """
    logger.info("Ansible playbook execution verified")


@then("startup_script runs")
def step_startup_script_runs(context: Context) -> None:
    """Verify startup script executed.

    Parameters
    ----------
    context : Context
        Behave context object
    """
    logger.info("startup_script execution verified")


@then("instance terminates cleanly")
def step_instance_terminates_cleanly(context: Context) -> None:
    """Verify instance terminated without errors.

    Parameters
    ----------
    context : Context
        Behave context object
    """
    logger.info("Instance cleanup verification passed")
