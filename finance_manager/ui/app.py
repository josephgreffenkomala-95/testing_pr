from __future__ import annotations

import webbrowser
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path
from typing import cast

from rich.panel import Panel
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Input, Static

from finance_manager.config.auth import run_oauth_flow
from finance_manager.config.settings import persist_app_state
from finance_manager.logic.calculations import BudgetUsage, ProjectionPoint, current_month, month_budget_report, projection, total_balance
from finance_manager.models.entities import Account, Budget, PlannedTransaction, Snapshot, Transaction
from finance_manager.services.sheets import (
    ExternalServiceError,
    FinanceManagerError,
    GoogleSheetsRepository,
    InvalidSheetStructureError,
    MissingCredentialsError,
)
from finance_manager.ui.forms import (
    ConfirmScreen,
    FormField,
    LIGHT_CONFIRM_CSS,
    LIGHT_FORM_CSS,
    RecordFormScreen,
    TOKYONIGHT_CONFIRM_CSS,
    TOKYONIGHT_FORM_CSS,
)
from finance_manager.ui.screens import (
    ClientSecretResult,
    LIGHT_LOGIN_CSS,
    LIGHT_SETUP_CSS,
    LIGHT_SHEET_CSS,
    LoginScreen,
    SheetRef,
    SheetSelectScreen,
    SetupScreen,
    TOKYONIGHT_LOGIN_CSS,
    TOKYONIGHT_SETUP_CSS,
    TOKYONIGHT_SHEET_CSS,
)


def _format_amount(value: Decimal | float, currency: str = "IDR") -> str:
    if isinstance(value, Decimal):
        formatted = f"{value:,.2f}"
    else:
        formatted = f"{value:,.2f}"
    return f"{currency} {formatted}"


TOKYONIGHT_CSS = """
Screen {
    background: #1a1b26;
    color: #c0caf5;
}
Header {
    background: #7aa2f7;
    color: #1a1b26;
}
Footer {
    background: #24283b;
    color: #9aa5ce;
}
#sidebar {
    width: 30;
    padding: 1 2;
    background: #24283b;
    color: #a9b1d6;
    border-right: solid #414868;
}
#main {
    padding: 1;
}
#tabs {
    height: 3;
    content-align: left middle;
    color: #7aa2f7;
    text-style: bold;
}
#filter-bar {
    height: 3;
    margin: 0 0 1 0;
}
#filter-input {
    width: 1fr;
    background: #24283b;
    color: #c0caf5;
    border: solid #414868;
}
#filter-input:focus {
    border: solid #7aa2f7;
}
#filter-input.--placeholder {
    color: #565f89;
}
#body {
    height: 1fr;
}
#record-list {
    width: 1fr;
    min-width: 48;
    border: solid #414868;
    background: #24283b;
}
DataTable {
    background: #24283b;
    color: #c0caf5;
    scrollbar-background: #1a1b26;
    scrollbar-color: #414868;
    & > .datatable--header {
        background: #1a1b26;
        color: #7aa2f7;
        text-style: bold;
    }
    & > .datatable--cursor {
        background: #2ac3de;
        color: #1a1b26;
    }
    & > .datatable--hover {
        background: #414868;
    }
    & > .datatable--even {
        background: #24283b;
    }
    & > .datatable--odd {
        background: #1e2030;
    }
}
#detail {
    width: 40;
    padding: 1;
    border: solid #414868;
    background: #24283b;
    color: #c0caf5;
}
#status {
    height: 3;
    padding: 0 1;
    color: #a9b1d6;
}
#form-modal {
    width: 72;
    height: auto;
    padding: 1 2;
    background: #24283b;
    border: round #7aa2f7;
}
.form-title {
    text-style: bold;
    color: #7aa2f7;
    margin-bottom: 1;
}
.form-label {
    margin-top: 1;
    color: #9aa5ce;
}
.form-hint {
    color: #565f89;
}
.form-buttons {
    margin-top: 1;
    height: auto;
}
ListView > ListItem {
    background: #24283b;
    color: #c0caf5;
}
ListView > ListItem.--highlight {
    background: #2ac3de;
    color: #1a1b26;
}
"""

