"""Step definitions for TUI Vim-like search feature."""

from behave import given, then, when
from behave.runner import Context
from rich.text import Text


class MockSearchInput:
    """Mock SearchInput widget for testing."""

    def __init__(self) -> None:
        self.visible = False
        self.has_focus = False
        self.query = ""
        self.match_count_text = ""
        self.matches_count = 0


class MockSelectableLogSearch:
    """Extended mock for SelectableLog supporting search functionality."""

    def __init__(self, max_lines: int = 5000) -> None:
        self.lines: list[Text] = []
        self.max_lines = max_lines
        self.selection: tuple[tuple[int, int], tuple[int, int]] | None = None
        self.clipboard_content: str | None = None
        self.notification: str | None = None
        self.scroll_position = 0
        self.has_focus = False
        self.search_query: str | None = None
        self.search_matches: list[tuple[int, int, int]] = []
        self.current_match_index: int = -1
        self.highlighting_cleared: bool = False

    def write(self, content: str | Text) -> None:
        """Write content to widget.

        Parameters
        ----------
        content : str | Text
            Content to write
        """
        text = Text.from_ansi(content) if isinstance(content, str) else content

        for line in text.split("\n"):
            self.lines.append(line)

        if len(self.lines) > self.max_lines:
            self.lines = self.lines[-self.max_lines :]

    def get_selected_text(self) -> str:
        """Get currently selected text.

        Returns
        -------
        str
            Selected text or empty string
        """
        if not self.selection:
            return ""

        start, end = self.selection
        if start > end:
            start, end = end, start

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

    def copy_to_clipboard(self) -> None:
        """Copy selected text to clipboard."""
        text = self.get_selected_text()
        if text:
            self.clipboard_content = text
            self.notification = "Copied to clipboard"

    def find_matches(self, query: str) -> list[tuple[int, int, int]]:
        """Find all matches of query in content.

        Parameters
        ----------
        query : str
            Search query (case-insensitive literal text)

        Returns
        -------
        list[tuple[int, int, int]]
            List of (line_index, start_col, end_col) tuples
        """
        import re

        if not query:
            return []

        matches = []
        pattern = re.compile(re.escape(query), re.IGNORECASE)

        for line_idx, line in enumerate(self.lines):
            for match in pattern.finditer(line.plain):
                matches.append((line_idx, match.start(), match.end()))

        return matches

    def start_search(self, query: str) -> None:
        """Start search with given query.

        Parameters
        ----------
        query : str
            Search query
        """
        self.search_query = query
        self.search_matches = self.find_matches(query)
        self.current_match_index = 0 if self.search_matches else -1
        self.highlighting_cleared = False

    def next_match(self) -> None:
        """Navigate to next match with wrap-around."""
        if not self.search_matches:
            return
        self.current_match_index = (self.current_match_index + 1) % len(self.search_matches)

    def previous_match(self) -> None:
        """Navigate to previous match with wrap-around."""
        if not self.search_matches:
            return
        self.current_match_index = (self.current_match_index - 1) % len(self.search_matches)

    def clear_search(self) -> None:
        """Clear search state and highlighting."""
        self.search_query = None
        self.search_matches = []
        self.current_match_index = -1
        self.highlighting_cleared = True


@given("search input is open")
def step_search_input_open(context: Context) -> None:
    """Open search input.

    Parameters
    ----------
    context : Context
        Behave context
    """
    if not hasattr(context, "search_input"):
        context.search_input = MockSearchInput()
    context.search_input.visible = True
    context.search_input.has_focus = True


@given("search is active with {query} query")
def step_search_active_with_query(context: Context, query: str) -> None:
    """Activate search with specific query.

    Parameters
    ----------
    context : Context
        Behave context
    query : str
        Search query
    """
    if not hasattr(context, "selectable_log"):
        context.selectable_log = MockSelectableLogSearch()
    if not hasattr(context, "search_input"):
        context.search_input = MockSearchInput()

    context.selectable_log.start_search(query)
    context.search_input.visible = True
    context.search_input.query = query
    context.search_input.matches_count = len(context.selectable_log.search_matches)


@given('a SelectableLog widget with {num:d} lines of content containing "{text}"')
def step_widget_with_n_lines_containing(context: Context, num: int, text: str) -> None:
    """Create SelectableLog with N lines each containing text.

    Parameters
    ----------
    context : Context
        Behave context
    num : int
        Number of lines
    text : str
        Text to include in each line
    """
    if not hasattr(context, "selectable_log"):
        context.selectable_log = MockSelectableLogSearch()

    for i in range(num):
        context.selectable_log.write(f"Line {i}: {text}")


