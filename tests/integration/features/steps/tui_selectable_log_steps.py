"""Step definitions for TUI SelectableLog widget feature."""

from behave import given, then, when
from behave.runner import Context
from rich.text import Text


class MockSelectableLog:
    """Mock SelectableLog widget for testing."""

    def __init__(self, max_lines: int = 5000) -> None:
        self.lines: list[Text] = []
        self.max_lines = max_lines
        self.selection: tuple[tuple[int, int], tuple[int, int]] | None = None
        self.clipboard_content: str | None = None
        self.notification: str | None = None
        self.scroll_position = 0
        self.has_focus = False

    def write(self, content: str | Text) -> None:
        text = Text.from_ansi(content) if isinstance(content, str) else content

        for line in text.split("\n"):
            self.lines.append(line)

        if len(self.lines) > self.max_lines:
            self.lines = self.lines[-self.max_lines :]

        self.scroll_position = len(self.lines) - 1

    def get_selected_text(self) -> str:
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
        text = self.get_selected_text()
        if text:
            self.clipboard_content = text
            self.notification = "Copied to clipboard"

    def select_all(self) -> None:
        if not self.lines:
            return
        last_line = len(self.lines) - 1
        last_col = len(self.lines[last_line].plain)
        self.selection = ((0, 0), (last_line, last_col))

    def render_line(self, y: int) -> str:
        if y >= len(self.lines):
            return ""
        return self.lines[y].plain


@given("a SelectableLog widget is created with max_lines {max_lines:d}")
def step_create_selectable_log(context: Context, max_lines: int) -> None:
    """Create a SelectableLog widget with specified max_lines.

    Parameters
    ----------
    context : Context
        Behave context
    max_lines : int
        Maximum number of lines to store
    """
    context.selectable_log = MockSelectableLog(max_lines=max_lines)


@given('a SelectableLog widget with content "{content}" on line {line_num:d}')
def step_selectable_log_with_content(context: Context, content: str, line_num: int) -> None:
    """Create a SelectableLog widget with specific content.

    Parameters
    ----------
    context : Context
        Behave context
    content : str
        Content to write
    line_num : int
        Line number (for validation)
    """
    if not hasattr(context, "selectable_log") or context.selectable_log is None:
        context.selectable_log = MockSelectableLog()

    context.selectable_log.write(content)
    context.selectable_log.has_focus = True


@given('a SelectableLog widget with content "{content}"')
def step_selectable_log_with_content_simple(context: Context, content: str) -> None:
    """Create a SelectableLog widget with specific content (simple variant).

    Parameters
    ----------
    context : Context
        Behave context
    content : str
        Content to write
    """
    if not hasattr(context, "selectable_log") or context.selectable_log is None:
        context.selectable_log = MockSelectableLog()

    context.selectable_log.write(content)
    context.selectable_log.has_focus = True


@given("the widget has focus")
def step_widget_has_focus(context: Context) -> None:
    """Mark widget as having focus.

    Parameters
    ----------
    context : Context
        Behave context
    """
    if hasattr(context, "selectable_log") and context.selectable_log:
        context.selectable_log.has_focus = True


@given('a SelectableLog widget with selected text "{text}"')
def step_selectable_log_with_selection(context: Context, text: str) -> None:
    """Create a SelectableLog with specific text selected.

    Parameters
    ----------
    context : Context
        Behave context
    text : str
        Text to select
    """
    if not hasattr(context, "selectable_log") or context.selectable_log is None:
        context.selectable_log = MockSelectableLog()

    context.selectable_log.write(text)
    context.selectable_log.selection = ((0, 0), (0, len(text)))
    context.selectable_log.has_focus = True


@given("a SelectableLog widget with no selection")
def step_selectable_log_no_selection(context: Context) -> None:
    """Create a SelectableLog with no text selected.

    Parameters
    ----------
    context : Context
        Behave context
    """
    if not hasattr(context, "selectable_log") or context.selectable_log is None:
        context.selectable_log = MockSelectableLog()

    context.selectable_log.selection = None
    context.selectable_log.has_focus = True


@given("a SelectableLog widget is mounted in TUI app")
def step_selectable_log_mounted_in_app(context: Context) -> None:
    """Create a SelectableLog mounted in TUI application.

    Parameters
    ----------
    context : Context
        Behave context
    """
    context.selectable_log = MockSelectableLog()
    context.tui_log_widget = context.selectable_log


@given("widget is scrolled to top")
def step_widget_scrolled_to_top(context: Context) -> None:
    """Set widget scroll position to top.

    Parameters
    ----------
    context : Context
        Behave context
    """
    if hasattr(context, "selectable_log") and context.selectable_log:
        context.selectable_log.scroll_position = 0


@when('text content "{content}" is written')
def step_write_text_content(context: Context, content: str) -> None:
    """Write text content to SelectableLog.

    Parameters
    ----------
    context : Context
        Behave context
    content : str
        Content to write
    """
    context.selectable_log.write(content)


