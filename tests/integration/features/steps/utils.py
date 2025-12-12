"""Utility functions for BDD step definitions."""

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any


def run_async_test(async_func: Callable[[], Coroutine[Any, Any, Any]]) -> Any:
    """Run an async function to completion.

    This acts as the bridge between the synchronous behave step
    and the async run_test method from Textual Pilot.

    Parameters
    ----------
    async_func : Callable[[], Coroutine[Any, Any, Any]]
        Async function to execute

    Returns
    -------
    Any
        Result from the async function
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info("[ASYNC_TEST] Entering run_async_test")
    try:
        loop = asyncio.get_running_loop()
        logger.info("[ASYNC_TEST] Event loop already running, using run_in_executor workaround")
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, async_func())
            return future.result()
    except RuntimeError:
        logger.info("[ASYNC_TEST] No running event loop, using asyncio.run()")
        return asyncio.run(async_func())
