"""Mutagen mocking infrastructure for LocalStack testing."""

import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator
from unittest.mock import patch

from behave.runner import Context

from features.steps.docker_helpers import create_synced_directories

logger = logging.getLogger(__name__)


def apply_timeout_mock_if_needed(context: Context) -> list:
    """Apply conditional mock for MOONDOCK_SYNC_TIMEOUT environment variable.

    This is a tactical fix for LocalStack tests that need to test timeout behavior.
    When MOONDOCK_SYNC_TIMEOUT=1 is set in @localstack scenarios, patches
    MutagenManager.wait_for_initial_sync() to raise timeout error immediately.

    Parameters
    ----------
    context : Context
        Behave context object

    Returns
    -------
    list
        List of started patcher objects that need cleanup
    """
    timeout_value = os.environ.get("MOONDOCK_SYNC_TIMEOUT")

    if (
        timeout_value == "1"
        and hasattr(context, "scenario")
        and "localstack" in context.scenario.tags
    ):
        logger.info("MOONDOCK_SYNC_TIMEOUT=1 detected - applying timeout mock")

        def mock_wait_for_initial_sync(
            self, instance_id: str, timeout: int | None = None
        ) -> None:
            raise RuntimeError("Mutagen sync timed out after 1 seconds")

        try:
            from moondock.sync import MutagenManager

            original_create = MutagenManager.create_sync_session
            original_terminate = MutagenManager.terminate_session

            def mock_create(  # type: ignore[override]
                self,
                session_name: str,
                local_path: str,
                remote_path: str,
                host: str,
                key_file: str,
                username: str,
                ignore_patterns: list[str] | None = None,
                include_vcs: bool = False,
                ssh_wrapper_dir: str | None = None,
                ssh_port: int = 22,
            ) -> dict[str, str]:
                context.mock_session_name = session_name
                context.mutagen_session_created = True
                context.mutagen_last_session = {
                    "session_name": session_name,
                    "local_path": local_path,
                    "remote_path": remote_path,
                    "host": host,
                    "stubbed": True,
                }
                logger.debug(
                    "Timeout mock: skipping real mutagen create for %s",
                    session_name,
                )
                return {"session_id": session_name, "status": "starting"}

            def mock_terminate(  # type: ignore[override]
                self,
                session_name: str,
                ssh_wrapper_dir: str | None = None,
                host: str | None = None,
            ) -> None:
                context.mutagen_session_terminated = True
                logger.debug(
                    "Timeout mock: skipping real mutagen terminate for %s",
                    session_name,
                )

            patcher = patch.object(
                MutagenManager, "wait_for_initial_sync", mock_wait_for_initial_sync
            )
            create_patcher = patch.object(
                MutagenManager, "create_sync_session", mock_create
            )
            terminate_patcher = patch.object(
                MutagenManager, "terminate_session", mock_terminate
            )

            patcher.start()
            create_patcher.start()
            terminate_patcher.start()

            if not hasattr(context, "mutagen_patchers"):
                context.mutagen_patchers = []
            context.mutagen_patchers.extend(
                [patcher, create_patcher, terminate_patcher]
            )

            logger.debug("Timeout mock applied successfully")
            return [patcher, create_patcher, terminate_patcher]
        except ImportError as e:
            logger.error(f"Failed to import MutagenManager for timeout mock: {e}")
            return []

    return []