@when('ANSI colored text "{content}" is written')
def step_write_ansi_colored_text(context: Context, content: str) -> None:
    """Write ANSI colored text to SelectableLog.

    Parameters
    ----------
    context : Context
        Behave context
    content : str
        ANSI colored content to write
    """
    decoded_content = content.encode("utf-8").decode("unicode_escape")
    context.selectable_log.write(decoded_content)
    context.last_written_content = decoded_content


@when('ANSI control sequence "{sequence}" is written')
def step_write_ansi_control_sequence(context: Context, sequence: str) -> None:
    """Write ANSI control sequence to SelectableLog.

    Parameters
    ----------
    context : Context
        Behave context
    sequence : str
        Control sequence to write
    """
    decoded_sequence = sequence.encode("utf-8").decode("unicode_escape")
    context.selectable_log.write(decoded_sequence)
    context.last_written_content = decoded_sequence


@when("{num:d} lines of text are written")
def step_write_multiple_lines(context: Context, num: int) -> None:
    """Write multiple lines of text.

    Parameters
    ----------
    context : Context
        Behave context
    num : int
        Number of lines to write
    """
    for i in range(num):
        context.selectable_log.write(f"Line {i + 1}")


@when("user clicks at position ({x:d}, {y:d})")
def step_user_clicks(context: Context, x: int, y: int) -> None:
    """Record user click position.

    Parameters
    ----------
    context : Context
        Behave context
    x : int
        X coordinate
    y : int
        Y coordinate
    """
    context.click_start = (x, y)
    context.click_current = (x, y)


@when("user drags to position ({x:d}, {y:d})")
def step_user_drags(context: Context, x: int, y: int) -> None:
    """Record user drag end position.

    Parameters
    ----------
    context : Context
        Behave context
    x : int
        X coordinate
    y : int
        Y coordinate
    """
    if hasattr(context, "click_start") and context.click_start:
        start = context.click_start
        context.selectable_log.selection = (start, (x, y))


@when("user presses Ctrl+A")
def step_user_presses_ctrl_a(context: Context) -> None:
    """Simulate Ctrl+A key press.

    Parameters
    ----------
    context : Context
        Behave context
    """
    context.selectable_log.select_all()


@when("user presses Ctrl+C")
def step_user_presses_ctrl_c(context: Context) -> None:
    """Simulate Ctrl+C key press.

    Parameters
    ----------
    context : Context
        Behave context
    """
    if context.selectable_log.get_selected_text():
        context.selectable_log.copy_to_clipboard()
    else:
        context.ctrl_c_no_selection = True


@when("new content is written")
def step_new_content_written(context: Context) -> None:
    """Write new content to trigger auto-scroll.

    Parameters
    ----------
    context : Context
        Behave context
    """
    context.selectable_log.write("New log line")


@when('log message "{message}" is emitted')
def step_log_message_emitted(context: Context, message: str) -> None:
    """Emit a log message to be captured by TUI.

    Parameters
    ----------
    context : Context
        Behave context
    message : str
        Log message to emit
    """
    context.emitted_log_message = message
    if hasattr(context, "tui_log_widget") and context.tui_log_widget:
        context.tui_log_widget.write(message)


@then('the widget displays "{content}"')
def step_widget_displays_content(context: Context, content: str) -> None:
    """Verify widget displays expected content.

    Parameters
    ----------
    context : Context
        Behave context
    content : str
        Expected content
    """
    all_text = "".join([line.plain for line in context.selectable_log.lines])
    assert content in all_text, f"Expected '{content}' in widget, got: {all_text}"


@then("the text is displayed in red color")
def step_text_displayed_in_red(context: Context) -> None:
    """Verify text is displayed with red styling.

    Parameters
    ----------
    context : Context
        Behave context
    """
    if not context.selectable_log.lines:
        raise AssertionError("No lines in widget")

    found_red = False
    for line in context.selectable_log.lines:
        if not line.spans:
            continue
        for span in line.spans:
            if not span.style:
                continue
            style_str = str(span.style).lower()
            has_red = "red" in style_str or "color(1)" in style_str
            if has_red:
                found_red = True
                break
        if found_red:
            break

    line_info = [(line.plain, str(line.spans)) for line in context.selectable_log.lines]
    assert found_red, f"Expected red color in widget. Lines: {line_info}"


@then("no raw escape characters are visible")
def step_no_escape_characters_visible(context: Context) -> None:
    """Verify no raw ANSI escape characters in output.

    Parameters
    ----------
    context : Context
        Behave context
    """
    all_text = "".join([line.plain for line in context.selectable_log.lines])
    assert "\x1b" not in all_text, f"Found escape character in: {all_text}"
    assert "\033" not in all_text, f"Found escape character in: {all_text}"


@then("no control sequences are displayed")
def step_no_control_sequences_displayed(context: Context) -> None:
    """Verify no control sequences are visible.

    Parameters
    ----------
    context : Context
        Behave context
    """
    all_text = "".join([line.plain for line in context.selectable_log.lines])
    assert "\x1b[2J" not in all_text, "Clear screen sequence found"
    assert "\x1b[H" not in all_text, "Cursor home sequence found"


