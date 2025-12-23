"""Context menu widget for right-click actions on selectable widgets."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from textual.containers import Container
from textual.message import Message
from textual.widgets import Static

if TYPE_CHECKING:
    from textual.app import ComposeResult

logger = logging.getLogger(__name__)


class ContextMenu(Container):
    """A context menu widget that appears on right-click at mouse coordinates.

    This is a reusable component that can be used with any widget. It displays
    a list of menu items that the user can activate via clicking or keyboard
    navigation.

    Parameters
    ----------
    items : list[str] | None
        List of menu item labels (default: ["Copy", "Search", "Clear"])
    **kwargs
        Additional keyword arguments passed to Container

    Attributes
    ----------
    items : list[str]
        List of menu item labels
    highlighted_index : int
        Index of currently highlighted menu item
    target_widget
        Reference to the widget that triggered the context menu
    disabled_items : list[str]
        List of item labels that are currently disabled
    """

    DEFAULT_CSS = """
    ContextMenu {
        position: absolute;
        width: 20;
        height: auto;
        background: #383838;
        border: solid #606060;
        display: none;
        layer: overlay;
    }

    ContextMenu.visible {
        display: block;
    }

    ContextMenu .menu-item {
        padding: 0 2;
        height: 1;
        color: #ffffff;
    }

    ContextMenu .menu-item:hover {
        background: #505050;
    }

    ContextMenu .menu-item.disabled {
        color: #808080;
    }

    ContextMenu .menu-item.highlighted {
        background: #505050;
    }
    """

    class ItemSelected(Message):
        """Posted when a menu item is selected.

        Parameters
        ----------
        action : str
            Name of the selected action (lowercase item name)
        target_widget
            Reference to the widget that triggered the context menu
        """

        def __init__(self, action: str, target_widget) -> None:
            self.action = action
            self.target_widget = target_widget
            super().__init__()

    def __init__(self, items: list[str] | None = None, **kwargs) -> None:
        """Initialize ContextMenu widget.

        Parameters
        ----------
        items : list[str] | None
            List of menu item labels (default: ["Copy", "Search", "Clear"])
        **kwargs
            Additional keyword arguments passed to Container
        """
        super().__init__(**kwargs)
        self._items = items if items is not None else ["Copy", "Search", "Clear"]
        self._highlighted_index = 0
        self._target_widget = None
        self._disabled_items: list[str] = []
        self._would_overflow = False

    def compose(self) -> ComposeResult:
        """Compose menu items.

        Yields
        ------
        Static
            A Static widget for each menu item
        """
        for item in self._items:
            yield Static(item, classes="menu-item")

    def show_at(
        self,
        x: int,
        y: int,
        target_widget,
        disabled_items: list[str] | None = None,
    ) -> None:
        """Show context menu at specified position.

        Adjusts position if menu would overflow viewport bounds.

        Parameters
        ----------
        x : int
            X coordinate (screen position)
        y : int
            Y coordinate (screen position)
        target_widget
            Reference to widget that triggered this menu
        disabled_items : list[str] | None
            List of item names to disable (default: [])
        """
        self._target_widget = target_widget
        self._highlighted_index = 0
        self._disabled_items = disabled_items or []

        viewport_width = self.app.size.width
        viewport_height = self.app.size.height
        menu_width = 20
        menu_height = len(self._items)

        adjusted_x = x
        adjusted_y = y
        self._would_overflow = False

        if x + menu_width > viewport_width:
            adjusted_x = max(0, x - menu_width)
            self._would_overflow = True

        if y + menu_height > viewport_height:
            adjusted_y = max(0, y - menu_height)
            self._would_overflow = True

        self.styles.offset = (adjusted_x, adjusted_y)
        self.add_class("visible")
        self._update_disabled_state()
        self.focus()
        self._update_highlight()

    def hide(self) -> None:
        """Hide the context menu."""
        self.remove_class("visible")
        self._target_widget = None

    def _update_disabled_state(self) -> None:
        """Update CSS classes for disabled items."""
        items = self.query(".menu-item")
        for i, item in enumerate(items):
            if self._items[i] in self._disabled_items:
                item.add_class("disabled")
            else:
                item.remove_class("disabled")

    def _update_highlight(self) -> None:
        """Update CSS classes for highlighted item."""
        items = self.query(".menu-item")
        for i, item in enumerate(items):
            if i == self._highlighted_index:
                item.add_class("highlighted")
            else:
                item.remove_class("highlighted")

    def on_key(self, event) -> None:
        """Handle key press events.

        Parameters
        ----------
        event
            Key event from Textual
        """
        if event.key == "escape":
            self.hide()
            event.stop()
        elif event.key == "up":
            self._highlighted_index = (self._highlighted_index - 1) % len(self._items)
            self._update_highlight()
            event.stop()
        elif event.key == "down":
            self._highlighted_index = (self._highlighted_index + 1) % len(self._items)
            self._update_highlight()
            event.stop()
        elif event.key == "enter":
            self._activate_item(self._highlighted_index)
            event.stop()

    def on_click(self, event) -> None:
        """Handle mouse click on menu items.

        Parameters
        ----------
        event
            Click event from Textual
        """
        for i, item in enumerate(self.query(".menu-item")):
            if item.region.contains(event.screen_x, event.screen_y):
                self._activate_item(i)
                return

    def on_blur(self, event) -> None:
        """Handle blur event to close menu when clicking outside.

        Parameters
        ----------
        event
            Blur event from Textual
        """
        self.hide()

    def _activate_item(self, index: int) -> None:
        """Activate a menu item by index.

        Parameters
        ----------
        index : int
            Index of item to activate
        """
        if index < 0 or index >= len(self._items):
            return

        item_name = self._items[index]
        if item_name in self._disabled_items:
            return

        action = item_name.lower()
        target = self._target_widget
        self.post_message(self.ItemSelected(action, target))
        self.hide()

    @property
    def would_overflow(self) -> bool:
        """Check if menu position required adjustment for viewport bounds.

        Returns
        -------
        bool
            True if menu would overflow and was adjusted, False otherwise
        """
        return self._would_overflow

    @property
    def items(self) -> list[str]:
        """Get menu items.

        Returns
        -------
        list[str]
            List of menu item labels
        """
        return self._items
