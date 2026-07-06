from __future__ import annotations

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static


@dataclass(frozen=True)
class FormField:
    name: str
    label: str
    placeholder: str = ""
    value: str = ""


class RecordFormScreen(ModalScreen[dict[str, str] | None]):
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
