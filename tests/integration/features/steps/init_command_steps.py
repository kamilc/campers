import os
import subprocess
from pathlib import Path

from behave import given, then, when


def resolve_config_path(context, fallback_path: str) -> Path:
    """Resolve the configuration file path from context attributes.

    Parameters
    ----------
    context : behave.runner.Context
        The behave context object containing test state
    fallback_path : str
        Path to use if no config path is set in context

    Returns
    -------
    Path
        The resolved configuration file path
    """
    if hasattr(context, "init_config_path"):
        return Path(context.init_config_path)

    if hasattr(context, "env_config_path") and context.env_config_path:
        config_path = context.env_config_path

        if not config_path.startswith("/"):
            config_path = str(context.tmp_dir / config_path)

        return Path(config_path)

    return context.tmp_dir / fallback_path


@given('"{path}" does not exist')
def step_file_does_not_exist(context, path: str) -> None:
    full_path = context.tmp_dir / path

    if full_path.exists():
        if full_path.is_dir():
            import shutil

            shutil.rmtree(full_path)
        else:
            full_path.unlink()

    if not path.endswith("/"):
        context.init_config_path = str(full_path)


@given("CAMPERS_CONFIG is not set")
def step_campers_config_not_set(context) -> None:
    if hasattr(context, "harness") and getattr(context.harness, "services", None):
        context.harness.services.configuration_env.delete("CAMPERS_CONFIG")
    else:
        os.environ.pop("CAMPERS_CONFIG", None)

    context.init_config_path = str(context.tmp_dir / "campers.yaml")


@given('"{path}" exists')
def step_file_exists(context, path: str) -> None:
    full_path = context.tmp_dir / path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text("existing content")
    context.init_config_path = str(full_path)
    context.original_content = "existing content"


@when("I run init command")
def step_run_init_command(context) -> None:
    env = os.environ.copy()

    if hasattr(context, "init_config_path"):
        env["CAMPERS_CONFIG"] = context.init_config_path
    elif hasattr(context, "env_config_path"):
        path = context.env_config_path

        if not path.startswith("/"):
            path = str(context.tmp_dir / path)

        env["CAMPERS_CONFIG"] = path

    result = subprocess.run(
        ["uv", "run", "-m", "campers", "init"],
        cwd=str(context.project_root),
        capture_output=True,
        text=True,
        env=env,
    )
    context.result = result
    context.stdout = result.stdout
    context.stderr = result.stderr
    context.exit_code = result.returncode


@when('I run init command with "{flag}"')
def step_run_init_command_with_flag(context, flag: str) -> None:
    env = os.environ.copy()

    if hasattr(context, "init_config_path"):
        env["CAMPERS_CONFIG"] = context.init_config_path
    elif hasattr(context, "env_config_path"):
        path = context.env_config_path

        if not path.startswith("/"):
            path = str(context.tmp_dir / path)

        env["CAMPERS_CONFIG"] = path

    result = subprocess.run(
        ["uv", "run", "-m", "campers", "init", flag],
        cwd=str(context.project_root),
        capture_output=True,
        text=True,
        env=env,
    )
    context.result = result
    context.stdout = result.stdout
    context.stderr = result.stderr
    context.exit_code = result.returncode


@then('"{path}" is created')
def step_file_is_created(context, path: str) -> None:
    file_path = resolve_config_path(context, path)
    assert file_path.exists(), f"File {file_path} was not created"
    context.created_file = file_path


@then("file contains template content")
def step_file_contains_template_content(context) -> None:
    if hasattr(context, "created_file"):
        file_path = context.created_file
    else:
        file_path = resolve_config_path(context, "campers.yaml")

    content = file_path.read_text()
    assert "# Campers Configuration File" in content
    assert "defaults:" in content
    assert "region:" in content
    assert "instance_type:" in content


@then('success message includes "{text}"')
def step_success_message_includes(context, text: str) -> None:
    assert text in context.stdout, f"Expected '{text}' in stdout, got: {context.stdout}"


@then("command fails with exit code 1")
def step_command_fails_with_exit_code_1(context) -> None:
    assert context.exit_code == 1, f"Expected exit code 1, got: {context.exit_code}"


@then('"{path}" is not modified')
def step_file_is_not_modified(context, path: str) -> None:
    file_path = resolve_config_path(context, path)
    current_content = file_path.read_text()
    assert current_content == context.original_content, (
        f"File was modified. Original: {context.original_content}, Current: {current_content}"
    )


@then('"{directory}" directory is created')
def step_directory_is_created(context, directory: str) -> None:
    if hasattr(context, "env_config_path") and context.env_config_path:
        config_path = context.env_config_path

        if not config_path.startswith("/"):
            config_path = str(context.tmp_dir / config_path)

        dir_path = Path(config_path).parent
    else:
        dir_path = context.tmp_dir / directory

    assert dir_path.exists(), f"Directory {dir_path} was not created"
    assert dir_path.is_dir(), f"{dir_path} exists but is not a directory"


@then('"{path}" is overwritten')
def step_file_is_overwritten(context, path: str) -> None:
    file_path = resolve_config_path(context, path)
    current_content = file_path.read_text()
    assert current_content != context.original_content, (
        "File was not overwritten - content is the same"
    )
    assert "# Campers Configuration File" in current_content, (
        "File was overwritten but does not contain template content"
    )
