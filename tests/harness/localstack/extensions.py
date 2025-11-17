"""Extension container for LocalStackHarness extensions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tests.harness.localstack.pilot_extension import PilotExtension


@dataclass
class Extensions:
    """Container for LocalStackHarness extensions.

    Attributes
    ----------
    pilot : PilotExtension | None
        TUI Pilot extension for testing Textual applications
    """

    pilot: PilotExtension | None = None
