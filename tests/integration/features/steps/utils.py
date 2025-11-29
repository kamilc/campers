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
    return asyncio.run(async_func())
