from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, ListItem, ListView, Static


if TYPE_CHECKING:
    from finance_manager.services.sheets import GoogleSheetsRepository


@dataclass
class SheetRef:
    spreadsheet_id: str
    title: str


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
            list_view = ListView(id="sheet-list")
            yield list_view
            with Vertical(id="sheet-actions"):
                yield Button("Cancel", id="sheet-cancel")
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