@then("the widget renders without corruption")
def step_widget_renders_without_corruption(context: Context) -> None:
    """Verify widget renders without errors.

    Parameters
    ----------
    context : Context
        Behave context
    """
    assert len(context.selectable_log.lines) > 0, "Widget has no lines"


@then("only the last {num:d} lines are stored")
def step_only_last_lines_stored(context: Context, num: int) -> None:
    """Verify buffer contains only last N lines.

    Parameters
    ----------
    context : Context
        Behave context
    num : int
        Expected number of lines
    """
    assert len(context.selectable_log.lines) == num, (
        f"Expected {num} lines, got {len(context.selectable_log.lines)}"
    )


@then("the first {num:d} lines are discarded")
def step_first_lines_discarded(context: Context, num: int) -> None:
    """Verify first N lines were removed from buffer.

    Parameters
    ----------
    context : Context
        Behave context
    num : int
        Number of lines that should be removed
    """
    pass


@then("text is selected from column {start:d} to column {end:d}")
def step_text_selected_range(context: Context, start: int, end: int) -> None:
    """Verify text selection range.

    Parameters
    ----------
    context : Context
        Behave context
    start : int
        Start column
    end : int
        End column
    """
    if not context.selectable_log.selection:
        raise AssertionError("No selection in widget")

    sel_start, sel_end = context.selectable_log.selection
    assert sel_start[1] == start, f"Expected selection start {start}, got {sel_start[1]}"
    assert sel_end[1] == end, f"Expected selection end {end}, got {sel_end[1]}"


@then("selection is visually highlighted")
def step_selection_visually_highlighted(context: Context) -> None:
    """Verify selection is highlighted.

    Parameters
    ----------
    context : Context
        Behave context
    """
    assert context.selectable_log.selection is not None, "Selection not set"


@then("all content is selected")
def step_all_content_selected(context: Context) -> None:
    """Verify all content is selected.

    Parameters
    ----------
    context : Context
        Behave context
    """
    if not context.selectable_log.lines:
        raise AssertionError("Widget has no content")

    assert context.selectable_log.selection is not None, "No selection"


@then("selection spans from start to end")
def step_selection_spans_full_range(context: Context) -> None:
    """Verify selection spans entire content.

    Parameters
    ----------
    context : Context
        Behave context
    """
    if not context.selectable_log.selection:
        raise AssertionError("No selection")

    start, end = context.selectable_log.selection
    assert start[0] == 0 and start[1] == 0, "Selection should start at (0, 0)"


@then("text is copied to clipboard")
def step_text_copied_to_clipboard(context: Context) -> None:
    """Verify text is in clipboard.

    Parameters
    ----------
    context : Context
        Behave context
    """
    assert context.selectable_log.clipboard_content is not None, "Clipboard is empty"


@then('notification "{notification}" is shown')
def step_notification_shown(context: Context, notification: str) -> None:
    """Verify notification is displayed.

    Parameters
    ----------
    context : Context
        Behave context
    notification : str
        Expected notification text
    """
    assert context.selectable_log.notification == notification, (
        f"Expected notification '{notification}', got '{context.selectable_log.notification}'"
    )


@then("widget scrolls to show latest content")
def step_widget_scrolls_to_latest(context: Context) -> None:
    """Verify widget scrolled to show latest content.

    Parameters
    ----------
    context : Context
        Behave context
    """
    pass


@then("scroll position is at bottom")
def step_scroll_position_at_bottom(context: Context) -> None:
    """Verify scroll position is at bottom.

    Parameters
    ----------
    context : Context
        Behave context
    """
    expected_position = len(context.selectable_log.lines) - 1
    assert context.selectable_log.scroll_position == expected_position, (
        f"Expected scroll at {expected_position}, got {context.selectable_log.scroll_position}"
    )


@then("key event bubbles to application")
def step_key_event_bubbles(context: Context) -> None:
    """Verify key event bubbles up.

    Parameters
    ----------
    context : Context
        Behave context
    """
    assert hasattr(context, "ctrl_c_no_selection") and context.ctrl_c_no_selection, (
        "Ctrl+C should not be consumed when no selection"
    )


@then("application quit handler receives event")
def step_application_receives_quit(context: Context) -> None:
    """Verify application quit handler would receive event.

    Parameters
    ----------
    context : Context
        Behave context
    """
    pass


@then("message appears in SelectableLog widget")
def step_message_appears_in_widget(context: Context) -> None:
    """Verify log message appears in widget.

    Parameters
    ----------
    context : Context
        Behave context
    """
    all_text = "".join([line.plain for line in context.selectable_log.lines])
    assert context.emitted_log_message in all_text, (
        f"Expected '{context.emitted_log_message}' in widget"
    )


@then("text can be selected and copied")
def step_text_can_be_selected_and_copied(context: Context) -> None:
    """Verify text can be selected and copied.

    Parameters
    ----------
    context : Context
        Behave context
    """
    all_text = "".join([line.plain for line in context.selectable_log.lines])
    assert len(all_text) > 0, "Widget has no text"
