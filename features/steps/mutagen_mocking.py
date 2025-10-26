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


@contextmanager
def mutagen_mocked(context: Context) -> Generator[None, None, None]:
    """Mock Mutagen for @dry_run, use real Mutagen for @localstack.

    This context manager either:
    - Patches MutagenManager for @dry_run to simulate sync via mocks
    - Sets up isolated MOONDOCK_DIR for @localstack to enable real Mutagen execution

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
        os.environ["MOONDOCK_DIR"] = str(test_dir)

        logger.info(f"Set isolated MOONDOCK_DIR: {test_dir}")

        try:
            yield
        finally:
            if original_moondock_dir:
                os.environ["MOONDOCK_DIR"] = original_moondock_dir
            else:
                os.environ.pop("MOONDOCK_DIR", None)
            logger.debug("Restored original MOONDOCK_DIR")
    else:

        def mock_check_mutagen(self) -> None:
            logger.debug("Mocked: Mutagen installation check skipped")

        def mock_create_sync_session(self, *args: Any, **kwargs: Any) -> dict[str, str]:
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
