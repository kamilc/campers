"""Logging handlers for TUI integration."""

import logging
import threading
from typing import TYPE_CHECKING, Protocol

from textual.message import Message

if TYPE_CHECKING:
    from campers.tui import CampersTUI

logger = logging.getLogger(__name__)


class LogWidget(Protocol):
    """Protocol for log widget objects.

    Defines the interface required for widgets to work with TuiLogHandler.
    """

    def write(self, content: str) -> None:
        """Write content to the log widget.

        Parameters
        ----------
        content : str
            Content to write to the log
        """
        ...


class TuiLogMessage(Message):
    """Message delivering a log line to the TUI log widget."""

    def __init__(self, text: str) -> None:
        self.text = text
        super().__init__()


class TuiLogHandler(logging.Handler):
    """Logging handler that writes to a Textual log widget.

    Parameters
    ----------
    app : CampersTUI
        Textual app instance
    log_widget : LogWidget
        Log widget to write to (RichLog or SelectableLog)

    Attributes
    ----------
    app : CampersTUI
        Textual app instance
    log_widget : LogWidget
        Log widget to write to (RichLog or SelectableLog)
    """

    def __init__(self, app: "CampersTUI", log_widget: LogWidget) -> None:
        """Initialize TuiLogHandler.

        Parameters
        ----------
        app : CampersTUI
            Textual app instance
        log_widget : LogWidget
            Log widget to write to (RichLog or SelectableLog)
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
