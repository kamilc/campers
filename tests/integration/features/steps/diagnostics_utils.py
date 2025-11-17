"""Utility helpers for collecting diagnostics during Behave scenarios."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


from behave.runner import Context
from tests.harness.utils.system_snapshot import gather_system_snapshot


DIAGNOSTIC_ENV_PREFIXES: tuple[str, ...] = ("MOONDOCK_", "AWS_", "LOCALSTACK")


def sanitize_for_path(value: str) -> str:
    """Sanitize text for safe filesystem usage.

    Parameters
    ----------
    value : str
        Arbitrary string that may contain unsupported characters.

    Returns
    -------
    str
        Lowercase string containing alphanumeric characters and hyphens.
    """

    sanitized = re.sub(r"[^a-z0-9]+", "-", value.lower())
    sanitized = sanitized.strip("-")
    return sanitized or "diagnostic"


def run_diagnostic_command(command: Sequence[str]) -> str:
    """Execute a diagnostic command and capture its output.

    Parameters
    ----------
    command : Sequence[str]
        Command and arguments to execute.

    Returns
    -------
    str
        Combined stdout and stderr output or an error description.
    """

    try:
        result = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except Exception as exc:  # pragma: no cover - defensive diagnostics
        return f"command failed: {' '.join(command)} :: {exc}"

    stdout_text = result.stdout.strip()
    stderr_text = result.stderr.strip()
    payload: list[str] = []

    if stdout_text:
        payload.append(stdout_text)

    if stderr_text:
        payload.append(f"[stderr] {stderr_text}")

    if not payload:
        payload.append(f"command returned {result.returncode} with no output")

    return "\n".join(payload)


def record_diagnostic_artifact(context: Context, artifact_path: Path) -> None:
    """Record a diagnostics artifact path on the Behave context.

    Parameters
    ----------
    context : Context
        Behave runtime context.
    artifact_path : Path
        Path to diagnostics artifact.
    """

    if not hasattr(context, "diagnostic_artifacts"):
        context.diagnostic_artifacts: list[Path] = []

    context.diagnostic_artifacts.append(artifact_path)


def send_signal_to_process(process: subprocess.Popen, sig: int) -> None:
    """Deliver a signal to a subprocess and its process group when available."""

    if process is None:
        return

    pid = getattr(process, "pid", None)

    if pid is None:
        return

    try:
        pgid = os.getpgid(pid)
    except OSError:
        try:
            os.kill(pid, sig)
        except OSError:
            pass
        return

    try:
        os.killpg(pgid, sig)
    except OSError:
        try:
            os.kill(pid, sig)
        except OSError:
            pass


def collect_diagnostics(
    context: Context,
    stdout_text: str = "",
    stderr_text: str = "",
    reason: str = "scenario_failure",
) -> Path:
    """Collect diagnostics for the given scenario context.

    Parameters
    ----------
    context : Context
        Behave runtime context instance.
    stdout_text : str, optional
        Captured stdout from subprocess execution.
    stderr_text : str, optional
        Captured stderr from subprocess execution.
    reason : str, optional
        High-level reason for diagnostics capture (default: "scenario_failure").

    Returns
    -------
    Path
        Filesystem path to the diagnostics artifact.
    """

    scenario = getattr(context, "scenario", None)
    scenario_name = scenario.name if scenario is not None else "unknown-scenario"
    scenario_status = getattr(scenario, "status", "unknown")
    scenario_tags = sorted(getattr(scenario, "tags", []))

    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    scenario_slug = sanitize_for_path(scenario_name)
    reason_slug = sanitize_for_path(reason)

    env_snapshot = {
        key: os.environ[key]
        for key in sorted(os.environ.keys())
        if any(key.startswith(prefix) for prefix in DIAGNOSTIC_ENV_PREFIXES)
    }

    pid_value = getattr(getattr(context, "app_process", None), "pid", None)
    return_code = getattr(getattr(context, "app_process", None), "returncode", None)

    ps_command = [
        "ps",
        "-p",
        str(pid_value) if pid_value is not None else "0",
        "-o",
        "pid,ppid,stat,etime,command",
    ]
    docker_logs_command = [
        "docker",
        "logs",
        "moondock-localstack",
        "--tail",
        "200",
    ]

    system_snapshot = gather_system_snapshot(include_thread_stacks=True)

    sections = [
        f"timestamp: {timestamp}",
        f"scenario: {scenario_name}",
        f"status: {scenario_status}",
        f"tags: {json.dumps(scenario_tags)}",
        f"reason: {reason}",
        f"pid: {pid_value}",
        f"process_returncode: {return_code}",
        "",
        "environment_snapshot:",
        json.dumps(env_snapshot, indent=2) if env_snapshot else "<none>",
        "",
        "process_status:",
        run_diagnostic_command(ps_command),
        "",
        "docker_ps:",
        run_diagnostic_command(["docker", "ps"]),
        "",
        "docker_logs_moondock_localstack:",
        run_diagnostic_command(docker_logs_command),
        "",
        "mutagen_sync_list:",
        run_diagnostic_command(["mutagen", "sync", "list"]),
        "",
        "subprocess_stdout:",
        stdout_text.strip() or "<empty>",
        "",
        "subprocess_stderr:",
        stderr_text.strip() or "<empty>",
        "",
        "context_process_output:",
        getattr(context, "process_output", "").strip() or "<empty>",
        "",
        "system_snapshot:",
        json.dumps(system_snapshot, indent=2),
    ]

    content = "\n".join(sections) + "\n"

    harness = getattr(context, "harness", None)
    services = getattr(harness, "services", None)
    artifact_manager = getattr(services, "artifacts", None)

    unique_suffix = f"{int(time.time() * 1000)}"
    run_id = getattr(artifact_manager, "run_id", None)

    if run_id:
        unique_suffix = f"{run_id}-{unique_suffix}"

    filename = f"diagnostics/{scenario_slug}/{unique_suffix}-{reason_slug}.log"

    if artifact_manager is not None:
        artifact_path = artifact_manager.create_temp_file(filename, content)
    else:
        fallback_dir = Path.cwd() / "tmp" / "behave" / "diagnostics" / scenario_slug
        fallback_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = fallback_dir / f"{unique_suffix}-{reason_slug}.log"
        artifact_path.write_text(content)

    record_diagnostic_artifact(context, artifact_path)
    return artifact_path
