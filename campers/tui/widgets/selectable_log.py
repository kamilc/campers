"""Selectable log widget for TUI application."""

from __future__ import annotations

import logging
from typing import ClassVar

from rich.style import Style
from rich.text import Text
from textual.geometry import Offset, Size
from textual.scroll_view import ScrollView
from textual.strip import Strip

from campers.tui.widgets.selection import Selection

logger = logging.getLogger(__name__)


class SelectableLog(ScrollView, can_focus=True):
    """A scrollable log widget with text selection and clipboard support.

    This widget displays log content and allows users to select text with
    the mouse and copy it to the clipboard. It sanitizes ANSI escape codes
    while preserving color information.

    Parameters
    ----------
    max_lines : int, optional
        Maximum number of lines to store in buffer (default: 5000)
    **kwargs
        Additional keyword arguments passed to ScrollView

    Attributes
    ----------
    lines : list[Text]
        List of Rich Text objects representing log lines
    max_lines : int
        Maximum number of lines to store in buffer
    selection : Selection | None
        Current text selection, or None if no selection
    """

    BINDINGS: ClassVar = [
        ("ctrl+c", "copy", "Copy"),
        ("ctrl+a", "select_all", "Select All"),
    ]

    SELECTION_STYLE: ClassVar = Style(bgcolor="blue", color="white")

    def __init__(self, max_lines: int = 5000, **kwargs) -> None:
        """Initialize SelectableLog widget.

        Parameters
        ----------
        max_lines : int
            Maximum number of lines to store (default: 5000)
        **kwargs
            Additional keyword arguments passed to ScrollView
        """
        super().__init__(**kwargs)
        self.lines: list[Text] = []
        self.max_lines = max_lines
        self.selection: Selection | None = None
        self._selecting = False

    def write(self, content: str | Text) -> None:
        """Write content to the log widget.

        Converts ANSI-escaped strings to Rich Text and splits multiline
        content into separate lines. Automatically trims buffer to max_lines
        and scrolls to bottom.

        Parameters
        ----------
        content : str | Text
            Content to write (string with optional ANSI codes or Rich Text)
        """
        text = Text.from_ansi(content) if isinstance(content, str) else content

        for line in text.split("\n"):
            self.lines.append(line)

        if len(self.lines) > self.max_lines:
            self.lines = self.lines[-self.max_lines :]
            self.selection = None

        max_width = max((len(line.plain) for line in self.lines), default=0)
        self.virtual_size = Size(max_width, len(self.lines))
        self.scroll_end(animate=False)
        self.refresh()

    def render_line(self, y: int) -> Strip:
        """Render a single line of the log.

        Accounts for scroll offset and applies selection styling if the line
        contains selected content.

        Parameters
        ----------
        y : int
            Y coordinate relative to viewport

        Returns
        -------
        Strip
            Rendered line as a Strip object
        """
        scroll_y = self.scroll_offset.y
        line_index = y + scroll_y

        if line_index >= len(self.lines):
            return Strip([])

        line = self.lines[line_index].copy()

        if self.selection:
            start, end = self.selection.normalized
            if start[0] <= line_index <= end[0]:
                start_col = start[1] if line_index == start[0] else 0
                end_col = end[1] if line_index == end[0] else len(line.plain)
                line.stylize(self.SELECTION_STYLE, start_col, end_col)

        return Strip(line.render(self.app.console))

    def _screen_to_content(self, offset: Offset) -> tuple[int, int]:
        """Convert screen coordinates to content coordinates.

        Accounts for scroll offset when converting from screen position to
        content position.

        Parameters
        ----------
        offset : Offset
            Screen position (relative to widget viewport)

        Returns
        -------
        tuple[int, int]
            Content position as (line, column)
        """
        scroll_x, scroll_y = self.scroll_offset
        line = max(0, offset.y + scroll_y)
        col = max(0, offset.x + scroll_x)
        return (line, col)

    def on_mouse_down(self, event) -> None:
        """Handle mouse down event to start selection.

        Parameters
        ----------
        event
            Mouse event from Textual
        """
        if event.button == 3:
            from campers.tui.widgets.context_menu import ContextMenu

            menu = self.app.query_one(ContextMenu)
            disabled = []
            if not self.get_selected_text():
                disabled.append("Copy")
            menu.show_at(event.screen_x, event.screen_y, self, disabled_items=disabled)
            event.stop()
            return

        if event.button != 1:
            return
        self.capture_mouse()
        self._selecting = True
        pos = self._screen_to_content(event.offset)
        self.selection = Selection(start=pos, end=pos)
        self.refresh()

    def on_mouse_move(self, event) -> None:
        """Handle mouse move event to update selection.

        Parameters
        ----------
        event
            Mouse event from Textual
        """
        if not self._selecting:
            return
        pos = self._screen_to_content(event.offset)
        if self.selection:
            self.selection.end = pos
        self.refresh()

    def on_mouse_up(self, event) -> None:
        """Handle mouse up event to end selection.

        Parameters
        ----------
        event
            Mouse event from Textual
        """
        self._selecting = False
        self.release_mouse()

    def get_selected_text(self) -> str:
        """Extract plain text from current selection.

        Handles multi-line selections by extracting the appropriate portion
        of each line.

        Returns
        -------
        str
            Selected text, or empty string if no selection
        """
        if not self.selection:
            return ""

        start, end = self.selection.normalized

        if start[0] >= len(self.lines):
            return ""

        selected_lines = []

        for i in range(start[0], min(end[0] + 1, len(self.lines))):
            line_text = self.lines[i].plain
            if i == start[0] and i == end[0]:
                selected_lines.append(line_text[start[1] : end[1]])
            elif i == start[0]:
                selected_lines.append(line_text[start[1] :])
            elif i == end[0]:
                selected_lines.append(line_text[: end[1]])
            else:
                selected_lines.append(line_text)

        return "\n".join(selected_lines)

    def action_copy(self) -> None:
        """Copy selected text to clipboard.

        Attempts to copy using pyperclip first, falls back to Textual's
        OSC 52 clipboard method if pyperclip fails.
        """
        text = self.get_selected_text()
        if not text:
            return

        try:
            import pyperclip

            pyperclip.copy(text)
            self.app.notify("Copied to clipboard")
        except Exception:
            try:
                self.app.copy_to_clipboard(text)
                self.app.notify("Copied to clipboard")
            except Exception:
                self.app.notify("Clipboard unavailable", severity="warning")

    def on_key(self, event) -> None:
        """Handle key press events.

        Intercepts Ctrl+C when text is selected to prevent event bubbling.
        Allows Ctrl+C to bubble when no text is selected (for quit handler).

        Parameters
        ----------
        event
            Key event from Textual
        """
        if event.key == "ctrl+c" and not self.get_selected_text():
            return
        if event.key == "ctrl+c":
            self.action_copy()
            event.stop()

    def action_select_all(self) -> None:
        """Select all text in the log.

        Updates selection to span from first character to last character
        of the entire log content.
        """
        if not self.lines:
            return
        last_line = len(self.lines) - 1
        last_col = len(self.lines[last_line].plain)
        self.selection = Selection(start=(0, 0), end=(last_line, last_col))
        self.refresh()

    def clear(self) -> None:
        """Clear all lines from the log widget.

        Removes all content, resets selection, updates virtual size, and refreshes display.
        """
        self.lines = []
        self.selection = None
        self.virtual_size = Size(0, 0)
        self.refresh()
