"""Step definitions for TUI context menu feature."""

from behave import given, then, when
from behave.runner import Context
from rich.text import Text


class MockSelectableLog:
    """Mock SelectableLog widget for context menu testing."""

    def __init__(self, max_lines: int = 5000) -> None:
        self.lines: list[Text] = []
        self.max_lines = max_lines
        self.selection: tuple[tuple[int, int], tuple[int, int]] | None = None
        self.clipboard_content: str | None = None
        self.notification: str | None = None

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

    def clear(self) -> None:
        """Clear all lines from widget."""
        self.lines = []
        self.selection = None


class MockContextMenu:
    """Mock ContextMenu widget for testing."""

    def __init__(self) -> None:
        self.items = ["Copy", "Search", "Clear"]
        self.visible = False
        self.position = (0, 0)
        self.highlighted_index = 0
        self.disabled_items = []
        self.last_activated_action = None
        self.would_overflow = False

    def show_at(
        self,
        x: int,
        y: int,
        target_widget,
        disabled_items: list[str] | None = None,
    ) -> None:
        """Show context menu at specified position.

        Parameters
        ----------
        x : int
            X coordinate
        y : int
            Y coordinate
        target_widget
            Target widget reference
        disabled_items : list[str] | None
            List of disabled item names
        """
        self.visible = True
        self.target_widget = target_widget
        self.disabled_items = disabled_items or []
        self.highlighted_index = 0

        viewport_width = 200
        viewport_height = 150
        menu_width = 20
        menu_height = len(self.items)

        adjusted_x = x
        adjusted_y = y
        self.would_overflow = False

        if x + menu_width > viewport_width:
            adjusted_x = max(0, x - menu_width)
            self.would_overflow = True

        if y + menu_height > viewport_height:
            adjusted_y = max(0, y - menu_height)
            self.would_overflow = True

        self.position = (adjusted_x, adjusted_y)

    def hide(self) -> None:
        """Hide the context menu."""
        self.visible = False
        self.target_widget = None

    def activate_item(self, index: int) -> None:
        """Activate a menu item by index.

        Parameters
        ----------
        index : int
            Item index
        """
        if index < 0 or index >= len(self.items):
            return

        item_name = self.items[index]
        if item_name in self.disabled_items:
            return

        self.last_activated_action = item_name.lower()
        self.hide()

    def highlight_item(self, index: int) -> None:
        """Highlight a menu item.

        Parameters
        ----------
        index : int
            Item index
        """
        if 0 <= index < len(self.items):
            self.highlighted_index = index


@given("context menu is open")
def step_context_menu_open(context: Context) -> None:
    """Open context menu with SelectableLog reference.

    Parameters
    ----------
    context : Context
        Behave context
    """
    if not hasattr(context, "context_menu"):
        context.context_menu = MockContextMenu()

    disabled = []
    if hasattr(context, "selectable_log"):
        selected_text = context.selectable_log.get_selected_text()
        if not selected_text:
            disabled.append("Copy")

    context.context_menu.show_at(20, 5, context.selectable_log, disabled_items=disabled)


@given("context menu is open with {item} highlighted")
def step_context_menu_open_with_item_highlighted(context: Context, item: str) -> None:
    """Open context menu with specific item highlighted.

    Parameters
    ----------
    context : Context
        Behave context
    item : str
        Item name to highlight
    """
    if not hasattr(context, "context_menu"):
        context.context_menu = MockContextMenu()

    disabled = []
    if hasattr(context, "selectable_log"):
        selected_text = context.selectable_log.get_selected_text()
        if not selected_text:
            disabled.append("Copy")

    context.context_menu.show_at(20, 5, context.selectable_log, disabled_items=disabled)

    if item in context.context_menu.items:
        index = context.context_menu.items.index(item)
        context.context_menu.highlight_item(index)


@given("a SelectableLog widget with {num:d} lines of content")
def step_widget_with_n_lines(context: Context, num: int) -> None:
    """Create widget with N lines of content.

    Parameters
    ----------
    context : Context
        Behave context
    num : int
        Number of lines
    """
    if not hasattr(context, "selectable_log"):
        context.selectable_log = MockSelectableLog()

    for i in range(num):
        context.selectable_log.write(f"Line {i + 1}")