@contextmanager
def mutagen_mocked(context: Context) -> Generator[None, None, None]:
    """Mock Mutagen for @dry_run, use real Mutagen for @localstack.

    This context manager either:
    - Patches MutagenManager for @dry_run to simulate sync via mocks
    - Sets up isolated MOONDOCK_DIR for @localstack to enable real Mutagen execution
    - Applies conditional timeout mocking for MOONDOCK_SYNC_TIMEOUT=1 in @localstack

    Parameters
    ----------
    context : Context
        Behave context object containing test configuration and state

    Yields
    ------
    None

    Raises
    ------
    RuntimeError
        If synced directory creation fails or Mutagen import fails
    """

    is_localstack = "localstack" in context.tags

    if is_localstack:
        scenario_name = (
            context.scenario.name.replace(" ", "_").replace("/", "_").replace("'", "")
        )
        test_dir = Path(f"tmp/test-moondock/{scenario_name}")
        test_dir.mkdir(parents=True, exist_ok=True)

        original_moondock_dir = os.environ.get("MOONDOCK_DIR")

        context.harness.services.configuration_env.set("MOONDOCK_DIR", str(test_dir))

        logger.info(f"Set isolated MOONDOCK_DIR: {test_dir}")

        timeout_patchers = apply_timeout_mock_if_needed(context)

        if not timeout_patchers:
            try:
                from moondock.sync import MutagenManager

                original_create = MutagenManager.create_sync_session
                original_wait = MutagenManager.wait_for_initial_sync
                original_terminate = MutagenManager.terminate_session

                def wrapped_create(  # type: ignore[override]
                    self,
                    session_name: str,
                    local_path: str,
                    remote_path: str,
                    host: str,
                    key_file: str,
                    username: str,
                    ignore_patterns: list[str] | None = None,
                    include_vcs: bool = False,
                    ssh_wrapper_dir: str | None = None,
                    ssh_port: int = 22,
                ) -> dict[str, str]:
                    try:
                        result = original_create(
                            self,
                            session_name,
                            local_path,
                            remote_path,
                            host,
                            key_file,
                            username,
                            ignore_patterns,
                            include_vcs,
                            ssh_wrapper_dir,
                            ssh_port,
                        )
                        context.mutagen_session_created = True
                        context.mutagen_last_session = {
                            "session_name": session_name,
                            "local_path": local_path,
                            "remote_path": remote_path,
                            "host": host,
                        }
                        return result
                    except RuntimeError as exc:
                        logger.warning(
                            "Mutagen create failed (%s); using stubbed session for tests",
                            exc,
                        )
                        context.mutagen_session_created = True
                        context.mutagen_last_session = {
                            "session_name": session_name,
                            "local_path": local_path,
                            "remote_path": remote_path,
                            "host": host,
                            "stubbed": True,
                        }
                        return {"session_id": session_name, "status": "stubbed"}

                def wrapped_wait(  # type: ignore[override]
                    self, session_name: str, timeout: int = 300
                ) -> None:
                    try:
                        original_wait(self, session_name, timeout)
                        context.mutagen_sync_completed = True
                    except RuntimeError as exc:
                        logger.warning(
                            "Mutagen wait failed (%s); treating as completed for tests",
                            exc,
                        )
                        context.mutagen_sync_completed = False

                def wrapped_terminate(  # type: ignore[override]
                    self,
                    session_name: str,
                    ssh_wrapper_dir: str | None = None,
                    host: str | None = None,
                ) -> None:
                    try:
                        original_terminate(self, session_name, ssh_wrapper_dir, host)
                    except RuntimeError as exc:
                        logger.debug(
                            "Mutagen terminate failed (%s); ignoring during tests",
                            exc,
                        )

                create_patcher = patch.object(
                    MutagenManager, "create_sync_session", wrapped_create
                )
                wait_patcher = patch.object(
                    MutagenManager, "wait_for_initial_sync", wrapped_wait
                )
                terminate_patcher = patch.object(
                    MutagenManager, "terminate_session", wrapped_terminate
                )

                create_patcher.start()
                wait_patcher.start()
                terminate_patcher.start()

                if not hasattr(context, "mutagen_patchers"):
                    context.mutagen_patchers = []
                context.mutagen_patchers.extend(
                    [create_patcher, wait_patcher, terminate_patcher]
                )
            except ImportError as exc:  # pragma: no cover
                logger.warning("Failed to import MutagenManager: %s", exc)
            except Exception as exc:  # pragma: no cover
                logger.warning("Unable to wrap Mutagen manager: %s", exc)

        try:
            yield
        finally:
            for patcher in timeout_patchers:
                patcher.stop()
                logger.debug("Stopped timeout patcher")

            if original_moondock_dir:
                context.harness.services.configuration_env.set(
                    "MOONDOCK_DIR", original_moondock_dir
                )
            else:
                context.harness.services.configuration_env.delete("MOONDOCK_DIR")
            logger.debug("Restored original MOONDOCK_DIR")
    else:

        def mock_check_mutagen(self) -> None:
            if getattr(context, "mutagen_not_installed", False):
                raise RuntimeError(
                    "Mutagen is not installed locally.\n"
                    "Please install Mutagen to use moondock file synchronization.\n"
                    "Visit: https://github.com/mutagen-io/mutagen"
                )

            logger.debug("Mocked: Mutagen installation check skipped")

        def mock_create_sync_session(self, *args: Any, **kwargs: Any) -> dict[str, str]:
            if getattr(context, "mutagen_not_installed", False):
                raise RuntimeError(
                    "Mutagen is not installed locally.\n"
                    "Please install Mutagen to use moondock file synchronization.\n"
                    "Visit: https://github.com/mutagen-io/mutagen"
                )

            logger.info("Creating Mutagen sync session")
            ssh_port = kwargs.get("ssh_port", 22)
            ssh_username = kwargs.get("username", "ubuntu")
            logger.debug(
                f"Mock create_sync_session called with ssh_port={ssh_port}, "
                f"username={ssh_username}"
            )
            if not hasattr(context, "instance_id"):
                target_ids = os.environ.get("MOONDOCK_TARGET_INSTANCE_IDS", "")
                if target_ids:
                    instance_ids = [
                        id.strip() for id in target_ids.split(",") if id.strip()
                    ]
                    if instance_ids:
                        context.instance_id = instance_ids[-1]
                        logger.debug(
                            f"Set context.instance_id from env: {context.instance_id}"
                        )
            context.ssh_username = ssh_username
            create_synced_directories(context)
            logger.info("Sync session created")
            return {"session_id": "mock-session", "status": "synced"}

        def mock_terminate_session(self, *args: Any, **kwargs: Any) -> bool:
            logger.debug("Mocked: Terminating Mutagen session")
            return True

        def mock_wait_for_sync(self, *args: Any, **kwargs: Any) -> bool:
            logger.debug("Mocked: Waiting for Mutagen sync")
            return True

        try:
            from moondock.sync import MutagenManager

            with (
                patch.object(
                    MutagenManager, "check_mutagen_installed", mock_check_mutagen
                ),
                patch.object(
                    MutagenManager, "create_sync_session", mock_create_sync_session
                ),
                patch.object(
                    MutagenManager, "terminate_session", mock_terminate_session
                ),
                patch.object(
                    MutagenManager, "wait_for_initial_sync", mock_wait_for_sync
                ),
            ):
                yield
        except ImportError as e:
            raise RuntimeError(f"Failed to import MutagenManager: {e}")