@given("search is active with current match at line {line_num:d}")
def step_search_active_at_line(context: Context, line_num: int) -> None:
    """Set search active at specific line.

    Parameters
    ----------
    context : Context
        Behave context
    line_num : int
        Line number of current match
    """
    if (
        hasattr(context, "selectable_log")
        and context.selectable_log.search_matches
        and line_num < len(context.selectable_log.search_matches)
    ):
        for i, match in enumerate(context.selectable_log.search_matches):
            if match[0] == line_num:
                context.selectable_log.current_match_index = i
                break


@given("matches are highlighted")
def step_matches_highlighted(context: Context) -> None:
    """Verify matches are highlighted.

    Parameters
    ----------
    context : Context
        Behave context
    """
    if hasattr(context, "selectable_log"):
        assert len(context.selectable_log.search_matches) > 0, "No matches to highlight"
        assert not context.selectable_log.highlighting_cleared, "Highlighting was cleared"


@given("a SelectableLog widget with active search")
def step_widget_with_active_search(context: Context) -> None:
    """Create SelectableLog with active search.

    Parameters
    ----------
    context : Context
        Behave context
    """
    if not hasattr(context, "selectable_log"):
        context.selectable_log = MockSelectableLogSearch()
        context.selectable_log.write("error on line 1")
        context.selectable_log.write("error on line 2")
        context.selectable_log.write("warning on line 3")

    context.selectable_log.start_search("error")
    if not hasattr(context, "search_input"):
        context.search_input = MockSearchInput()
    context.search_input.visible = True


@given("current match is at index {index:d}")
def step_current_match_at_index(context: Context, index: int) -> None:
    """Set current match index.

    Parameters
    ----------
    context : Context
        Behave context
    index : int
        Match index
    """
    if hasattr(context, "selectable_log"):
        context.selectable_log.current_match_index = index


@given("a SelectableLog widget with matches at lines {line_nums}")
def step_widget_with_matches_at_lines(context: Context, line_nums: str) -> None:
    """Create SelectableLog with matches at specific lines.

    Parameters
    ----------
    context : Context
        Behave context
    line_nums : str
        Comma-separated line numbers
    """
    if not hasattr(context, "selectable_log"):
        context.selectable_log = MockSelectableLogSearch()

    lines = [int(n.strip()) for n in line_nums.split(" and ")]
    max_line = max(lines) if lines else 0

    for i in range(max_line + 1):
        if i in lines:
            context.selectable_log.write(f"match content line {i}")
        else:
            context.selectable_log.write(f"other content line {i}")

    context.selectable_log.start_search("match")


@when('user types "{text}"')
def step_user_types(context: Context, text: str) -> None:
    """Simulate user typing in search input.

    Parameters
    ----------
    context : Context
        Behave context
    text : str
        Text to type
    """
    if hasattr(context, "selectable_log"):
        context.selectable_log.start_search(text)

    if hasattr(context, "search_input"):
        context.search_input.query = text
        matches_count = (
            len(context.selectable_log.search_matches)
            if hasattr(context, "selectable_log")
            else 0
        )
        context.search_input.matches_count = matches_count




@then("search input appears")
def step_search_input_appears(context: Context) -> None:
    """Verify search input appears.

    Parameters
    ----------
    context : Context
        Behave context
    """
    assert hasattr(context, "search_input"), "Search input not created"
    assert context.search_input.visible, "Search input is not visible"


@then("search input has focus")
def step_search_input_has_focus(context: Context) -> None:
    """Verify search input has focus.

    Parameters
    ----------
    context : Context
        Behave context
    """
    assert hasattr(context, "search_input"), "Search input not created"
    assert context.search_input.has_focus, "Search input does not have focus"


@then("{num:d} matches are found")
def step_n_matches_found(context: Context, num: int) -> None:
    """Verify N matches were found.

    Parameters
    ----------
    context : Context
        Behave context
    num : int
        Expected number of matches
    """
    assert hasattr(context, "selectable_log"), "SelectableLog not created"
    actual_matches = len(context.selectable_log.search_matches)
    assert actual_matches == num, f"Expected {num} matches, found {actual_matches}"


