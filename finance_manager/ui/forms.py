from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static


TOKYONIGHT_FORM_CSS = """
#form-modal { width: 72; height: auto; max-height: 95%; padding: 1 2; background: #24283b; color: #c0caf5; border: round #7aa2f7; }
.form-title { color: #7aa2f7; text-style: bold; }
.form-label { color: #9aa5ce; margin-top: 1; }
.form-hint { color: #7dcfff; }
#form-error { color: #f7768e; height: auto; margin-top: 1; }
.form-buttons { height: auto; margin-top: 1; }
Input, Select { background: #1a1b26; color: #c0caf5; border: solid #414868; }
Input:focus, Select:focus { border: double #7aa2f7; }
Button#save { background: #7aa2f7; color: #1a1b26; }
"""


@dataclass(frozen=True)
class FormField:
    name: str
    label: str
    placeholder: str = ""
    value: str = ""
    options: tuple[str, ...] = ()
    input_type: str = "text"
    required: bool = True


class RecordFormScreen(ModalScreen[dict[str, str] | None]):
    DEFAULT_CSS = TOKYONIGHT_FORM_CSS

    def __init__(self, title: str, fields: list[FormField], hint: str = "") -> None:
        super().__init__()
        self.form_title = title
        self.fields = fields
        self.hint = hint

    def compose(self) -> ComposeResult:
        with Vertical(id="form-modal"):
            yield Label(self.form_title, classes="form-title")
            if self.hint:
                yield Static(self.hint, classes="form-hint")
            for field in self.fields:
                yield Label(field.label, classes="form-label")
                if field.options:
                    yield Select.from_values(
                        list(field.options),
                        value=field.value or field.options[0],
                        id=f"field-{field.name}",
                    )
                else:
                    input_kind: Literal["number", "text"] = "number" if field.input_type == "amount" else "text"
                    yield Input(
                        value=field.value,
                        placeholder=field.placeholder,
                        type=input_kind,
                        id=f"field-{field.name}",
                    )
            yield Static("", id="form-error")
            with Horizontal(classes="form-buttons"):
                yield Button("Save", id="save", variant="primary")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        if self.fields:
            self.query_one(f"#field-{self.fields[0].name}").focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        values = self._values()
        error = self._validate(values)
        if error:
            self.query_one("#form-error", Static).update(error)
            return
        self.dismiss(values)

    def _values(self) -> dict[str, str]:
        values = {}
        for field in self.fields:
            control = self.query_one(f"#field-{field.name}")
            if isinstance(control, Select):
                values[field.name] = "" if control.value is Select.BLANK else str(control.value)
            elif isinstance(control, Input):
                values[field.name] = control.value
        return values

    def _validate(self, values: dict[str, str]) -> str:
        for field in self.fields:
            value = values[field.name].strip()
            if field.required and not value:
                return f"{field.label} is required."
            if not value:
                continue
            if field.input_type == "amount":
                try:
                    if Decimal(value) < 0:
                        return f"{field.label} cannot be negative."
                except InvalidOperation:
                    return f"{field.label} must be a valid amount."
            elif field.input_type == "date":
                try:
                    date.fromisoformat(value)
                except ValueError:
                    return f"{field.label} must use YYYY-MM-DD."
            elif field.input_type == "month":
                try:
                    datetime.strptime(value, "%Y-%m")
                except ValueError:
                    return f"{field.label} must use YYYY-MM."
        return ""
