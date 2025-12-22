"""Labeled value widget with aligned display and copyable value."""

from __future__ import annotations

from textual.widgets import Static

LABEL_WIDTH = 18


class LabeledValue(Static):
    """A widget that displays a label and value with alignment, supporting value copy.

    The label is left-aligned with fixed width, and the value follows.
    Right-click copies just the value (not the label).

    Parameters
    ----------
    label : str
        The label text (e.g., "Status")
    value : str
        The value text (e.g., "running")
    **kwargs
        Additional keyword arguments passed to Static
    """

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
        super().__init__(self._format_display(), **kwargs)

    def _format_display(self) -> str:
        """Format the label and value for display.

        Returns
        -------
        str
            Formatted string with aligned label and value
        """
        label_with_colon = f"{self._label}:"
        return f"{label_with_colon:<{LABEL_WIDTH}}{self._value}"

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

    def on_mouse_down(self, event) -> None:
        """Handle mouse down event for context menu.

        Parameters
        ----------
        event
            Mouse event from Textual
        """
        if event.button == 2:
            from campers.tui.widgets.context_menu import ContextMenu

            menu = self.app.query_one(ContextMenu)
            menu.show_at(event.screen_x, event.screen_y, self)
            event.stop()

    def action_copy(self) -> None:
        """Copy the value to clipboard (not the label)."""
        if not self._value:
            return

        try:
            import pyperclip

            pyperclip.copy(self._value)
            self.app.notify("Copied to clipboard")
        except Exception:
            try:
                self.app.copy_to_clipboard(self._value)
                self.app.notify("Copied to clipboard")
            except Exception:
                self.app.notify("Clipboard unavailable", severity="warning")

    def get_selected_text(self) -> str:
        """Get the text for copying (returns just the value).

        Returns
        -------
        str
            The value text (not the label)
        """
        return self._value
