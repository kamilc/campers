"""Logging handlers for TUI integration."""

import logging
import threading
from typing import TYPE_CHECKING

from textual.message import Message
from textual.widgets import Log

if TYPE_CHECKING:
    from campers.tui import CampersTUI

logger = logging.getLogger(__name__)


class TuiLogMessage(Message):
    """Message delivering a log line to the TUI log widget."""

    def __init__(self, text: str) -> None:
        self.text = text
        super().__init__()


class TuiLogHandler(logging.Handler):
    """Logging handler that writes to a Textual Log widget.

    Parameters
    ----------
    app : CampersTUI
        Textual app instance
    log_widget : Log
        Log widget to write to

    Attributes
    ----------
    app : CampersTUI
        Textual app instance
    log_widget : Log
        Log widget to write to
    """

    def __init__(self, app: "CampersTUI", log_widget: Log) -> None:
        """Initialize TuiLogHandler.

        Parameters
        ----------
        app : CampersTUI
            Textual app instance
        log_widget : Log
            Log widget to write to
        """
        super().__init__()
        self.app = app
        self.log_widget = log_widget

    def emit(self, record: logging.LogRecord) -> None:
        """Emit log record to TUI widget.

        Parameters
        ----------
        record : logging.LogRecord
            Log record to emit
        """
        msg = self.format(record)

        try:
            if not hasattr(self.app, "_running") or not self.app._running:
                return

            if self.app._thread_id == threading.get_ident():
                self.log_widget.write_line(msg)
                return

            self.app.post_message(TuiLogMessage(msg))
        except (RuntimeError, AttributeError) as e:
            logger.debug("Error emitting log message to TUI: %s", e)
