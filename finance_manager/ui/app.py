from __future__ import annotations

from dataclasses import dataclass

from rich.panel import Panel
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Label, ListItem, ListView, Static

from finance_manager.logic.calculations import current_month, month_budget_report, projection, total_balance
from finance_manager.models.entities import Budget, PlannedTransaction, Snapshot, Transaction
from finance_manager.services.sheets import (
    ExternalServiceError,
    GoogleSheetsRepository,
    InvalidSheetStructureError,
    MissingCredentialsError,
)
from finance_manager.ui.forms import FormField, RecordFormScreen


@dataclass
class RowRef:
    record_id: str
    title: str
    subtitle: str


class FinanceListItem(ListItem):
    def __init__(self, row: RowRef) -> None:
        super().__init__(Label(f"{row.title}\n{row.subtitle}"))
        self.row = row


class FinanceManagerApp(App[None]):
    CSS = """
    Screen {
        background: #f4efe5;
        color: #231f20;
    }
    Header {
        background: #8f3b1b;
        color: #fff8f0;
    }
    Footer {
        background: #231f20;
        color: #f7f1e3;
    }
    #sidebar {
        width: 30;
        padding: 1 2;
        background: #e0d3bf;
        color: #36281d;
    }
    #main {
        padding: 1;
    }
    #tabs {
        height: 3;
        content-align: left middle;
        color: #8f3b1b;
        text-style: bold;
    }
    #body {
        height: 1fr;
    }
    #record-list {
        width: 1fr;
        min-width: 48;
        border: solid #b88a5a;
        background: #fffaf2;
    }
    #detail {
        width: 40;
        padding: 1;
        border: solid #b88a5a;
        background: #f8f2e8;
    }
    #status {
        height: 3;
        padding: 0 1;
        color: #6c4d31;
    }
    #form-modal {
        width: 72;
        height: auto;
        padding: 1 2;
        background: #fff8f0;
        border: round #8f3b1b;
    }
    .form-title {
        text-style: bold;
        color: #8f3b1b;
        margin-bottom: 1;
    }
    .form-label {
        margin-top: 1;
    }
    .form-hint {
        color: #6c4d31;
    }
    .form-buttons {
        margin-top: 1;
        height: auto;
    }
    """

    BINDINGS = [
        Binding("1", "switch_view('transactions')", "Transactions"),
        Binding("2", "switch_view('planned')", "Planned"),
        Binding("3", "switch_view('budgets')", "Budgets"),
        Binding("4", "switch_view('projection')", "Projection"),
        Binding("5", "switch_view('setup')", "Setup"),
        Binding("a", "add_record", "Add"),
        Binding("e", "edit_record", "Edit"),
        Binding("d", "delete_record", "Delete"),
        Binding("r", "reload_data", "Reload"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, repository: GoogleSheetsRepository | None = None) -> None:
        super().__init__()
        self.repository = repository or GoogleSheetsRepository()
        self.snapshot = Snapshot([], [], [], [], [], {})
        self.current_view = "transactions"
        self.current_rows: list[RowRef] = []
        self.error_message = ""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="body-wrap"):
            yield Static(id="sidebar")
            with Vertical(id="main"):
                yield Static(id="tabs")
                with Horizontal(id="body"):
                    yield ListView(id="record-list")
                    yield Static(id="detail")
                yield Static(id="status")
        yield Footer()

    def on_mount(self) -> None:
        self._load_data(initial=True)

    def _load_data(self, *, initial: bool = False) -> None:
        try:
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
        self.current_rows = self._rows_for_current_view()
        list_view = self.query_one("#record-list", ListView)
        list_view.clear()
        for row in self.current_rows:
            list_view.append(FinanceListItem(row))
        self._update_detail()
        self.query_one("#status", Static).update(status_message)

    def _render_tabs(self) -> str:
        items = [
            ("transactions", "1 Transactions"),
            ("planned", "2 Planned"),
            ("budgets", "3 Budgets"),
            ("projection", "4 Projection"),
            ("setup", "5 Setup"),
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
        lines = [
            "Finance",
            "",
            f"Sheet: {self.repository.config.spreadsheet_title}",
            f"Accounts: {len(self.snapshot.accounts)}",
            f"Categories: {len(self.snapshot.categories)}",
            f"Balance: {balance:.2f}",
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
            "r reload",
            "q quit",
        ]
        if self.error_message:
            lines.extend(["", "Status", self.error_message[:120]])
        return "\n".join(lines)

    def _rows_for_current_view(self) -> list[RowRef]:
        categories = {category.id: category.name for category in self.snapshot.categories}
        accounts = {account.id: account.name for account in self.snapshot.accounts}
        if self.current_view == "transactions":
            items = sorted(self.snapshot.transactions, key=lambda item: item.date, reverse=True)
            return [
                RowRef(
                    record_id=item.id,
                    title=f"{item.date}  {item.entry_type.upper()}  {item.amount:.2f}",
                    subtitle=f"{categories.get(item.category_id, item.category_id)} · {accounts.get(item.account_id, item.account_id)} · {item.description}",
                )
                for item in items
            ]
        if self.current_view == "planned":
            items = sorted(self.snapshot.planned_transactions, key=lambda item: item.expected_date or "9999-99-99")
            return [
                RowRef(
                    record_id=item.id,
                    title=f"{item.expected_date or 'No date'}  {item.status.upper()}  {item.amount:.2f}",
                    subtitle=f"{item.entry_type} · {categories.get(item.category_id, item.category_id)} · {item.description}",
                )
                for item in items
            ]
        if self.current_view == "budgets":
            budgets_by_id = {budget.id: budget for budget in self.snapshot.budgets if budget.month == current_month()}
            report = month_budget_report(self.snapshot, current_month())
            return [
                RowRef(
                    record_id=next(
                        (
                            budget.id
                            for budget in budgets_by_id.values()
                            if budget.category_id == self._category_id_for_name(row.category_name)
                            and budget.entry_type == row.entry_type
                        ),
                        row.category_name,
                    ),
                    title=f"{row.category_name}  budget {row.budgeted:.2f}",
                    subtitle=f"actual {row.actual:.2f} · planned {row.planned:.2f} · remaining {row.projected_remaining:.2f}",
                )
                for row in report
            ]
        if self.current_view == "projection":
            daily, _ = projection(self.snapshot)
            return [
                RowRef(
                    record_id=str(index),
                    title=f"{point.label}  balance {point.balance:.2f}",
                    subtitle=f"change {point.change:+.2f}",
                )
                for index, point in enumerate(daily)
            ]
        setup_lines = self._setup_rows()
        return [RowRef(str(index), title, subtitle) for index, (title, subtitle) in enumerate(setup_lines)]

    def _setup_rows(self) -> list[tuple[str, str]]:
        if self.error_message:
            return [
                ("Credentials or connectivity issue", self.error_message),
                (
                    "Expected OAuth client file",
                    str(self.repository.config.oauth_client_secret_path),
                ),
                (
                    "Auth help",
                    "Create a Google Desktop OAuth client, place the client JSON at the configured path, then run `finance-manager auth`.",
                ),
            ]
        return [
            ("Spreadsheet ID", self.repository.config.spreadsheet_id or "Stored after first successful bootstrap"),
            ("OAuth client file", str(self.repository.config.oauth_client_secret_path)),
            ("OAuth token file", str(self.repository.config.oauth_token_path)),
            ("Current title", self.repository.config.spreadsheet_title),
        ]

    def _selected_row(self) -> RowRef | None:
        list_view = self.query_one("#record-list", ListView)
        if list_view.index is None or list_view.index >= len(self.current_rows):
            return self.current_rows[0] if self.current_rows else None
        return self.current_rows[list_view.index]

    def _update_detail(self) -> None:
        row = self._selected_row()
        detail = self.query_one("#detail", Static)
        if row is None:
            detail.update(Panel("No records yet.\nPress `a` to add one.", title="Details"))
            return
        detail.update(Panel(f"{row.title}\n\n{row.subtitle}", title="Details"))

    def on_list_view_highlighted(self, _event: ListView.Highlighted) -> None:
        self._update_detail()

    def action_switch_view(self, view: str) -> None:
        self.current_view = view
        self._refresh_ui(f"Viewing {view}.")

    def action_reload_data(self) -> None:
        self._load_data()

    def action_add_record(self) -> None:
        if self.current_view == "transactions":
            self._open_transaction_form()
        elif self.current_view == "planned":
            self._open_planned_form()
        elif self.current_view == "budgets":
            self._open_budget_form()
        else:
            self.query_one("#status", Static).update("Add is available in Transactions, Planned, and Budgets.")

    def action_edit_record(self) -> None:
        row = self._selected_row()
        if row is None:
            self.query_one("#status", Static).update("Nothing selected.")
            return
        if self.current_view == "transactions":
            record = self.repository.get_transaction(row.record_id)
            self._open_transaction_form(record=record)
        elif self.current_view == "planned":
            record = self.repository.get_planned_transaction(row.record_id)
            self._open_planned_form(record=record)
        elif self.current_view == "budgets":
            budget = next((item for item in self.snapshot.budgets if item.id == row.record_id), None)
            if budget:
                self._open_budget_form(record=budget)
        else:
            self.query_one("#status", Static).update("Edit is not available in this view.")

    def action_delete_record(self) -> None:
        row = self._selected_row()
        if row is None:
            self.query_one("#status", Static).update("Nothing selected.")
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
            else:
                self.query_one("#status", Static).update("Delete is not available in this view.")
                return
            self.snapshot = self.repository.load_snapshot()
            self._refresh_ui("Deleted record.")
        except Exception as exc:
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
            RecordFormScreen("Transaction", fields, hint="Unknown categories/accounts are created automatically."),
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
            RecordFormScreen("Planned transaction", fields, hint="Leave expected date blank for unscheduled plans."),
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
            RecordFormScreen("Monthly budget", fields),
            lambda data: self._save_budget_form(data, record.id if record else None),
        )

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
        except Exception as exc:
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
        except Exception as exc:
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
        except Exception as exc:
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

    def _account_name(self, account_id: str) -> str:
        for account in self.snapshot.accounts:
            if account.id == account_id:
                return account.name
        return account_id


def run_tui(repository: GoogleSheetsRepository | None = None) -> None:
    app = FinanceManagerApp(repository=repository)
    app.run()