LIGHT_CSS = """
Screen {
    background: #ffffff;
    color: #333333;
}
Header {
    background: #4a90d9;
    color: #ffffff;
}
Footer {
    background: #f0f0f0;
    color: #333333;
}
#sidebar {
    width: 30;
    padding: 1 2;
    background: #f0f0f0;
    color: #333333;
    border-right: solid #cccccc;
}
#main {
    padding: 1;
}
#tabs {
    height: 3;
    content-align: left middle;
    color: #4a90d9;
    text-style: bold;
}
#filter-bar {
    height: 3;
    margin: 0 0 1 0;
}
#filter-input {
    width: 1fr;
    background: #ffffff;
    color: #333333;
    border: solid #cccccc;
}
#filter-input:focus {
    border: solid #4a90d9;
}
#filter-input.--placeholder {
    color: #999999;
}
#body {
    height: 1fr;
}
#record-list {
    width: 1fr;
    min-width: 48;
    border: solid #cccccc;
    background: #ffffff;
}
DataTable {
    background: #ffffff;
    color: #333333;
    scrollbar-background: #ffffff;
    scrollbar-color: #cccccc;
    & > .datatable--header {
        background: #f0f0f0;
        color: #4a90d9;
        text-style: bold;
    }
    & > .datatable--cursor {
        background: #4a90d9;
        color: #ffffff;
    }
    & > .datatable--hover {
        background: #e8f0fe;
    }
    & > .datatable--even {
        background: #ffffff;
    }
    & > .datatable--odd {
        background: #f5f5f5;
    }
}
#detail {
    width: 40;
    padding: 1;
    border: solid #cccccc;
    background: #fafafa;
    color: #333333;
}
#status {
    height: 3;
    padding: 0 1;
    color: #333333;
}
#form-modal {
    width: 72;
    height: auto;
    padding: 1 2;
    background: #ffffff;
    border: round #4a90d9;
}
.form-title {
    text-style: bold;
    color: #4a90d9;
    margin-bottom: 1;
}
.form-label {
    margin-top: 1;
    color: #666666;
}
.form-hint {
    color: #999999;
}
.form-buttons {
    margin-top: 1;
    height: auto;
}
ListView > ListItem {
    background: #ffffff;
    color: #333333;
}
ListView > ListItem.--highlight {
    background: #4a90d9;
    color: #ffffff;
}
"""

THEMES: dict[str, str] = {
    "tokyonight": TOKYONIGHT_CSS,
    "light": LIGHT_CSS,
}

THEME_PALETTES: dict[str, dict[str, object]] = {
    "tokyonight": {
        "accent": "#7aa2f7",
        "positive": "#9ece6a",
        "negative": "#f7768e",
        "status": {"planned": "#e0af68", "confirmed": "#7aa2f7", "completed": "#9ece6a", "cancelled": "#f7768e"},
    },
    "light": {
        "accent": "#4a90d9",
        "positive": "#2e7d32",
        "negative": "#c62828",
        "status": {"planned": "#b26a00", "confirmed": "#2f73b8", "completed": "#2e7d32", "cancelled": "#c62828"},
    },
}

SCREEN_THEME_CSS: dict[str, dict[str, str]] = {
    "tokyonight": {
        "form": TOKYONIGHT_FORM_CSS,
        "confirm": TOKYONIGHT_CONFIRM_CSS,
        "setup": TOKYONIGHT_SETUP_CSS,
        "login": TOKYONIGHT_LOGIN_CSS,
        "sheet": TOKYONIGHT_SHEET_CSS,
    },
    "light": {
        "form": LIGHT_FORM_CSS,
        "confirm": LIGHT_CONFIRM_CSS,
        "setup": LIGHT_SETUP_CSS,
        "login": LIGHT_LOGIN_CSS,
        "sheet": LIGHT_SHEET_CSS,
    },
}


@dataclass
class RowRef:
    record_id: str
    title: str
    subtitle: str