@when("user right-clicks on SelectableLog")
def step_user_right_clicks_widget(context: Context) -> None:
    """Simulate right-click on SelectableLog.

    Parameters
    ----------
    context : Context
        Behave context
    """
    if not hasattr(context, "context_menu"):
        context.context_menu = MockContextMenu()

    disabled = []
    if hasattr(context, "selectable_log"):
        selected_text = context.selectable_log.get_selected_text()
        if not selected_text:
            disabled.append("Copy")

    context.context_menu.show_at(20, 5, context.selectable_log, disabled_items=disabled)
    context.right_click_triggered = True


@when("user right-clicks near viewport edge")
def step_user_right_clicks_near_edge(context: Context) -> None:
    """Simulate right-click near viewport edge.

    Parameters
    ----------
    context : Context
        Behave context
    """
    if not hasattr(context, "context_menu"):
        context.context_menu = MockContextMenu()

    disabled = []
    if hasattr(context, "selectable_log"):
        selected_text = context.selectable_log.get_selected_text()
        if not selected_text:
            disabled.append("Copy")

    context.context_menu.show_at(190, 148, context.selectable_log, disabled_items=disabled)
    context.right_click_triggered = True


@when("user activates {item} from menu")
def step_user_activates_menu_item(context: Context, item: str) -> None:
    """Activate a menu item.

    Parameters
    ----------
    context : Context
        Behave context
    item : str
        Item name
    """
    if item not in context.context_menu.items:
        raise AssertionError(f"Menu item '{item}' not found")

    index = context.context_menu.items.index(item)

    if item == "Copy" and hasattr(context, "selectable_log"):
        context.selectable_log.copy_to_clipboard()

    if item == "Clear" and hasattr(context, "selectable_log"):
        context.selectable_log.clear()

    if item == "Search":
        context.context_menu_search_posted = True

    context.context_menu.activate_item(index)


@when("user clicks outside the menu area")
def step_user_clicks_outside_menu(context: Context) -> None:
    """Simulate click outside menu.

    Parameters
    ----------
    context : Context
        Behave context
    """
    if hasattr(context, "context_menu"):
        context.context_menu.hide()
        context.outside_click = True


@when("user presses Escape")
def step_user_presses_escape(context: Context) -> None:
    """Simulate Escape key press.

    Parameters
    ----------
    context : Context
        Behave context
    """
    if hasattr(context, "context_menu"):
        context.context_menu.hide()
        context.escape_pressed = True


@when("user presses Down arrow")
def step_user_presses_down_arrow(context: Context) -> None:
    """Simulate Down arrow key press.

    Parameters
    ----------
    context : Context
        Behave context
    """
    if hasattr(context, "context_menu"):
        next_index = (context.context_menu.highlighted_index + 1) % len(context.context_menu.items)
        context.context_menu.highlight_item(next_index)


@when("user presses Enter")
def step_user_presses_enter(context: Context) -> None:
    """Simulate Enter key press.

    Parameters
    ----------
    context : Context
        Behave context
    """
    if hasattr(context, "context_menu"):
        item_index = context.context_menu.highlighted_index
        item_name = context.context_menu.items[item_index]

        if item_name not in context.context_menu.disabled_items:
            if item_name == "Clear" and hasattr(context, "selectable_log"):
                context.selectable_log.clear()
            elif item_name == "Copy" and hasattr(context, "selectable_log"):
                context.selectable_log.copy_to_clipboard()
            elif item_name == "Search":
                context.context_menu_search_posted = True

            context.context_menu.activate_item(item_index)


@then("context menu is visible")
def step_context_menu_visible(context: Context) -> None:
    """Verify context menu is visible.

    Parameters
    ----------
    context : Context
        Behave context
    """
    assert hasattr(context, "context_menu"), "Context menu not created"
    assert context.context_menu.visible, "Context menu is not visible"


