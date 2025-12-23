"""Selectable log widget for TUI application."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import ClassVar

from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from textual.geometry import Offset, Region, Size, Spacing
from textual.scroll_view import ScrollView
from textual.strip import Strip

from campers.tui.widgets.selection import Selection

logger = logging.getLogger(__name__)


@dataclass
class SearchMatch:
    """Represents a single search match in the log.

    Parameters
    ----------
    line : int
        Line index of the match
    start : int
        Starting column of the match
    end : int
        Ending column of the match
    """

    line: int
    start: int
    end: int


class SelectableLog(ScrollView, can_focus=True):
    """A scrollable log widget with text selection, clipboard, and search support.

    This widget displays log content and allows users to select text with
    the mouse and copy it to the clipboard. It sanitizes ANSI escape codes
    while preserving color information. It also supports vim-like search
    with match highlighting and navigation.

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
    search_query : str | None
        Current search query, or None if no search active
    search_matches : list[SearchMatch]
        List of all search matches found
    current_match_index : int
        Index of current match in matches list
    """

    BINDINGS: ClassVar = [
        ("ctrl+c", "copy", "Copy"),
        ("cmd+c", "copy", "Copy"),
        ("ctrl+a", "select_all", "Select All"),
        ("slash", "open_search", "Search"),
        ("ctrl+f", "open_search", "Search"),
        ("n", "next_match", "Next Match"),
        ("N", "previous_match", "Previous Match"),
        ("f3", "next_match", "Next Match"),
        ("shift+f3", "previous_match", "Previous Match"),
    ]

    SELECTION_STYLE: ClassVar = Style(bgcolor="#3465a4", color="white")
    MATCH_STYLE: ClassVar = Style(bgcolor="yellow", color="black")
    CURRENT_MATCH_STYLE: ClassVar = Style(bgcolor="#ff8c00", color="black", bold=True)

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
        self.search_query: str | None = None
        self.search_matches: list[SearchMatch] = []
        self.current_match_index: int = 0

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

        Accounts for scroll offset and applies match and selection styling.
        Match highlighting is applied first, then selection highlighting takes
        precedence where they overlap.

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

        if self.search_matches:
            for i, match in enumerate(self.search_matches):
                if match.line == line_index:
                    style = (
                        self.CURRENT_MATCH_STYLE
                        if i == self.current_match_index
                        else self.MATCH_STYLE
                    )
                    line.stylize(style, match.start, match.end)

        if self.selection:
            start, end = self.selection.normalized
            if start[0] <= line_index <= end[0]:
                start_col = start[1] if line_index == start[0] else 0
                end_col = end[1] if line_index == end[0] else len(line.plain)
                line.stylize(self.SELECTION_STYLE, start_col, end_col)

        segments = list(line.render(self.app.console))
        bg_color = "#1e1e1e"
        cleaned_segments = []

        for seg in segments:
            if seg.style:
                new_style = Style(
                    color=seg.style.color,
                    bgcolor=seg.style.bgcolor or bg_color,
                    bold=seg.style.bold,
                    dim=seg.style.dim,
                    italic=seg.style.italic,
                    underline=seg.style.underline,
                    strike=seg.style.strike,
                )
            else:
                new_style = Style(bgcolor=bg_color)
            cleaned_segments.append(Segment(seg.text, new_style, seg.control))

        return Strip(cleaned_segments)

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
        if event.button == 2:
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

        from campers.tui.widgets.context_menu import ContextMenu

        try:
            menu = self.app.query_one(ContextMenu)
            menu.hide()
        except Exception:
            pass

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

    def action_open_search(self) -> None:
        """Open the search input widget.

        Shows the SearchInput widget and focuses it for user input.
        """
        from campers.tui.widgets.search_input import SearchInput

        search_input = self.app.query_one(SearchInput)
        search_input.show()

    def find_matches(self, query: str) -> list[SearchMatch]:
        """Find all matches of query in the log content.

        Performs case-insensitive search treating the query as literal text.
        Matches are returned with their line and column positions.

        Parameters
        ----------
        query : str
            Search query (treated as literal text, not regex)

        Returns
        -------
        list[SearchMatch]
            List of SearchMatch objects with positions
        """
        if not query:
            return []

        matches = []
        pattern = re.compile(re.escape(query), re.IGNORECASE)

        for line_idx, line in enumerate(self.lines):
            for match in pattern.finditer(line.plain):
                matches.append(SearchMatch(line=line_idx, start=match.start(), end=match.end()))

        return matches

    def start_search(self, query: str) -> None:
        """Start a new search with the given query.

        Updates search state, finds matches, resets current match index to 0,
        and scrolls to the first match if any are found.

        Parameters
        ----------
        query : str
            Search query text
        """
        self.search_query = query
        self.search_matches = self.find_matches(query)
        self.current_match_index = 0 if self.search_matches else -1

        if self.search_matches:
            self._scroll_to_current_match()

        self.refresh()

    def action_next_match(self) -> None:
        """Navigate to the next search match.

        Advances current_match_index and wraps around when reaching the end.
        Does nothing if no matches are found.
        """
        if not self.search_matches:
            return
        self.current_match_index = (self.current_match_index + 1) % len(self.search_matches)
        self._scroll_to_current_match()
        self._notify_match_count_update()
        self.refresh()

    def action_previous_match(self) -> None:
        """Navigate to the previous search match.

        Decrements current_match_index and wraps around when reaching the start.
        Does nothing if no matches are found.
        """
        if not self.search_matches:
            return
        self.current_match_index = (self.current_match_index - 1) % len(self.search_matches)
        self._scroll_to_current_match()
        self._notify_match_count_update()
        self.refresh()

    def _notify_match_count_update(self) -> None:
        """Update the match count display in SearchInput widget.

        Safely queries for SearchInput and updates match count if available.
        """
        try:
            from campers.tui.widgets.search_input import SearchInput

            search_input = self.app.query_one(SearchInput)
            search_input.update_match_count(self.current_match_index, len(self.search_matches))
        except Exception:
            logger.debug("SearchInput not available for match count update")

    def _scroll_to_current_match(self) -> None:
        """Scroll the view to show the current match.

        Uses scroll_to_region with padding to center the match in the viewport.
        Does nothing if there are no matches or current_match_index is invalid.
        """
        if not self.search_matches or self.current_match_index < 0:
            return
        match = self.search_matches[self.current_match_index]
        region = Region(x=match.start, y=match.line, width=match.end - match.start, height=1)
        self.scroll_to_region(region, spacing=Spacing(top=3, bottom=3))

    def clear_search(self) -> None:
        """Clear all search state.

        Resets search_query, search_matches, and current_match_index.
        Triggers a refresh to remove highlighting.
        """
        self.search_query = None
        self.search_matches = []
        self.current_match_index = 0
        self.refresh()

    def clear(self) -> None:
        """Clear all lines from the log widget.

        Removes all content, resets selection, updates virtual size, and refreshes display.
        """
        self.lines = []
        self.selection = None
        self.virtual_size = Size(0, 0)
        self.refresh()
