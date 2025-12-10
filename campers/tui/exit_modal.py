"""Exit action modal for TUI."""

import contextlib

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static


class ExitModal(ModalScreen[str]):
    """Modal dialog for exit action selection.

    Presents options for what to do with the running instance:
    - Stop: Pause instance, preserving data (storage costs apply)
    - Keep running: Detach local connections, instance stays running (useful for demos)
    - Destroy: Terminate instance and delete all data
    - Cancel: Dismiss modal and continue session

    Parameters
    ----------
    public_ip : str | None
        Public IP address of the instance
    public_ports : list[int] | None
        List of publicly accessible ports
    hourly_cost : float | None
        Estimated hourly cost of running instance

    Returns
    -------
    str
        One of: "stop", "detach", "destroy", "cancel"
    """

    CSS = """
    ExitModal {
        align: center middle;
        background: $surface 80%;
    }

    #exit-dialog {
        width: 60;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: thick $primary;
    }

    #exit-title {
        text-align: center;
        text-style: bold;
        padding-bottom: 1;
    }

    .option-description {
        color: $text-muted;
        padding-left: 2;
        padding-bottom: 1;
    }

    .public-url {
        color: $success;
        padding-left: 4;
    }

    Button {
        width: 100%;
        margin-bottom: 0;
    }
    """

    BINDINGS = [
        ("s", "select('stop')", "Stop"),
        ("k", "select('detach')", "Keep"),
        ("d", "select('destroy')", "Destroy"),
        ("escape", "select('cancel')", "Cancel"),
    ]

    def __init__(
        self,
        public_ip: str | None = None,
        public_ports: list[int] | None = None,
        hourly_cost: float | None = None,
    ) -> None:
        super().__init__()
        self.public_ip = public_ip
        self.public_ports = public_ports or []
        self.hourly_cost = hourly_cost

    def compose(self) -> ComposeResult:
        """Compose the exit modal layout."""
        with Container(id="exit-dialog"):
            yield Label("What would you like to do?", id="exit-title")

            with Vertical():
                yield Button("[S] Stop instance", id="btn-stop", variant="primary")
                yield Static(
                    "Pause instance, resume later. Storage costs apply.",
                    classes="option-description",
                )

                yield Button("[K] Keep running", id="btn-detach", variant="warning")
                cost_msg = (
                    f"Instance stays running (~${self.hourly_cost:.2f}/hr)"
                    if self.hourly_cost
                    else "Instance stays running"
                )
                yield Static(cost_msg, classes="option-description")

                if self.public_ip and self.public_ports:
                    yield Static("Clients can access:", classes="option-description")
                    for port in self.public_ports:
                        protocol = "https" if port == 443 else "http"
                        yield Static(
                            f"{protocol}://{self.public_ip}:{port}",
                            classes="public-url",
                        )

                yield Button("[D] Destroy", id="btn-destroy", variant="error")
                yield Static(
                    "Terminate instance and delete all data.",
                    classes="option-description",
                )

                yield Button("[Esc] Cancel", id="btn-cancel")
                yield Static("Stay connected.", classes="option-description")

    def on_mount(self) -> None:
        """Handle mount event - set focus to Stop button."""
        with contextlib.suppress(ValueError, AttributeError, RuntimeError):
            self.query_one("#btn-stop").focus()

    def action_select(self, action: str) -> None:
        """Handle keyboard shortcut selection.

        Parameters
        ----------
        action : str
            The action selected via keyboard binding
        """
        self.dismiss(action)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button click selection.

        Parameters
        ----------
        event : Button.Pressed
            Button press event
        """
        button_map = {
            "btn-stop": "stop",
            "btn-detach": "detach",
            "btn-destroy": "destroy",
            "btn-cancel": "cancel",
        }
        action = button_map.get(event.button.id, "cancel")
        self.dismiss(action)
