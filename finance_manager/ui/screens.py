from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ListItem, ListView, Static


if TYPE_CHECKING:
    from finance_manager.services.sheets import GoogleSheetsRepository


@dataclass
class SheetRef:
    spreadsheet_id: str
    title: str


@dataclass
class ClientSecretResult:
    """Result from the setup screen: whether to proceed and the chosen path."""
    proceed: bool
    client_secret_path: str


class SetupScreen(ModalScreen[ClientSecretResult | None]):
    """Shown when the OAuth client secret file is missing.

    Walks the user through downloading a Google Cloud OAuth client secret
    and lets them paste a path to their downloaded `client_secret.json`.
    """

    DEFAULT_CSS = """
    SetupScreen {
        align: center middle;
    }
    #setup-panel {
        width: 84;
        height: auto;
        max-height: 90%;
        padding: 1 2;
        background: #1a1b26;
        border: round #bb9af7;
    }
    #setup-title {
        text-style: bold;
        color: #bb9af7;
        margin-bottom: 1;
    }
    #setup-steps {
        color: #9aa5ce;
        margin-bottom: 1;
    }
    #setup-path-label {
        color: #9aa5ce;
        margin-top: 1;
    }
    #setup-path {
        background: #24283b;
        color: #c0caf5;
        border: solid #414868;
    }
    #setup-path:focus {
        border: solid #7aa2f7;
    }
    #setup-hint {
        color: #565f89;
        margin-top: 0;
    }
    #setup-actions {
        margin-top: 1;
        height: auto;
        align-horizontal: right;
    }
    #setup-continue {
        background: #7aa2f7;
        color: #1a1b26;
    }
    #setup-quit {
        background: #414868;
        color: #c0caf5;
    }
    """

    def __init__(self, default_path: str) -> None:
        super().__init__()
        self.default_path = default_path

    def compose(self) -> ComposeResult:
        with Vertical(id="setup-panel"):
            yield Label("Setup: connect Google OAuth", id="setup-title")
            yield Static(
                "The OAuth client secret file was not found. To set it up:\n"
                "\n"
                "1. Open https://console.cloud.google.com/\n"
                "2. Create or select a project, then enable the Google Sheets API\n"
                "3. APIs & Services > Credentials > Create Credentials > OAuth client ID\n"
                "4. Application type: Desktop app\n"
                "5. Download the JSON and place it somewhere on this machine\n"
                "\n"
                "Enter the path to that file below, then Continue to sign in.",
                id="setup-steps",
            )
            yield Label("Path to client_secret.json", id="setup-path-label")
            yield Input(value=self.default_path, id="setup-path")
            yield Static(
                "Tip: set FINANCE_MANAGER_OAUTH_CLIENT_SECRET to override this path.",
                id="setup-hint",
            )
            with Vertical(id="setup-actions"):
                yield Button("Continue", id="setup-continue", variant="primary")
                yield Button("Quit", id="setup-quit")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "setup-continue":
            path = self.query_one("#setup-path", Input).value.strip()
            self.dismiss(ClientSecretResult(proceed=True, client_secret_path=path))
        elif event.button.id == "setup-quit":
            self.dismiss(None)


class LoginScreen(ModalScreen[bool]):
    """First-run login screen: a single Login button triggers OAuth."""

    DEFAULT_CSS = """
    LoginScreen {
        align: center middle;
    }
    #login-panel {
        width: 60;
        height: auto;
        padding: 2 4;
        background: #1a1b26;
        border: round #7aa2f7;
    }
    #login-title {
        text-style: bold;
        color: #7aa2f7;
        margin-bottom: 1;
    }
    #login-hint {
        color: #9aa5ce;
        margin-bottom: 1;
    }
    #login-btn {
        background: #7aa2f7;
        color: #1a1b26;
        border: round #7dcfff;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="login-panel"):
            yield Label("Finance Manager", id="login-title")
            yield Static(
                "Connect your Google account to start.\n"
                "Click Login to authorize via OAuth.",
                id="login-hint",
            )
            yield Button("Login", id="login-btn", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "login-btn":
            self.dismiss(True)


class SheetSelectScreen(ModalScreen[SheetRef | None]):
    """Show the user's Google Sheets spreadsheets and let them pick one."""

    DEFAULT_CSS = """
    SheetSelectScreen {
        align: center middle;
    }
    #sheet-panel {
        width: 80;
        height: 28;
        padding: 1 2;
        background: #1a1b26;
        border: round #7aa2f7;
    }
    #sheet-title {
        text-style: bold;
        color: #7aa2f7;
        margin-bottom: 1;
    }
    #sheet-list {
        height: 1fr;
        border: solid #414868;
        background: #24283b;
    }
    #sheet-actions {
        height: auto;
        margin-top: 1;
        align-horizontal: right;
    }
    #sheet-cancel {
        background: #414868;
        color: #c0caf5;
    }
    """

    def __init__(self, sheets: list[SheetRef]) -> None:
        super().__init__()
        self.sheets = sheets

    def compose(self) -> ComposeResult:
        with Vertical(id="sheet-panel"):
            yield Label("Select a spreadsheet", id="sheet-title")
            yield ListView(id="sheet-list")
            with Vertical(id="sheet-actions"):
                yield Button("Cancel", id="sheet-cancel")

    def on_mount(self) -> None:
        # Populate the ListView after mount rather than during compose, per
        # Textual conventions that avoid widget mutation inside compose().
        list_view = self.query_one("#sheet-list", ListView)
        for sheet in self.sheets:
            list_view.append(ListItem(Label(f"{sheet.title}\n{sheet.spreadsheet_id}")))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        index = event.list_view.index
        if index is None or index >= len(self.sheets):
            return
        self.dismiss(self.sheets[index])

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "sheet-cancel":
            self.dismiss(None)