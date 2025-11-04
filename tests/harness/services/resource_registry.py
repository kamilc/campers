"""Registry for managing resource lifecycle with cleanup ordering."""

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


class ResourceRegistry:
    """Manages resource lifecycle with deterministic cleanup ordering.

    Tracks resources with optional dependencies and executes cleanup
    in reverse creation order. Continues cleanup even if individual
    disposals fail, logging warnings for diagnostics.

    Attributes
    ----------
    resources : list[dict]
        List of registered resources in creation order
    """

    def __init__(self) -> None:
        self.resources: list[dict[str, Any]] = []

    def register(
        self,
        kind: str,
        handle: Any,
        dispose_fn: Callable[[Any], None],
        label: str = "",
        dependencies: list[str] | None = None,
    ) -> None:
        """Register a resource for lifecycle management.

        Parameters
        ----------
        kind : str
            Type of resource (e.g., "container", "process")
        handle : Any
            Resource handle to pass to dispose_fn
        dispose_fn : Callable
            Function to call during cleanup: dispose_fn(handle)
        label : str, optional
            Descriptive label for diagnostics
        dependencies : list[str], optional
            Labels of resources that must be cleaned before this one
        """
        entry: dict[str, Any] = {
            "kind": kind,
            "handle": handle,
            "dispose_fn": dispose_fn,
            "label": label,
            "dependencies": dependencies or [],
        }
        self.resources.append(entry)
        logger.debug(f"Registered {kind}: {label}")

    def cleanup_all(self) -> None:
        """Cleanup all registered resources in reverse creation order.

        Executes cleanup even if individual disposals raise exceptions,
        logging warnings for failed disposals.
        """
        for entry in reversed(self.resources):
            try:
                entry["dispose_fn"](entry["handle"])
                logger.debug(f"Cleaned up {entry['kind']}: {entry['label']}")
            except Exception as e:
                logger.warning(
                    f"Cleanup failed for {entry['kind']} '{entry['label']}': {e}"
                )