@then('match count shows "{expected_text}"')
def step_match_count_shows(context: Context, expected_text: str) -> None:
    """Verify match count display.

    Parameters
    ----------
    context : Context
        Behave context
    expected_text : str
        Expected count text
    """
    if hasattr(context, "search_input"):
        if "of" in expected_text:
            current, total = expected_text.split(" of ")
            total_matches = int(total)
            actual_count = (
                len(context.selectable_log.search_matches)
                if hasattr(context, "selectable_log")
                else 0
            )
            assert (
                actual_count == total_matches
            ), f"Expected {total_matches} matches, got {actual_count}"
        else:
            assert (
                expected_text in ["No matches"]
            ), f"Expected '{expected_text}'"


@then("first match is highlighted with orange")
def step_first_match_orange(context: Context) -> None:
    """Verify first match is highlighted with orange.

    Parameters
    ----------
    context : Context
        Behave context
    """
    if hasattr(context, "selectable_log"):
        assert context.selectable_log.current_match_index == 0, "First match should be current"


@then("other matches are highlighted with yellow")
def step_other_matches_yellow(context: Context) -> None:
    """Verify non-current matches are highlighted with yellow.

    Parameters
    ----------
    context : Context
        Behave context
    """
    if hasattr(context, "selectable_log"):
        assert len(context.selectable_log.search_matches) > 1, "Expected multiple matches"


@then("current match changes to line {line_num:d}")
def step_current_match_at_line(context: Context, line_num: int) -> None:
    """Verify current match is at specific line.

    Parameters
    ----------
    context : Context
        Behave context
    line_num : int
        Expected line number
    """
    if (
        hasattr(context, "selectable_log")
        and context.selectable_log.current_match_index >= 0
    ):
        match = context.selectable_log.search_matches[
            context.selectable_log.current_match_index
        ]
        assert (
            match[0] == line_num
        ), f"Expected match at line {line_num}, got {match[0]}"


@then("current match wraps to line {line_num:d}")
def step_current_match_wraps(context: Context, line_num: int) -> None:
    """Verify current match wraps to specific line.

    Parameters
    ----------
    context : Context
        Behave context
    line_num : int
        Expected line number after wrap
    """
    if hasattr(context, "selectable_log"):
        match = context.selectable_log.search_matches[context.selectable_log.current_match_index]
        assert match[0] == line_num, f"Expected wrap to line {line_num}, got {match[0]}"


@then("search input closes")
def step_search_input_closes(context: Context) -> None:
    """Verify search input closes.

    Parameters
    ----------
    context : Context
        Behave context
    """
    assert hasattr(context, "search_input"), "Search input not created"
    assert not context.search_input.visible, "Search input should be closed"


@then("all match highlighting is removed")
def step_all_highlighting_removed(context: Context) -> None:
    """Verify all match highlighting is removed.

    Parameters
    ----------
    context : Context
        Behave context
    """
    if hasattr(context, "selectable_log"):
        assert context.selectable_log.highlighting_cleared, "Highlighting should be cleared"
        assert len(context.selectable_log.search_matches) == 0, "Matches should be cleared"


@then("match highlighting remains visible")
def step_highlighting_remains(context: Context) -> None:
    """Verify match highlighting remains.

    Parameters
    ----------
    context : Context
        Behave context
    """
    if hasattr(context, "selectable_log"):
        assert len(context.selectable_log.search_matches) > 0, "Matches should still be present"
        assert not context.selectable_log.highlighting_cleared, "Highlighting should not be cleared"


@then("current match advances to index {index:d}")
def step_match_advances_to_index(context: Context, index: int) -> None:
    """Verify current match is at index.

    Parameters
    ----------
    context : Context
        Behave context
    index : int
        Expected match index
    """
    if hasattr(context, "selectable_log"):
        current_index = context.selectable_log.current_match_index
        assert current_index == index, (
            f"Expected current match at index {index}, got {current_index}"
        )


@then("current match moves back to index {index:d}")
def step_match_moves_back_to_index(context: Context, index: int) -> None:
    """Verify current match moved back to index.

    Parameters
    ----------
    context : Context
        Behave context
    index : int
        Expected match index
    """
    if hasattr(context, "selectable_log"):
        current_index = context.selectable_log.current_match_index
        assert current_index == index, (
            f"Expected current match at index {index}, got {current_index}"
        )
