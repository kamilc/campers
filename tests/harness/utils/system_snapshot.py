"""Helpers for capturing rich system diagnostics snapshots."""

from __future__ import annotations

import subprocess
import threading
import traceback
import sys
from typing import Any


def _gather_thread_info(include_stacks: bool) -> list[dict[str, Any]]:
    threads: list[dict[str, Any]] = []
    frames = sys._current_frames() if include_stacks else {}

    for thread in threading.enumerate():
        info: dict[str, Any] = {
            "name": thread.name,
            "ident": thread.ident,
            "daemon": thread.daemon,
            "alive": thread.is_alive(),
        }

        if include_stacks and thread.ident in frames:
            info["stack"] = traceback.format_stack(frames[thread.ident])

        threads.append(info)

    return threads


def _gather_process_info() -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid,ppid,stat,etime,command"],
            capture_output=True,
            text=True,
            check=True,
        )
        snapshot["table"] = result.stdout.strip()
    except Exception as exc:  # pragma: no cover - best effort only
        snapshot["error"] = str(exc)

    return snapshot


def _gather_docker_info() -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    try:
        import docker  # type: ignore

        client = docker.from_env()
        containers = []
        for container in client.containers.list(all=True):
            containers.append(
                {
                    "id": container.id,
                    "name": container.name,
                    "status": container.status,
                    "image": container.image.tags,
                    "labels": container.attrs.get("Config", {}).get("Labels", {}),
                    "ports": container.attrs.get("NetworkSettings", {}).get(
                        "Ports", {}
                    ),
                }
            )
        snapshot["containers"] = containers
        client.close()
    except Exception as exc:  # pragma: no cover - docker optional during tests
        snapshot["error"] = str(exc)

    return snapshot


def gather_system_snapshot(
    *, include_thread_stacks: bool = False
) -> dict[str, Any]:
    """Gather diagnostic information about the current process, threads and Docker.

    Parameters
    ----------
    include_thread_stacks : bool, optional
        Whether to include full Python stack traces for all threads.

    Returns
    -------
    dict[str, Any]
        Structured snapshot of system state.
    """
    snapshot: dict[str, Any] = {}
    snapshot["threads"] = _gather_thread_info(include_thread_stacks)
    snapshot["processes"] = _gather_process_info()
    snapshot["docker"] = _gather_docker_info()
    return snapshot


__all__ = ["gather_system_snapshot"]
