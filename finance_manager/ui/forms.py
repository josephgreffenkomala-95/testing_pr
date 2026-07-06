from __future__ import annotations

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static


TOKYONIGHT_FORM_CSS = """
#form-modal {
    background: #24283b;
    color: #c0caf5;
}
.form-title {
    color: #7aa2f7;
}
.form-label {
    color: #9aa5ce;
}
.form-hint {
    color: #565f89;
}
Input {
    background: #1a1b26;
    color: #c0caf5;
    border: solid #414868;
}
Input:focus {
    border: solid #7aa2f7;
}
Input.--placeholder {
    color: #565f89;
}
Button {
    background: #414868;
    color: #c0caf5;
    border: solid #414868;
}
Button#save {
    background: #7aa2f7;
    color: #1a1b26;
}
Button:hover {
    background: #7aa2f7;
    color: #1a1b26;
}
"""


@dataclass(frozen=True)
class FormField:
    name: str
    label: str
    placeholder: str = ""
    value: str = ""


class RecordFormScreen(ModalScreen[dict[str, str] | None]):
    DEFAULT_CSS = TOKYONIGHT_FORM_CSS

    def __init__(self, title: str, fields: list[FormField], hint: str = "") -> None:
        super().__init__()
        self.title = title
        self.fields = fields
        self.hint = hint

    def compose(self) -> ComposeResult:
        with Vertical(id="form-modal"):
            yield Label(self.title, classes="form-title")
            if self.hint:
                yield Static(self.hint, classes="form-hint")
            for field in self.fields:
                yield Label(field.label, classes="form-label")
                yield Input(value=field.value, placeholder=field.placeholder, id=f"field-{field.name}")
            with Horizontal(classes="form-buttons"):
                yield Button("Save", id="save", variant="primary")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        if self.fields:
            self.query_one(f"#field-{self.fields[0].name}", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        values = {
            field.name: self.query_one(f"#field-{field.name}", Input).value
            for field in self.fields
        }
        self.dismiss(values)


CONFIRM_CSS = """
ConfirmScreen {
    align: center middle;
}
#confirm-panel {
    width: 60;
    height: auto;
    padding: 1 2;
    background: #1a1b26;
    border: round #f7768e;
}
#confirm-title {
    text-style: bold;
    color: #f7768e;
    margin-bottom: 1;
}
#confirm-message {
    color: #c0caf5;
    margin-bottom: 1;
}
#confirm-detail {
    color: #9aa5ce;
    margin-bottom: 1;
}
#confirm-actions {
    height: auto;
    align-horizontal: right;
}
#confirm-yes {
    background: #f7768e;
    color: #1a1b26;
}
#confirm-no {
    background: #414868;
    color: #c0caf5;
}
"""


class ConfirmScreen(ModalScreen[bool | None]):
    DEFAULT_CSS = CONFIRM_CSS

    def __init__(self, message: str, detail: str = "") -> None:
        super().__init__()
        self.message = message
        self.detail = detail

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-panel"):
            yield Label("Confirm", id="confirm-title")
            yield Static(self.message, id="confirm-message")
            if self.detail:
                yield Static(self.detail, id="confirm-detail")
            with Horizontal(id="confirm-actions"):
                yield Button("Delete", id="confirm-yes", variant="primary")
                yield Button("Cancel", id="confirm-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-yes":
            self.dismiss(True)
        else:
            self.dismiss(False)
