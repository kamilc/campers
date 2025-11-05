"""Environment variable sandboxing with stack-based context management."""

import os
from typing import Any


class ConfigurationEnv:
    """Provides stack-based environment variable sandboxing.

    Enables setting and unsetting environment variables within a context,
    with automatic restoration of previous state on context exit. Supports
    nested context managers for multi-level scoping.

    Attributes
    ----------
    _stack : list[dict]
        Stack of saved environment states for nested contexts
    """

    def __init__(self) -> None:
        self._stack: list[dict[str, Any]] = []

    def __enter__(self) -> "ConfigurationEnv":
        """Enter context manager, saving current environment state."""
        self._stack.append(dict(os.environ))
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context manager, restoring environment to previous state."""
        saved_env = self._stack.pop()
        os.environ.clear()
        os.environ.update(saved_env)

    def set(self, key: str, value: str) -> None:
        """Set environment variable within current context.

        Parameters
        ----------
        key : str
            Environment variable name
        value : str
            Environment variable value
        """
        os.environ[key] = value

    def unset(self, key: str) -> None:
        """Unset environment variable within current context.

        Parameters
        ----------
        key : str
            Environment variable name to remove
        """
        if key in os.environ:
            del os.environ[key]

    def delete(self, key: str) -> None:
        """Delete environment variable from the current context.

        Parameters
        ----------
        key : str
            Environment variable name to remove
        """
        self.unset(key)

    def clear(self) -> None:
        """Clear all environment variables within the current context."""
        os.environ.clear()

    def enter(self) -> None:
        """Enter configuration scope, saving current environment state.

        This method manually enters the context manager scope, allowing
        setup() to call it explicitly without using the `with` statement.
        Must be paired with a call to exit().
        """
        self._stack.append(dict(os.environ))

    def exit(self) -> None:
        """Exit configuration scope, restoring environment to previous state.

        This method manually exits the context manager scope, allowing
        cleanup() to call it explicitly without using the `with` statement.
        Must be called after a matching enter() call.
        """
        if self._stack:
            saved_env = self._stack.pop()
            os.environ.clear()
            os.environ.update(saved_env)
