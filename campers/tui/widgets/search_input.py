"""Search input widget for TUI log searching."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container
from textual.message import Message
from textual.widgets import Input, Static


class SearchQueryChanged(Message):
    """Message posted when search query changes.

    Parameters
    ----------
    query : str
        The current search query text
    """

    def __init__(self, query: str) -> None:
        """Initialize SearchQueryChanged message.

        Parameters
        ----------
        query : str
            The current search query text
        """
        self.query = query
        super().__init__()


class SearchClosed(Message):
    """Message posted when search input is closed.

    Parameters
    ----------
    keep_matches : bool
        Whether to preserve matches when closing
    """

    def __init__(self, keep_matches: bool) -> None:
        """Initialize SearchClosed message.

        Parameters
        ----------
        keep_matches : bool
            Whether to preserve matches when closing
        """
        self.keep_matches = keep_matches
        super().__init__()


class SearchInput(Container):
    """Container widget for search input and match count display.

    This widget displays a search input field and a match counter. It docks
    to the bottom of its parent container and can be shown/hidden dynamically.
    """

    DEFAULT_CSS = """
    SearchInput {
        dock: bottom;
        height: 1;
        background: #383838;
        display: none;
        layout: horizontal;
    }

    SearchInput.visible {
        display: block;
    }

    SearchInput Input {
        width: 1fr;
    }

    SearchInput .match-count {
        width: auto;
        padding: 0 2;
        color: #ffffff;
    }
    """

    def __init__(self, **kwargs) -> None:
        """Initialize SearchInput widget.

        Parameters
        ----------
        **kwargs
            Additional keyword arguments passed to Container
        """
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        """Compose child widgets.

        Yields
        ------
        Input
            Text input field for search query
        Static
            Static widget for displaying match count
        """
        yield Input(placeholder="Search...", id="search-query")
        yield Static("", id="match-count", classes="match-count")

    def show(self) -> None:
        """Show the search input and focus the text field.

        Adds the 'visible' class to display the widget and focuses the
        search query input field.
        """
        self.add_class("visible")
        self.query_one("#search-query", Input).focus()

    def hide(self, keep_matches: bool = False) -> None:
        """Hide the search input and post SearchClosed message.

        Parameters
        ----------
        keep_matches : bool
            Whether to preserve matches when closing
        """
        self.remove_class("visible")
        self.query_one("#search-query", Input).value = ""
        self.post_message(SearchClosed(keep_matches=keep_matches))

    def update_match_count(self, current: int, total: int) -> None:
        """Update the match counter display.

        Parameters
        ----------
        current : int
            Index of current match (0-based)
        total : int
            Total number of matches found
        """
        text = "No matches" if total == 0 or current < 0 else f"{current + 1} of {total}"
        self.query_one("#match-count", Static).update(text)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input change.

        Parameters
        ----------
        event : Input.Changed
            Input changed event from the search query field
        """
        self.post_message(SearchQueryChanged(query=event.value))

    def on_key(self, event) -> None:
        """Handle key press events.

        Parameters
        ----------
        event
            Key event from Textual
        """
        if event.key == "escape":
            self.hide(keep_matches=False)
            event.stop()
        elif event.key == "enter":
            self.hide(keep_matches=True)
            event.stop()