@then("menu has Copy, Search, Clear items")
def step_menu_has_items(context: Context) -> None:
    """Verify menu has standard items.

    Parameters
    ----------
    context : Context
        Behave context
    """
    expected_items = ["Copy", "Search", "Clear"]
    actual_items = context.context_menu.items

    assert actual_items == expected_items, f"Expected items {expected_items}, got {actual_items}"


@then("Copy menu item is enabled")
def step_copy_menu_item_enabled(context: Context) -> None:
    """Verify Copy item is enabled.

    Parameters
    ----------
    context : Context
        Behave context
    """
    assert "Copy" not in context.context_menu.disabled_items, "Copy should be enabled"


@then("context menu is adjusted within viewport")
def step_context_menu_adjusted(context: Context) -> None:
    """Verify menu position was adjusted for viewport.

    Parameters
    ----------
    context : Context
        Behave context
    """
    assert context.context_menu.would_overflow, "Menu was not adjusted"


@then("context menu is positioned within screen bounds")
def step_menu_positioned_within_bounds(context: Context) -> None:
    """Verify menu is positioned within screen bounds.

    Parameters
    ----------
    context : Context
        Behave context
    """
    x, y = context.context_menu.position
    menu_width = 20
    menu_height = len(context.context_menu.items)

    assert x + menu_width <= 200, "Menu extends beyond right edge"
    assert y + menu_height <= 150, "Menu extends beyond bottom edge"


@then("Copy menu item is disabled")
def step_copy_menu_item_disabled(context: Context) -> None:
    """Verify Copy item is disabled.

    Parameters
    ----------
    context : Context
        Behave context
    """
    assert "Copy" in context.context_menu.disabled_items, "Copy should be disabled"


@then("selecting Copy does nothing")
def step_selecting_copy_does_nothing(context: Context) -> None:
    """Verify Copy activation has no effect when disabled.

    Parameters
    ----------
    context : Context
        Behave context
    """
    copy_index = context.context_menu.items.index("Copy")
    context.context_menu.activate_item(copy_index)
    assert context.context_menu.last_activated_action != "copy", (
        "Copy should not activate when disabled"
    )


@then("widget displays no lines")
def step_widget_displays_no_lines(context: Context) -> None:
    """Verify widget has no content.

    Parameters
    ----------
    context : Context
        Behave context
    """
    assert len(context.selectable_log.lines) == 0, (
        f"Expected 0 lines, got {len(context.selectable_log.lines)}"
    )


@then("all content is cleared")
def step_all_content_cleared(context: Context) -> None:
    """Verify all content is cleared.

    Parameters
    ----------
    context : Context
        Behave context
    """
    assert len(context.selectable_log.lines) == 0, "Widget should have no content"


@then("ContextMenuSearch message is posted")
def step_context_menu_search_posted(context: Context) -> None:
    """Verify ContextMenuSearch message was posted.

    Parameters
    ----------
    context : Context
        Behave context
    """
    assert hasattr(context, "context_menu_search_posted"), (
        "ContextMenuSearch message was not posted"
    )


@then("context menu closes")
def step_context_menu_closes(context: Context) -> None:
    """Verify context menu closes.

    Parameters
    ----------
    context : Context
        Behave context
    """
    assert not context.context_menu.visible, "Context menu should be hidden"


@then("no menu action is performed")
def step_no_menu_action_performed(context: Context) -> None:
    """Verify no menu action was performed.

    Parameters
    ----------
    context : Context
        Behave context
    """
    assert not hasattr(context, "context_menu_search_posted") or (
        not context.context_menu_search_posted
    ), "Action was performed when it should not"


@then("{item} item is highlighted")
def step_item_highlighted(context: Context, item: str) -> None:
    """Verify item is highlighted.

    Parameters
    ----------
    context : Context
        Behave context
    item : str
        Item name
    """
    if item not in context.context_menu.items:
        raise AssertionError(f"Menu item '{item}' not found")

    expected_index = context.context_menu.items.index(item)
    actual_index = context.context_menu.highlighted_index

    assert actual_index == expected_index, (
        f"Expected {item} highlighted at index {expected_index}, got index {actual_index}"
    )
