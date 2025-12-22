"""TUI widgets module for campers."""

from campers.tui.widgets.context_menu import ContextMenu
from campers.tui.widgets.labeled_value import LabeledValue
from campers.tui.widgets.search_input import SearchInput
from campers.tui.widgets.selectable_log import SelectableLog
from campers.tui.widgets.selection import Selection


class WidgetID:
    """Constants for TUI widget identifiers."""

    UPTIME = "uptime-widget"
    STATUS = "status-widget"
    SSH = "ssh-widget"
    INSTANCE_TYPE = "instance-type-widget"
    REGION = "region-widget"
    CAMP_NAME = "camp-name-widget"
    COMMAND = "command-widget"
    MUTAGEN = "mutagen-widget"
    PORTFORWARD = "portforward-widget"
    PUBLIC_PORTS = "public-ports-widget"


__all__ = ["ContextMenu", "LabeledValue", "SearchInput", "SelectableLog", "Selection", "WidgetID"]
