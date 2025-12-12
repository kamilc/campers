"""Logging handlers for TUI integration."""

import logging
import threading
from typing import TYPE_CHECKING

from textual.message import Message
from textual.widgets import RichLog

if TYPE_CHECKING:
    from campers.tui import CampersTUI

logger = logging.getLogger(__name__)


class TuiLogMessage(Message):
    """Message delivering a log line to the TUI log widget."""

    def __init__(self, text: str) -> None:
        self.text = text
        super().__init__()


class TuiLogHandler(logging.Handler):
    """Logging handler that writes to a Textual RichLog widget.

    Parameters
    ----------
    app : CampersTUI
        Textual app instance
    log_widget : RichLog
        RichLog widget to write to

    Attributes
    ----------
    app : CampersTUI
        Textual app instance
    log_widget : RichLog
        RichLog widget to write to
    """

    def __init__(self, app: "CampersTUI", log_widget: RichLog) -> None:
        """Initialize TuiLogHandler.

        Parameters
        ----------
        app : CampersTUI
            Textual app instance
        log_widget : RichLog
            RichLog widget to write to
        """
        super().__init__()
        self.app = app
        self.log_widget = log_widget

    def _apply_level_markup(self, msg: str, level: int) -> str:
        """Apply Rich markup based on log level.

        Parameters
        ----------
        msg : str
            Log message to format
        level : int
            Log level (e.g., logging.WARNING, logging.ERROR)

        Returns
        -------
        str
            Message with Rich markup applied for WARNING/ERROR levels
        """
        if level >= logging.ERROR:
            return f"[red]{msg}[/red]"

        if level >= logging.WARNING:
            return f"[yellow]{msg}[/yellow]"

        return msg

    def emit(self, record: logging.LogRecord) -> None:
        """Emit log record to TUI widget.

        Parameters
        ----------
        record : logging.LogRecord
            Log record to emit
        """
        msg = self.format(record)
        msg = self._apply_level_markup(msg, record.levelno)

        try:
            if not hasattr(self.app, "_running") or not self.app._running:
                return

            thread_id = threading.get_ident()
            app_thread_id = self.app._thread_id

            if app_thread_id == thread_id:
                self.log_widget.write(msg)
                return

            self.app.post_message(TuiLogMessage(msg))
        except Exception:
            pass
