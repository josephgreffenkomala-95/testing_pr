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
    border: round #7aa2f7;
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
    border: solid #7aa2f7;
}
Button:hover {
    background: #89b4fa;
    color: #1a1b26;
}
Button#cancel {
    color: #c0caf5;
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

    def __init__(self, title: str, fields: list[FormField], hint: str = "", theme_css: str = "") -> None:
        super().__init__()
        self.form_title = title
        self.fields = fields
        self.hint = hint
        if theme_css:
            self.css = theme_css

    def compose(self) -> ComposeResult:
        with Vertical(id="form-modal"):
            yield Label(self.form_title, classes="form-title")
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


LIGHT_FORM_CSS = """
#form-modal {
    background: #ffffff;
    color: #333333;
    border: round #4a90d9;
}
.form-title {
    color: #4a90d9;
}
.form-label {
    color: #666666;
}
.form-hint {
    color: #999999;
}
Input {
    background: #ffffff;
    color: #333333;
    border: solid #cccccc;
}
Input:focus {
    border: solid #4a90d9;
}
Input.--placeholder {
    color: #999999;
}
Button {
    background: #e7edf5;
    color: #333333;
    border: solid #bccddd;
}
Button#save {
    background: #4a90d9;
    color: #ffffff;
    border: solid #4a90d9;
}
Button:hover {
    background: #dbe8f8;
    color: #1f3b5b;
}
Button#save:hover {
    background: #2f73b8;
    color: #ffffff;
}
"""

TOKYONIGHT_CONFIRM_CSS = """
ConfirmScreen {
    align: center middle;
}
#confirm-panel {
    width: 60;
    height: auto;
    padding: 1 2;
    background: #1a1b26;
    border: round #f7768e;
    color: #c0caf5;
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
    color: #a9b1d6;
    margin-bottom: 1;
}
#confirm-actions {
    height: auto;
    align-horizontal: right;
}
#confirm-yes {
    background: #f7768e;
    color: #1a1b26;
    border: solid #f7768e;
}
#confirm-no {
    background: #414868;
    color: #c0caf5;
    border: solid #565f89;
}
#confirm-no:hover {
    background: #565f89;
    color: #ffffff;
}
"""

LIGHT_CONFIRM_CSS = """
ConfirmScreen {
    align: center middle;
}
#confirm-panel {
    width: 60;
    height: auto;
    padding: 1 2;
    background: #ffffff;
    border: round #e74c3c;
    color: #333333;
}
#confirm-title {
    text-style: bold;
    color: #e74c3c;
    margin-bottom: 1;
}
#confirm-message {
    color: #333333;
    margin-bottom: 1;
}
#confirm-detail {
    color: #666666;
    margin-bottom: 1;
}
#confirm-actions {
    height: auto;
    align-horizontal: right;
}
#confirm-yes {
    background: #e74c3c;
    color: #ffffff;
    border: solid #e74c3c;
}
#confirm-no {
    background: #e7edf5;
    color: #333333;
    border: solid #bccddd;
}
#confirm-no:hover {
    background: #dbe8f8;
    color: #1f3b5b;
}
"""


class ConfirmScreen(ModalScreen[bool | None]):
    DEFAULT_CSS = TOKYONIGHT_CONFIRM_CSS

    def __init__(self, message: str, detail: str = "", theme_css: str = "") -> None:
        super().__init__()
        self.message = message
        self.detail = detail
        if theme_css:
            self.css = theme_css

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
