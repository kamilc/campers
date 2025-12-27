"""Labeled value widget with aligned display and copyable value."""

from __future__ import annotations

from typing import ClassVar

from rich.style import Style
from rich.text import Text
from textual.widgets import Static

LABEL_WIDTH = 18


class LabeledValue(Static, can_focus=True):
    """A widget that displays a label and value with alignment, supporting value copy.

    The label is left-aligned with fixed width, and the value follows.
    Supports text selection via mouse drag, similar to SelectableLog.

    Parameters
    ----------
    label : str
        The label text (e.g., "Status")
    value : str
        The value text (e.g., "running")
    **kwargs
        Additional keyword arguments passed to Static
    """

    BINDINGS: ClassVar = [
        ("ctrl+c", "copy", "Copy"),
        ("cmd+c", "copy", "Copy"),
    ]

    SELECTION_STYLE: ClassVar = Style(bgcolor="#3465a4", color="white")

    def __init__(self, label: str, value: str = "", **kwargs) -> None:
        """Initialize LabeledValue widget.

        Parameters
        ----------
        label : str
            The label text
        value : str
            The value text
        **kwargs
            Additional keyword arguments passed to Static
        """
        self._label = label
        self._value = value
        self._selection_start: int | None = None
        self._selection_end: int | None = None
        self._selecting = False
        super().__init__(self._format_display(), **kwargs)

    def _format_display(self) -> Text:
        """Format the label and value for display.

        Returns
        -------
        Text
            Rich Text with aligned label and value, with selection styling if selected
        """
        label_with_colon = f"{self._label}:"
        formatted = f"{label_with_colon:<{LABEL_WIDTH}}{self._value}"
        text = Text(formatted)

        if self._selection_start is not None and self._selection_end is not None and self._value:
            start = min(self._selection_start, self._selection_end)
            end = max(self._selection_start, self._selection_end)
            text.stylize(self.SELECTION_STYLE, start, end)

        return text

    @property
    def value(self) -> str:
        """Get the current value.

        Returns
        -------
        str
            The current value text
        """
        return self._value

    @value.setter
    def value(self, new_value: str) -> None:
        """Set the value and update display.

        Parameters
        ----------
        new_value : str
            The new value text
        """
        self._value = new_value
        self.update(self._format_display())

    def _x_to_column(self, x: int) -> int:
        """Convert x coordinate to column position in the formatted text.

        Parameters
        ----------
        x : int
            X coordinate of the click

        Returns
        -------
        int
            Column position, clamped to valid range
        """
        col = max(0, x)
        max_col = LABEL_WIDTH + len(self._value)
        return min(col, max_col)

    def on_mouse_down(self, event) -> None:
        """Handle mouse down event for selection and context menu.

        Left-click starts text selection via drag.
        Right-click shows context menu.

        Parameters
        ----------
        event
            Mouse event from Textual
        """
        if event.button == 1:
            from campers.tui.widgets.context_menu import ContextMenu

            try:
                menu = self.app.query_one(ContextMenu)
                menu.hide()
            except Exception:
                pass

            for widget in self.app.query(LabeledValue):
                if widget is not self:
                    widget.clear_selection()

            self.capture_mouse()
            self._selecting = True
            col = self._x_to_column(event.x)
            self._selection_start = col
            self._selection_end = col
            self.update(self._format_display())
            event.stop()
            return

        if event.button == 2:
            from campers.tui.widgets.context_menu import ContextMenu

            menu = self.app.query_one(ContextMenu)
            disabled = []
            if not self.get_selected_text():
                disabled.append("Copy")
            menu.show_at(event.screen_x, event.screen_y, self, disabled_items=disabled)
            event.stop()

    def on_mouse_move(self, event) -> None:
        """Handle mouse move event to extend selection.

        Parameters
        ----------
        event
            Mouse event from Textual
        """
        if not self._selecting:
            return
        self._selection_end = self._x_to_column(event.x)
        self.update(self._format_display())

    def on_mouse_up(self, event) -> None:
        """Handle mouse up event to end selection.

        Parameters
        ----------
        event
            Mouse event from Textual
        """
        self._selecting = False
        self.release_mouse()

    def action_copy(self) -> None:
        """Copy the selected text to clipboard."""
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

    def get_selected_text(self) -> str:
        """Get the selected text portion.

        Returns
        -------
        str
            The selected text, or empty string if no selection
        """
        if self._selection_start is None or self._selection_end is None:
            return ""

        start = min(self._selection_start, self._selection_end)
        end = max(self._selection_start, self._selection_end)
        full_text = f"{self._label}:{' ' * (LABEL_WIDTH - len(self._label) - 1)}{self._value}"
        return full_text[start:end]

    def clear_selection(self) -> None:
        """Clear the current selection and update display."""
        if self._selection_start is not None or self._selection_end is not None:
            self._selection_start = None
            self._selection_end = None
            self.update(self._format_display())