class FinanceManagerApp(App[None]):
    CSS = TOKYONIGHT_CSS

    BINDINGS = [
        Binding("1", "switch_view('transactions')", "Transactions"),
        Binding("2", "switch_view('planned')", "Planned"),
        Binding("3", "switch_view('budgets')", "Budgets"),
        Binding("4", "switch_view('projection')", "Projection"),
        Binding("5", "switch_view('accounts')", "Accounts"),
        Binding("6", "switch_view('setup')", "Setup"),
        Binding("a", "add_record", "Add"),
        Binding("e", "edit_record", "Edit"),
        Binding("d", "delete_record", "Delete"),
        Binding("f", "focus_filter", "Filter"),
        Binding("r", "reload_data", "Reload"),
        Binding("s", "seed_dummy", "Seed Data"),
        Binding("l", "login", "Login"),
        Binding("o", "open_sheet", "Open Sheet"),
        Binding("t", "toggle_theme", "Theme"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, repository: GoogleSheetsRepository | None = None) -> None:
        super().__init__()
        self.repository = repository or GoogleSheetsRepository()
        self.snapshot = Snapshot([], [], [], [], [], {})
        self.current_view = "transactions"
        self.current_rows: list[RowRef] = []
        self.row_keys: list[str] = []
        self.error_message = ""
        self.authenticated = False
        self.filter_text = ""
        self._current_theme = self.repository.config.theme
        self.CSS = THEMES.get(self._current_theme, TOKYONIGHT_CSS)  # type: ignore[assignment,misc]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="body-wrap"):
            yield Static(id="sidebar")
            with Vertical(id="main"):
                yield Static(id="tabs")
                with Horizontal(id="filter-bar"):
                    yield Input(placeholder="Filter records...", id="filter-input")
                with Horizontal(id="body"):
                    yield DataTable(id="record-list")
                    yield Static(id="detail")
                yield Static(id="status")
        yield Footer()

    def on_mount(self) -> None:
        if not self._has_client_secret():
            self.push_screen(SetupScreen(str(self.repository.config.oauth_client_secret_path), theme_css=self._theme_css("setup")), self._on_setup_result)
        elif not self._has_token():
            self.push_screen(LoginScreen(theme_css=self._theme_css("login")), self._on_login_result)
        else:
            self._try_authenticate()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "filter-input":
            self.filter_text = event.value.lower()
            self._refresh_ui("Filtered.")

    def action_focus_filter(self) -> None:
        self.query_one("#filter-input", Input).focus()

    def action_toggle_theme(self) -> None:
        self._current_theme = "light" if self._current_theme == "tokyonight" else "tokyonight"
        self.CSS = THEMES[self._current_theme]  # type: ignore[assignment,misc]
        for screen in self.screen_stack:
            self._apply_theme_to_screen(screen)
        self.refresh_css()
        persist_app_state(self.repository.config, theme=self._current_theme)
        self._refresh_ui(f"Theme: {self._current_theme}.")

    def _apply_theme_to_screen(self, screen) -> None:
        if isinstance(screen, RecordFormScreen):
            category = "form"
        elif isinstance(screen, ConfirmScreen):
            category = "confirm"
        elif isinstance(screen, SetupScreen):
            category = "setup"
        elif isinstance(screen, LoginScreen):
            category = "login"
        elif isinstance(screen, SheetSelectScreen):
            category = "sheet"
        else:
            return
        screen.css = self._theme_css(category)  # type: ignore[assignment]

    def _theme_css(self, category: str) -> str:
        return SCREEN_THEME_CSS[self._current_theme].get(category, "")

    def _theme_palette(self) -> dict[str, object]:
        return THEME_PALETTES[self._current_theme]

    def _accent_color(self) -> str:
        return str(self._theme_palette()["accent"])

    def _status_colors(self) -> dict[str, str]:
        return cast(dict[str, str], self._theme_palette()["status"])

    def _colorize(self, text: str, role: str) -> str:
        return f"[{self._theme_palette()[role]}]{text}[/]"

    def _has_client_secret(self) -> bool:
        return self.repository.config.oauth_client_secret_path.exists()

    def _has_token(self) -> bool:
        return self.repository.config.oauth_token_path.exists()

    def _try_authenticate(self) -> None:
        try:
            if self.repository.config.spreadsheet_id:
                self.query_one("#status", Static).update("Connecting...")
                self.repository.bootstrap()
                self.authenticated = True
                self._load_data(initial=True)
            else:
                self._enter_main_app()
        except MissingCredentialsError:
            self.push_screen(LoginScreen(theme_css=self._theme_css("login")), self._on_login_result)
        except (InvalidSheetStructureError, ExternalServiceError) as exc:
            self.error_message = str(exc)
            self._refresh_ui(self.error_message)

    def _on_setup_result(self, result: ClientSecretResult | None) -> None:
        if result is None or not result.proceed:
            self.app.exit("Setup cancelled.")
            return
        secret_path = Path(result.client_secret_path).expanduser()
        self.repository.config = replace(
            self.repository.config,
            oauth_client_secret_path=secret_path,
        )
        persist_app_state(self.repository.config, oauth_client_secret_path=str(secret_path))
        if not secret_path.exists():
            self.error_message = f"Client secret file not found: {secret_path}"
            self._refresh_ui(self.error_message)
            self.push_screen(SetupScreen(str(secret_path), theme_css=self._theme_css("setup")), self._on_setup_result)
            return
        self.push_screen(LoginScreen(theme_css=self._theme_css("login")), self._on_login_result)

    def _on_login_result(self, proceed: bool | None) -> None:
        if not proceed:
            self.app.exit("Login cancelled.")
            return
        try:
            run_oauth_flow(self.repository.config)
        except FinanceManagerError as exc:
            self.error_message = f"OAuth failed: {exc}"
            self._refresh_ui(self.error_message)
            return
        self._enter_main_app()

    def _enter_main_app(self) -> None:
        """Called after OAuth completes (or on mount when already authed).

        Lists the user's spreadsheets and asks them to pick one; if there are
        none, bootstraps a fresh sheet. Ensures the Login/Setup screen is
        dismissed and the main view is refreshed.
        """
        try:
            sheets = self.repository.list_spreadsheets()
        except FinanceManagerError as exc:
            self.error_message = f"Could not list spreadsheets: {exc}"
            self._refresh_ui(self.error_message)
            return
        if not sheets:
            try:
                self.repository.bootstrap()
            except FinanceManagerError as exc:
                self.error_message = f"Could not create spreadsheet: {exc}"
                self._refresh_ui(self.error_message)
                return
            self.authenticated = True
            self._load_data(initial=True)
            return
        self.push_screen(SheetSelectScreen(sheets, theme_css=self._theme_css("sheet")), self._on_sheet_selected)

    def _on_sheet_selected(self, sheet: SheetRef | None) -> None:
        if sheet is None:
            self.app.exit("No spreadsheet selected.")
            return
        try:
            self.repository.use_spreadsheet(sheet.spreadsheet_id, sheet.title)
        except FinanceManagerError as exc:
            self.error_message = f"Could not open spreadsheet: {exc}"
            self._refresh_ui(self.error_message)
            return
        self.authenticated = True
        self._load_data(initial=True)

    def _load_data(self, *, initial: bool = False) -> None:
        try:
            self.query_one("#status", Static).update("Connecting...")
            self.repository.bootstrap()
            self.snapshot = self.repository.load_snapshot()
            self.error_message = ""
        except (MissingCredentialsError, InvalidSheetStructureError, ExternalServiceError) as exc:
            self.error_message = str(exc)
            self.current_view = "setup"
        self._refresh_ui("Ready." if initial and not self.error_message else self.error_message or "Reloaded data.")

    def _refresh_ui(self, status_message: str = "") -> None:
        self.query_one("#tabs", Static).update(self._render_tabs())
        self.query_one("#sidebar", Static).update(self._render_sidebar())
        all_rows = self._rows_for_current_view()
        if self.filter_text:
            self.current_rows = [r for r in all_rows if self.filter_text in r.subtitle.lower() or self.filter_text in r.title.lower()]
        else:
            self.current_rows = all_rows
        table = self.query_one("#record-list", DataTable)
        table.clear(columns=True)
        columns = self._table_columns()
        for column in columns:
            table.add_column(column)
        self.row_keys = []
        for row in self.current_rows:
            cells = row.subtitle.split(" | ")
            key = row.record_id
            table.add_row(*cells, key=key)
            self.row_keys.append(key)
        if self.row_keys and table.row_count > 0:
            table.move_cursor(row=0)
        self._update_detail()
        self.query_one("#status", Static).update(status_message)

    def _table_columns(self) -> list[str]:
        if self.current_view == "transactions":
            return ["Date", "Type", "Amount", "Category", "Account", "Description"]
        if self.current_view == "planned":
            return ["Expected date", "Status", "Type", "Amount", "Category", "Description"]
        if self.current_view == "budgets":
            return ["Category", "Type", "Budgeted", "Actual", "Planned", "Remaining"]
        if self.current_view == "projection":
            return ["Label", "Balance", "Change"]
        if self.current_view == "accounts":
            return ["ID", "Name", "Type", "Currency", "Balance", "Active"]
        return ["Title", "Subtitle"]

    def _render_tabs(self) -> str:
        items = [
            ("transactions", "1 Transactions"),
            ("planned", "2 Planned"),
            ("budgets", "3 Budgets"),
            ("projection", "4 Projection"),
            ("accounts", "5 Accounts"),
            ("setup", "6 Setup"),
        ]
        return "   ".join(
            f"[{label}]" if key == self.current_view else label
            for key, label in items
        )

    def _render_sidebar(self):
        balance = total_balance(self.snapshot.accounts)
        month = current_month()
        budget_rows = month_budget_report(self.snapshot, month)
        overspent = sum(1 for row in budget_rows if row.is_projected_overspent)
        url = self.repository.spreadsheet_url()
        lines = [
            "Finance",
            "",
            f"Sheet: {self.repository.config.spreadsheet_title}",
        ]
        if url:
            lines.append(f"URL: {url}")
        lines.extend([
            f"Accounts: {len(self.snapshot.accounts)}",
            f"Categories: {len(self.snapshot.categories)}",
            f"Balance: {_format_amount(balance)}",
            "",
            f"Month: {month}",
            f"Budgets: {len(budget_rows)}",
            f"Warnings: {overspent}",
            "",
            "Shortcuts",
            "1-5 switch views",
            "a add",
            "e edit",
            "d delete",
            "f filter",
            "r reload",
            "o open sheet",
            f"t theme ({self._current_theme})",
            "q quit",
        ])
        if self.error_message:
            lines.extend(["", "Status", self.error_message[:120]])
        return "\n".join(lines)

    def _fmt_amount_colored(self, amount: Decimal | float, currency: str = "IDR") -> str:
        formatted = _format_amount(amount, currency)
        if amount > 0:
            return self._colorize(formatted, "positive")
        if amount < 0:
            return self._colorize(formatted, "negative")
        return formatted

    def _fmt_type_colored(self, entry_type: str) -> str:
        return self._colorize(entry_type.upper(), "positive" if entry_type == "income" else "negative")

    def _fmt_transaction(self, item: Transaction, categories: dict[str, str], accounts: dict[str, str]) -> str:
        amount = _format_amount(item.amount)
        colored_amount = self._colorize(amount, "positive" if item.entry_type == "income" else "negative")
        return f"{item.date} | {self._fmt_type_colored(item.entry_type)} | {colored_amount} | {categories.get(item.category_id, item.category_id)} | {accounts.get(item.account_id, item.account_id)} | {item.description}"

    def _fmt_planned(self, item: PlannedTransaction, categories: dict[str, str], accounts: dict[str, str], status_colors: dict[str, str]) -> str:
        amount = _format_amount(item.amount)
        colored_amount = self._colorize(amount, "positive" if item.entry_type == "income" else "negative")
        sc = status_colors.get(item.status)
        colored_status = f"[{sc}]{item.status.upper()}[/]" if sc else item.status.upper()
        return f"{item.expected_date or 'No date'} | {colored_status} | {self._fmt_type_colored(item.entry_type)} | {colored_amount} | {categories.get(item.category_id, item.category_id)} | {item.description}"

    def _fmt_budget_row(self, row: BudgetUsage) -> str:
        budgeted = self._fmt_amount_colored(row.budgeted)
        actual = self._fmt_amount_colored(row.actual)
        planned = self._fmt_amount_colored(row.planned)
        remaining = self._fmt_amount_colored(row.projected_remaining)
        return f"{row.category_name} | {row.entry_type} | {budgeted} | {actual} | {planned} | {remaining}"

    def _fmt_projection(self, point: ProjectionPoint) -> str:
        balance = self._fmt_amount_colored(point.balance)
        if point.change >= 0:
            change = self._colorize(_format_amount(point.change), "positive")
        else:
            change = self._colorize(_format_amount(point.change), "negative")
        return f"{point.label} | {balance} | {change}"

    def _fmt_account(self, account: Account) -> str:
        balance = self._fmt_amount_colored(account.current_balance, account.currency)
        return f"{account.id} | {account.name} | {account.account_type} | {account.currency} | {balance} | {'yes' if account.is_active else 'no'}"

    def _rows_for_current_view(self) -> list[RowRef]:
        categories = {category.id: category.name for category in self.snapshot.categories}
        accounts = {account.id: account.name for account in self.snapshot.accounts}
        status_colors = self._status_colors()
        if self.current_view == "transactions":
            items = sorted(self.snapshot.transactions, key=lambda item: item.date, reverse=True)
            return [
                RowRef(
                    record_id=item.id,
                    title=f"{item.date} {item.entry_type.upper()} {_format_amount(item.amount)}",
                    subtitle=self._fmt_transaction(item, categories, accounts),
                )
                for item in items
            ]
        if self.current_view == "planned":
            planned_items = sorted(self.snapshot.planned_transactions, key=lambda item: item.expected_date or "9999-99-99")
            return [
                RowRef(
                    record_id=item.id,
                    title=f"{item.expected_date or 'No date'} {item.status.upper()} {_format_amount(item.amount)}",
                    subtitle=self._fmt_planned(item, categories, accounts, status_colors),
                )
                for item in planned_items
            ]
        if self.current_view == "budgets":
            report = month_budget_report(self.snapshot, current_month())
            return [
                RowRef(
                    record_id=self._budget_id_for(row.category_name, row.entry_type) or row.category_name,
                    title=f"{row.category_name} budget {_format_amount(row.budgeted)}",
                    subtitle=self._fmt_budget_row(row),
                )
                for row in report
            ]
        if self.current_view == "projection":
            daily, _ = projection(self.snapshot)
            return [
                RowRef(
                    record_id=str(index),
                    title=f"{point.label} balance {_format_amount(point.balance)}",
                    subtitle=self._fmt_projection(point),
                )
                for index, point in enumerate(daily)
            ]
        if self.current_view == "accounts":
            return [
                RowRef(
                    record_id=account.id,
                    title=f"{account.name} {_format_amount(account.current_balance, account.currency)}",
                    subtitle=self._fmt_account(account),
                )
                for account in self.snapshot.accounts
            ]
        setup_lines = self._setup_rows()
        return [RowRef(str(index), title, subtitle) for index, (title, subtitle) in enumerate(setup_lines)]

    def _setup_rows(self) -> list[tuple[str, str]]:
        url = self.repository.spreadsheet_url()
        if self.error_message:
            return [
                ("Credentials or connectivity issue", self.error_message),
                (
                    "Expected OAuth client file",
                    str(self.repository.config.oauth_client_secret_path),
                ),
                (
                    "Auth help",
                    "Use the Login button to run the Google OAuth flow, then pick a spreadsheet.",
                ),
            ]
        rows = [
            ("Spreadsheet ID", self.repository.config.spreadsheet_id or "Stored after first successful bootstrap"),
            ("Spreadsheet URL", url or "(available once a sheet is opened)"),
            ("Open in browser", "Press o to open the sheet URL"),
            ("OAuth client file", str(self.repository.config.oauth_client_secret_path)),
            ("OAuth token file", str(self.repository.config.oauth_token_path)),
            ("Current title", self.repository.config.spreadsheet_title),
        ]
        return rows

    def _selected_row(self) -> RowRef | None:
        table = self.query_one("#record-list", DataTable)
        if table.cursor_row is None or table.cursor_row >= len(self.current_rows):
            return self.current_rows[0] if self.current_rows else None
        return self.current_rows[table.cursor_row]

    def _detail_labels(self) -> list[str]:
        if self.current_view == "transactions":
            return ["Date", "Type", "Amount", "Category", "Account", "Description"]
        if self.current_view == "planned":
            return ["Expected date", "Status", "Type", "Amount", "Category", "Description"]
        if self.current_view == "budgets":
            return ["Category", "Type", "Budgeted", "Actual", "Planned", "Remaining"]
        if self.current_view == "projection":
            return ["Label", "Balance", "Change"]
        if self.current_view == "accounts":
            return ["ID", "Name", "Type", "Currency", "Balance", "Active"]
        return ["Title", "Subtitle"]

    def _update_detail(self) -> None:
        row = self._selected_row()
        detail = self.query_one("#detail", Static)
        if row is None:
            detail.update(Panel("No records yet.\nPress `a` to add one.", title="Details"))
            return
        labels = self._detail_labels()
        parts = row.subtitle.split(" | ")
        lines = [f"[bold]{row.title}[/bold]", ""]
        for label, part in zip(labels, parts):
            lines.append(f"  [bold]{label}:[/] {part}")
        detail.update(Panel("\n".join(lines), title="Details", border_style=self._accent_color()))

    def on_data_table_row_highlighted(self, _event: DataTable.RowHighlighted) -> None:
        self._update_detail()

    def action_switch_view(self, view: str) -> None:
        self.current_view = view
        self._refresh_ui(f"Viewing {view}.")

    def action_reload_data(self) -> None:
        self.repository.clear_cache()
        self._load_data()

    def action_login(self) -> None:
        self.push_screen(LoginScreen(theme_css=self._theme_css("login")), self._on_login_result)

    def action_open_sheet(self) -> None:
        url = self.repository.spreadsheet_url()
        if not url:
            self.query_one("#status", Static).update("No spreadsheet is open yet.")
            return
        if webbrowser.open(url, new=2):
            self.query_one("#status", Static).update("Opened spreadsheet in browser.")
        else:
            self.query_one("#status", Static).update("Could not open browser.")

    def action_add_record(self) -> None:
        if self.current_view == "transactions":
            self._open_transaction_form()
        elif self.current_view == "planned":
            self._open_planned_form()
        elif self.current_view == "budgets":
            self._open_budget_form()
        elif self.current_view == "accounts":
            self._open_account_form()
        else:
            self.query_one("#status", Static).update("Add is available in Transactions, Planned, Budgets, and Accounts.")

    def action_edit_record(self) -> None:
        row = self._selected_row()
        if row is None:
            self.query_one("#status", Static).update("Nothing selected.")
            return
        if self.current_view == "transactions":
            record = self.repository.get_transaction(row.record_id)
            self._open_transaction_form(record=record)
        elif self.current_view == "planned":
            planned = self.repository.get_planned_transaction(row.record_id)
            self._open_planned_form(record=planned)
        elif self.current_view == "budgets":
            budget = next((item for item in self.snapshot.budgets if item.id == row.record_id), None)
            if budget:
                self._open_budget_form(record=budget)
        elif self.current_view == "accounts":
            account = next((item for item in self.snapshot.accounts if item.id == row.record_id), None)
            if account:
                self._open_account_form(record=account)
        else:
            self.query_one("#status", Static).update("Edit is not available in this view.")

    def action_delete_record(self) -> None:
        row = self._selected_row()
        if row is None:
            self.query_one("#status", Static).update("Nothing selected.")
            return
        self.push_screen(
            ConfirmScreen(f"Delete this {self.current_view[:-1]} record?", row.title, theme_css=self._theme_css("confirm")),
            lambda confirmed: self._confirm_delete(confirmed),
        )

    def _confirm_delete(self, confirmed: bool | None) -> None:
        if not confirmed:
            self.query_one("#status", Static).update("Delete cancelled.")
            return
        row = self._selected_row()
        if row is None:
            return
        try:
            if self.current_view == "transactions":
                self.repository.delete_transaction(row.record_id)
            elif self.current_view == "planned":
                self.repository.delete_planned_transaction(row.record_id)
            elif self.current_view == "budgets":
                budget = next((item for item in self.snapshot.budgets if item.id == row.record_id), None)
                if budget:
                    self.repository.delete_budget(budget.id)
            elif self.current_view == "accounts":
                account = next((item for item in self.snapshot.accounts if item.id == row.record_id), None)
                if account:
                    self.repository.delete_account(account.id)
            else:
                self.query_one("#status", Static).update("Delete is not available in this view.")
                return
            self.snapshot = self.repository.load_snapshot()
            self._refresh_ui("Deleted record.")
        except (FinanceManagerError, KeyError) as exc:
            self.query_one("#status", Static).update(str(exc))

    def action_seed_dummy(self) -> None:
        try:
            created = self.repository.seed_dummy_data()
            self.snapshot = self.repository.load_snapshot()
            self._refresh_ui(f"Seeded {created} sample rows.")
        except FinanceManagerError as exc:
            self.query_one("#status", Static).update(str(exc))

    def _open_transaction_form(self, record: Transaction | None = None) -> None:
        category_name = self._category_name(record.category_id) if record else ""
        account_name = self._account_name(record.account_id) if record else ""
        fields = [
            FormField("entry_type", "Type", "income or expense", record.entry_type if record else "expense"),
            FormField("date", "Date", "YYYY-MM-DD", record.date if record else ""),
            FormField("amount", "Amount", "125000.00", f"{record.amount:.2f}" if record else ""),
            FormField("category", "Category", "Groceries", category_name),
            FormField("description", "Description", "Short description", record.description if record else ""),
            FormField("account", "Account", "Cash", account_name),
            FormField("notes", "Notes", "Optional", record.notes if record else ""),
        ]
        self.push_screen(
            RecordFormScreen("Transaction", fields, hint="Unknown categories/accounts are created automatically.", theme_css=self._theme_css("form")),
            lambda data: self._save_transaction_form(data, record.id if record else None),
        )

    def _open_planned_form(self, record: PlannedTransaction | None = None) -> None:
        category_name = self._category_name(record.category_id) if record else ""
        account_name = self._account_name(record.account_id) if record else ""
        fields = [
            FormField("entry_type", "Type", "income or expense", record.entry_type if record else "expense"),
            FormField("status", "Status", "planned / confirmed / completed / cancelled", record.status if record else "planned"),
            FormField("expected_date", "Expected date", "YYYY-MM-DD or blank", record.expected_date or "" if record else ""),
            FormField("amount", "Amount", "125000.00", f"{record.amount:.2f}" if record else ""),
            FormField("category", "Category", "Groceries", category_name),
            FormField("description", "Description", "Expected cash movement", record.description if record else ""),
            FormField("account", "Account", "Cash", account_name),
            FormField("notes", "Notes", "Optional", record.notes if record else ""),
        ]
        self.push_screen(
            RecordFormScreen("Planned transaction", fields, hint="Leave expected date blank for unscheduled plans.", theme_css=self._theme_css("form")),
            lambda data: self._save_planned_form(data, record.id if record else None),
        )

    def _open_budget_form(self, record: Budget | None = None) -> None:
        category_name = self._category_name(record.category_id) if record else ""
        fields = [
            FormField("month", "Month", "YYYY-MM", record.month if record else current_month()),
            FormField("entry_type", "Type", "income or expense", record.entry_type if record else "expense"),
            FormField("category", "Category", "Groceries", category_name),
            FormField("amount", "Budget amount", "2500000.00", f"{record.amount:.2f}" if record else ""),
            FormField("notes", "Notes", "Optional", record.notes if record else ""),
        ]
        self.push_screen(
            RecordFormScreen("Monthly budget", fields, theme_css=self._theme_css("form")),
            lambda data: self._save_budget_form(data, record.id if record else None),
        )

    def _open_account_form(self, record: Account | None = None) -> None:
        fields = [
            FormField("name", "Account name", "Bank BCA", record.name if record else ""),
            FormField("account_type", "Type", "cash / bank / ewallet", record.account_type if record else "cash"),
            FormField("currency", "Currency", "IDR", record.currency if record else "IDR"),
            FormField("current_balance", "Current balance", "1000000.00", f"{record.current_balance:.2f}" if record else "0.00"),
        ]
        self.push_screen(
            RecordFormScreen("Bank account", fields, hint="Add multiple accounts to track them separately.", theme_css=self._theme_css("form")),
            lambda data: self._save_account_form(data, record.id if record else None),
        )

    def _save_account_form(self, data: dict[str, str] | None, record_id: str | None) -> None:
        if data is None:
            self.query_one("#status", Static).update("Cancelled.")
            return
        try:
            if record_id:
                self.repository.update_account(record_id, data)
            else:
                self.repository.add_account(data)
            self.snapshot = self.repository.load_snapshot()
            self._refresh_ui("Saved account.")
        except (FinanceManagerError, ValueError, KeyError) as exc:
            self.query_one("#status", Static).update(str(exc))

    def _save_transaction_form(self, data: dict[str, str] | None, record_id: str | None) -> None:
        if data is None:
            self.query_one("#status", Static).update("Cancelled.")
            return
        try:
            if record_id:
                self.repository.update_transaction(record_id, data)
            else:
                self.repository.add_transaction(data)
            self.snapshot = self.repository.load_snapshot()
            self._refresh_ui("Saved transaction.")
        except (FinanceManagerError, ValueError, KeyError) as exc:
            self.query_one("#status", Static).update(str(exc))

    def _save_planned_form(self, data: dict[str, str] | None, record_id: str | None) -> None:
        if data is None:
            self.query_one("#status", Static).update("Cancelled.")
            return
        try:
            if record_id:
                self.repository.update_planned_transaction(record_id, data)
            else:
                self.repository.add_planned_transaction(data)
            self.snapshot = self.repository.load_snapshot()
            self._refresh_ui("Saved planned transaction.")
        except (FinanceManagerError, ValueError, KeyError) as exc:
            self.query_one("#status", Static).update(str(exc))

    def _save_budget_form(self, data: dict[str, str] | None, record_id: str | None) -> None:
        if data is None:
            self.query_one("#status", Static).update("Cancelled.")
            return
        try:
            if record_id:
                self.repository.update_budget(record_id, data)
            else:
                self.repository.add_budget(data)
            self.snapshot = self.repository.load_snapshot()
            self._refresh_ui("Saved budget.")
        except (FinanceManagerError, ValueError, KeyError) as exc:
            self.query_one("#status", Static).update(str(exc))

    def _category_name(self, category_id: str) -> str:
        for category in self.snapshot.categories:
            if category.id == category_id:
                return category.name
        return category_id

    def _category_id_for_name(self, category_name: str) -> str:
        for category in self.snapshot.categories:
            if category.name == category_name:
                return category.id
        return category_name

    def _budget_id_for(self, category_name: str, entry_type: str) -> str:
        category_id = self._category_id_for_name(category_name)
        for budget in self.snapshot.budgets:
            if budget.month == current_month() and budget.category_id == category_id and budget.entry_type == entry_type:
                return budget.id
        return ""

    def _account_name(self, account_id: str) -> str:
        for account in self.snapshot.accounts:
            if account.id == account_id:
                return account.name
        return account_id


def run_tui(repository: GoogleSheetsRepository | None = None) -> None:
    app = FinanceManagerApp(repository=repository)
    app.run()
