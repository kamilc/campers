"""CSS styling for TUI application."""

TUI_CSS = """
Screen {
    layers: base overlay;
}
#status-panel {
    height: auto;
    background: #383838;
    padding: 1;
}
#log-panel {
    height: 1fr;
}
InstanceOverviewWidget {
    height: 1;
    background: #383838;
    content-align: center middle;
    text-style: dim;
}
RichLog {
    scrollbar-background: #383838;
    scrollbar-color: #606060;
    scrollbar-background-hover: #404040;
    scrollbar-color-hover: #707070;
    scrollbar-background-active: #383838;
    scrollbar-color-active: #606060;
}
SelectableLog {
    background: #1e1e1e;
}
LabeledValue {
    background: transparent;
}
LabeledValue:hover {
    background: transparent;
}
LabeledValue:focus {
    background: transparent;
}
.hidden {
    display: none;
}
"""
