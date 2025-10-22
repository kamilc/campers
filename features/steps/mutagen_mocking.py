"""Mutagen mocking infrastructure for LocalStack testing."""

import logging
from contextlib import contextmanager
from typing import Generator
from unittest.mock import patch

from behave.runner import Context

from features.steps.docker_helpers import create_synced_directories

logger = logging.getLogger(__name__)


@contextmanager
def mutagen_mocked(context: Context) -> Generator[None, None, None]:
    """Mock Mutagen for LocalStack scenarios.

    This context manager patches MutagenManager methods to simulate Mutagen
    sync without actually running Mutagen. It creates synced directories
    via Docker API to provide high-fidelity sync simulation.

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
        If synced directory creation fails
    """

    def mock_check_mutagen(self) -> None:
        logger.debug("Mocked: Mutagen installation check skipped")

    def mock_create_sync_session(self, *args, **kwargs):
        logger.info("Creating Mutagen sync session")
        create_synced_directories(context)
        logger.info("Sync session created")
        return {"session_id": "mock-session", "status": "synced"}

    def mock_terminate_session(self, *args, **kwargs):
        logger.debug("Mocked: Terminating Mutagen session")
        return True

    def mock_wait_for_sync(self, *args, **kwargs):
        logger.debug("Mocked: Waiting for Mutagen sync")
        return True

    try:
        from moondock.sync import MutagenManager

        with (
            patch.object(MutagenManager, "check_mutagen_installed", mock_check_mutagen),
            patch.object(
                MutagenManager, "create_sync_session", mock_create_sync_session
            ),
            patch.object(MutagenManager, "terminate_session", mock_terminate_session),
            patch.object(MutagenManager, "wait_for_initial_sync", mock_wait_for_sync),
        ):
            yield
    except ImportError as e:
        raise RuntimeError(f"Failed to import MutagenManager: {e}")
