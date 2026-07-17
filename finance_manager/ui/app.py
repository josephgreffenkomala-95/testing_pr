from __future__ import annotations

import calendar
import webbrowser
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Callable

from rich.panel import Panel
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Static

from finance_manager.config.auth import credential_store, run_oauth_flow, validate_oauth_client_file
from finance_manager.config.settings import AppConfig, persist_app_state
from finance_manager.logic.calculations import (
    account_balances,
    current_month,
    expand_recurring_plan,
    month_budget_report,
    projection_summary,
)
from finance_manager.models.entities import Account, Budget, PlannedTransaction, RecurringPlan, Snapshot, Transaction
from finance_manager.services.gateway import FinanceGateway, SheetRef
from finance_manager.services.sheets import (
    ExternalServiceError,
    FinanceManagerError,
    GoogleSheetsRepository,
    InvalidSheetStructureError,
    MissingCredentialsError,
)
from finance_manager.ui.forms import FormField, RecordFormScreen
from finance_manager.ui.screens import (
    ClientSecretResult,
    ConfirmationScreen,
    LoginScreen,
    SheetSelectScreen,
    SetupScreen,
    WorkspaceSetupResult,
    WorkspaceSetupScreen,
)


APP_CSS = """
Screen { background: #1a1b26; color: #c0caf5; }
Header { background: #7aa2f7; color: #1a1b26; }
Footer { background: #24283b; color: #c0caf5; }
#body-wrap { height: 1fr; }
#sidebar { width: 34; min-width: 24; padding: 1 2; background: #24283b; border-right: solid #414868; }
#main { width: 1fr; padding: 1; }
#tabs { height: 3; color: #7aa2f7; text-style: bold; }
#record-list { height: 1fr; border: solid #414868; background: #24283b; }
#detail { height: 7; padding: 1; background: #24283b; }
#status { height: 3; padding: 0 1; color: #7dcfff; }
DataTable > .datatable--header { background: #1a1b26; color: #7aa2f7; text-style: bold; }
DataTable > .datatable--cursor { background: #2ac3de; color: #1a1b26; }
.theme-light Screen { background: #f2f4f8; color: #20242c; }
.theme-light #sidebar, .theme-light #record-list, .theme-light #detail { background: #ffffff; color: #20242c; }
.theme-contrast Screen { background: #000000; color: #ffffff; }
.theme-contrast #sidebar, .theme-contrast #record-list, .theme-contrast #detail { background: #000000; color: #ffffff; border: double #ffffff; }
"""


THEMES = ("tokyonight", "light", "high-contrast")
VIEW_LABELS = {
    "dashboard": "Dashboard",
    "activity": "Activity",
    "plans": "Plans",
    "budgets": "Budgets",
    "projection": "Projection",
    "accounts": "Accounts",
    "settings": "Settings & Google Sheets",
}


@dataclass(frozen=True)
class RowRef:
    record_id: str
    values: tuple[str, ...]
    detail: str


def _default_oauth_flow(config: AppConfig) -> str:
    store = credential_store(config)
    run_oauth_flow(config, store)
    return store.disclosure


class FinanceManagerApp(App[None]):
    CSS = APP_CSS
    BINDINGS = [
        Binding("1", "switch_view('dashboard')", "Dashboard"),
        Binding("2", "switch_view('activity')", "Activity"),
        Binding("3", "switch_view('plans')", "Plans"),
        Binding("4", "switch_view('budgets')", "Budgets"),
        Binding("5", "switch_view('projection')", "Projection"),
        Binding("6", "switch_view('accounts')", "Accounts"),
        Binding("7", "switch_view('settings')", "Settings"),
        Binding("i", "add_income", "Add income"),
        Binding("x", "add_expense", "Add expense"),
        Binding("t", "add_transfer", "Add transfer"),
        Binding("a", "add_record", "Add"),
        Binding("e", "edit_record", "Edit"),
        Binding("c", "complete_plan", "Complete"),
        Binding("g", "add_recurring", "Recurring Plan"),
        Binding("f", "filter_activity", "Filter Activity"),
        Binding("b", "reconcile", "Reconcile"),
        Binding("p", "projection_date", "Projection Date"),
        Binding("y", "copy_budgets", "Copy Budgets"),
        Binding("k", "manage_categories", "Categories"),
        Binding("d", "retire_record", "Void/Cancel/Close"),
        Binding("r", "reload_data", "Reload"),
        Binding("ctrl+s", "sync_now", "Sync now"),
        Binding("ctrl+t", "cycle_theme", "Theme"),
        Binding("o", "open_sheet", "Open Sheet"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        gateway: FinanceGateway | None = None,
        *,
        oauth_flow: Callable[[AppConfig], str] = _default_oauth_flow,
        oauth_client_validator: Callable[[Path], Path] = validate_oauth_client_file,
    ) -> None:
        super().__init__()
        self.repository = gateway or GoogleSheetsRepository()
        self.oauth_flow = oauth_flow
        self.oauth_client_validator = oauth_client_validator
        self.snapshot = Snapshot()
        self.current_view = "dashboard"
        self.current_rows: list[RowRef] = []
        self.error_message = ""
        self.authenticated = False
        self.visual_theme = self.repository.config.theme
        self.projection_date = self.repository.config.projection_date
        self.activity_filters: dict[str, str] = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="body-wrap"):
            yield Static(id="sidebar")
            with Vertical(id="main"):
                yield Static(id="tabs")
                yield DataTable(id="record-list")
                yield Static(id="detail")
                yield Static(id="status")
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(300, self._periodic_sync)
        self._apply_theme_class()
        if not self.repository.requires_authentication:
            self.authenticated = True
            self._load_data(initial=True)
            return
        if not self.repository.config.oauth_client_secret_path.exists():
            self.push_screen(
                SetupScreen(str(self.repository.config.oauth_client_secret_path)),
                self._on_setup_result,
            )
            return
        self._try_authenticate()

    def _try_authenticate(self) -> None:
        try:
            if not self.repository.config.spreadsheet_id:
                raise MissingCredentialsError("Finance Sheet setup is not complete.")
            self.repository.bootstrap()
            self.authenticated = True
            self._load_data(initial=True)
        except MissingCredentialsError:
            self.push_screen(LoginScreen(), self._on_login_result)
        except (InvalidSheetStructureError, ExternalServiceError) as exc:
            self._show_error(str(exc))

    def _on_setup_result(self, result: ClientSecretResult | None) -> None:
        if result is None or not result.proceed:
            self.exit()
            return
        path = Path(result.client_secret_path).expanduser()
        try:
            self.oauth_client_validator(path)
        except ValueError as exc:
            self._show_error(str(exc))
            self.push_screen(SetupScreen(str(path)), self._on_setup_result)
            return
        self.repository.config = replace(self.repository.config, oauth_client_secret_path=path)
        persist_app_state(self.repository.config, oauth_client_secret_path=path)
        self.push_screen(LoginScreen(), self._on_login_result)

    def _on_login_result(self, proceed: bool | None) -> None:
        if not proceed:
            self.exit()
            return
        try:
            disclosure = self.oauth_flow(self.repository.config)
        except Exception:
            self._show_error(
                "Google authorization failed or was cancelled. Check the Desktop OAuth file, browser, and connection, then retry."
            )
            return
        self.query_one("#status", Static).update(f"Google connected. {disclosure}")
        if self.repository.config.spreadsheet_id:
            self._try_authenticate()
            return
        self.push_screen(
            WorkspaceSetupScreen(self.repository.now().date().isoformat(), self.repository.config.base_currency),
            self._on_workspace_setup,
        )

    def _on_workspace_setup(self, result: WorkspaceSetupResult | None) -> None:
        if result is None:
            self.exit()
            return
        if result.use_existing:
            try:
                sheets = self.repository.list_spreadsheets()
            except FinanceManagerError as exc:
                self._show_error(f"Could not list compatible Finance Sheets: {exc}")
                return
            self.push_screen(SheetSelectScreen(sheets), self._on_sheet_selected)
            return
        try:
            create = getattr(self.repository, "create_finance_sheet")
            create(result.base_currency)
            self.repository.add_account(
                {
                    "name": result.account_name,
                    "account_type": result.account_type,
                    "currency": result.base_currency,
                    "opening_date": result.opening_date,
                    "opening_balance": result.opening_balance,
                }
            )
            self.authenticated = True
            self._load_data(initial=True)
        except (FinanceManagerError, ValueError, AttributeError) as exc:
            self._show_error(f"Could not create the Finance Sheet: {exc}")

    def _on_sheet_selected(self, sheet: SheetRef | None) -> None:
        if sheet is None:
            return
        try:
            self.repository.use_spreadsheet(sheet.spreadsheet_id, sheet.title)
            self.authenticated = True
            self._load_data(initial=True)
        except FinanceManagerError as exc:
            self._show_error(f"Could not open the Finance Sheet: {exc}")

    def _load_data(self, *, initial: bool = False) -> None:
        try:
            self.repository.bootstrap()
            self.snapshot = self.repository.load_snapshot()
            self.error_message = ""
            self.visual_theme = self.snapshot.settings.get("theme", self.visual_theme)
        except (MissingCredentialsError, InvalidSheetStructureError, ExternalServiceError) as exc:
            self.error_message = str(exc)
        status = self._sync_text()
        if initial:
            status = f"{status} · Ready."
        self._refresh_ui(status)

    def _refresh_ui(self, status_message: str = "") -> None:
        self.query_one("#tabs", Static).update(self._render_tabs())
        self.query_one("#sidebar", Static).update(self._render_sidebar())
        self.current_rows = self._rows_for_view()
        table = self.query_one("#record-list", DataTable)
        table.clear(columns=True)
        for column in self._columns_for_view():
            table.add_column(column)
        for row in self.current_rows:
            table.add_row(*row.values, key=row.record_id)
        self._update_detail()
        status = status_message or self._sync_text()
        if self.current_view == "activity":
            visible_ids = {row.record_id for row in self.current_rows}
            income = sum(
                (item.amount for item in self.snapshot.transactions if item.id in visible_ids and item.entry_type == "income" and not item.is_voided),
                Decimal("0"),
            )
            expense = sum(
                (item.amount for item in self.snapshot.transactions if item.id in visible_ids and item.entry_type == "expense" and not item.is_voided),
                Decimal("0"),
            )
            status = f"{status} · Visible totals: income {income:.2f}, expense {expense:.2f}, net {income - expense:+.2f}"
        self.query_one("#status", Static).update(status)

    def _render_tabs(self) -> str:
        labels = []
        for index, key in enumerate(VIEW_LABELS, start=1):
            label = VIEW_LABELS[key]
            labels.append(f"[{index} {label}]" if key == self.current_view else f"{index} {label}")
        return "  ".join(labels)

    def _render_sidebar(self) -> str:
        if self.error_message:
            return f"[ERROR]\n{self.error_message}\n\nPress 7 for Settings & Google Sheets."
        validation_errors = getattr(self.repository, "validation_errors", [])
        if validation_errors:
            return "[ERROR] Finance Sheet validation\n\nFinancial totals are withheld until these relationships are safe:\n" + "\n".join(
                validation_errors[:5]
            )
        balances = account_balances(self.snapshot)
        current = sum(balances.values(), Decimal("0"))
        target = self._projection_target()
        summary = projection_summary(self.snapshot, target, today=self.repository.now().date())
        currency = self.snapshot.settings.get("base_currency", self.repository.config.base_currency)
        account_lines = [
            f"  {account.name}: {self._format_money(balances.get(account.id, Decimal('0')), currency)}"
            for account in self.snapshot.accounts
            if account.is_active
        ]
        warnings = []
        if any(balance < 0 for balance in balances.values()):
            warnings.append("[WARNING] Negative Account balance")
        if summary.shortfall:
            warnings.append(f"[WARNING] Cash Shortfall on {summary.shortfall.date.isoformat()}")
        pending = sum(
            1
            for records in (
                self.snapshot.transactions,
                self.snapshot.planned_transactions,
                self.snapshot.budgets,
                self.snapshot.accounts,
            )
            for item in records
            if item.pending_sync
        )
        if pending:
            warnings.append(f"[PENDING SYNC] {pending} record(s)")
        return "\n".join(
            [
                "Finance Manager",
                "",
                f"Current Balance\n{self._format_money(current, currency)}",
                *account_lines,
                "",
                f"Projection Date: {target.isoformat()}",
                f"Expected: {self._format_money(summary.expected, currency)}",
                f"Confirmed: {self._format_money(summary.confirmed, currency)}",
                f"Budget-Safe: {self._format_money(summary.budget_safe, currency)}",
                f"Range: {self._format_money(summary.low, currency)} – {self._format_money(summary.high, currency)}",
                "",
                *(warnings or ["[OK] No current warnings"]),
                "",
                self._sync_text(),
            ]
        )

    def _projection_target(self) -> date:
        if self.projection_date:
            try:
                return date.fromisoformat(self.projection_date)
            except ValueError:
                self.projection_date = ""
        today = self.repository.now().date()
        return date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])

    def _rows_for_view(self) -> list[RowRef]:
        if self.current_view == "dashboard":
            return self._dashboard_rows()
        if self.current_view == "activity":
            return self._activity_rows()
        if self.current_view == "plans":
            return self._plan_rows()
        if self.current_view == "budgets":
            return self._budget_rows()
        if self.current_view == "projection":
            return self._projection_rows()
        if self.current_view == "accounts":
            return self._account_rows()
        return self._settings_rows()

    def _columns_for_view(self) -> tuple[str, ...]:
        return {
            "dashboard": ("When", "Upcoming", "Amount", "Confidence"),
            "activity": ("Date", "Kind", "Description", "Amount", "Account", "State"),
            "plans": ("Group", "Schedule", "Kind", "Description", "Amount", "Status"),
            "budgets": ("Category", "Budget/Target", "Actual", "Upcoming", "Remaining", "State"),
            "projection": ("Date", "Event", "Change", "Account"),
            "accounts": ("Account", "Type", "Opening Date", "Current Balance", "State"),
            "settings": ("Setting", "Value"),
        }[self.current_view]

    def _dashboard_rows(self) -> list[RowRef]:
        rows = []
        for plan in self.snapshot.planned_transactions:
            if plan.status not in {"planned", "confirmed"}:
                continue
            schedule = plan.expected_date or plan.scheduled_month or "Needs scheduling"
            amount = self._signed_display(plan.entry_type, plan.amount)
            state = f"{plan.status}{' · PENDING SYNC' if plan.pending_sync else ''}"
            rows.append(RowRef(plan.id, (schedule, plan.description, amount, state), self._plan_detail(plan)))
        return sorted(rows, key=lambda row: row.values[0])

    def _activity_rows(self) -> list[RowRef]:
        account_names = {account.id: account.name for account in self.snapshot.accounts}
        rows = []
        for activity in sorted(self.snapshot.transactions, key=lambda item: item.date, reverse=True):
            if not self.activity_filters and activity.date[:7] != current_month(self.repository.now().date()):
                continue
            search = self.activity_filters.get("search", "").casefold()
            if search and search not in f"{activity.description} {activity.notes}".casefold():
                continue
            if self.activity_filters.get("start_date") and activity.date < self.activity_filters["start_date"]:
                continue
            if self.activity_filters.get("end_date") and activity.date > self.activity_filters["end_date"]:
                continue
            if self.activity_filters.get("kind") and activity.entry_type != self.activity_filters["kind"]:
                continue
            if self.activity_filters.get("account") and self._account_name(activity.account_id) != self.activity_filters["account"]:
                continue
            if self.activity_filters.get("category") and self._category_name(activity.category_id) != self.activity_filters["category"]:
                continue
            state = "VOIDED" if activity.is_voided else "PENDING SYNC" if activity.pending_sync else "Recorded"
            account = account_names.get(activity.account_id, activity.account_id)
            if activity.destination_account_id:
                account = f"{account} → {account_names.get(activity.destination_account_id, activity.destination_account_id)}"
            rows.append(
                RowRef(
                    activity.id,
                    (activity.date, activity.entry_type, activity.description, self._signed_display(activity.entry_type, activity.amount), account, state),
                    self._activity_detail(activity),
                )
            )
        return rows

    def _plan_rows(self) -> list[RowRef]:
        today = self.repository.now().date()
        rows = []
        for plan in self.snapshot.planned_transactions:
            schedule = plan.expected_date or plan.scheduled_month or "Unscheduled"
            if plan.status in {"completed", "cancelled"}:
                group = "History"
            elif plan.schedule_precision == "unscheduled":
                group = "Needs scheduling"
            elif plan.expected_date and date.fromisoformat(plan.expected_date) < today:
                group = "Overdue"
            else:
                group = "Upcoming"
            status = f"{plan.status}{' · PENDING SYNC' if plan.pending_sync else ''}"
            rows.append(
                RowRef(
                    plan.id,
                    (group, schedule, plan.entry_type, plan.description, self._signed_display(plan.entry_type, plan.amount), status),
                    self._plan_detail(plan),
                )
            )
        for rule in self.snapshot.recurring_plans:
            schedule = f"{rule.frequency} from {rule.start_date}"
            status = f"{rule.status}{' · PENDING SYNC' if rule.pending_sync else ''}"
            rows.append(
                RowRef(
                    rule.id,
                    ("Recurring rules", schedule, rule.entry_type, rule.description, self._signed_display(rule.entry_type, rule.amount), status),
                    f"Recurring Plan stored once as a {rule.frequency} rule.",
                )
            )
            for occurrence in expand_recurring_plan(rule, self._projection_target(), self.snapshot.plan_exceptions)[:3]:
                rows.append(
                    RowRef(
                        f"{rule.id}:{occurrence.date.isoformat()}",
                        ("Upcoming occurrence", occurrence.date.isoformat(), occurrence.entry_type, occurrence.description, self._signed_display(occurrence.entry_type, occurrence.amount), rule.status),
                        f"Traceable occurrence of Recurring Plan {rule.description}.",
                    )
                )
        return sorted(rows, key=lambda row: (row.values[0], row.values[1]))

    def _budget_rows(self) -> list[RowRef]:
        rows = []
        for usage in month_budget_report(self.snapshot, current_month(self.repository.now().date())):
            state = "WARNING: target not met" if usage.is_projected_overspent else "OK"
            rows.append(
                RowRef(
                    self._budget_id(usage.category_name, usage.entry_type),
                    (
                        usage.category_name,
                        f"{usage.budgeted:.2f}",
                        f"{usage.actual:.2f}",
                        f"{usage.planned:.2f}",
                        f"{usage.projected_remaining:.2f}",
                        state,
                    ),
                    f"{usage.entry_type.title()} Budget Performance for {usage.month}",
                )
            )
        return rows

    def _projection_rows(self) -> list[RowRef]:
        summary = projection_summary(
            self.snapshot,
            self._projection_target(),
            today=self.repository.now().date(),
        )
        return [
            RowRef(
                f"event-{index}",
                (event.date.isoformat(), event.label, f"{event.amount:+.2f}", self._account_name(event.account_id)),
                f"Chronological projected balance change: {event.amount:+.2f}",
            )
            for index, event in enumerate(summary.events)
        ]

    def _account_rows(self) -> list[RowRef]:
        balances = account_balances(self.snapshot)
        currency = self.snapshot.settings.get("base_currency", self.repository.config.base_currency)
        return [
            RowRef(
                account.id,
                (
                    account.name,
                    account.account_type,
                    account.opening_date,
                    self._format_money(balances[account.id], currency),
                    "Open" if account.is_active else "Closed · historical",
                ),
                f"Opening Balance: {self._format_money(account.opening_balance, currency)}\nVersion: {account.version}",
            )
            for account in self.snapshot.accounts
        ]

    def _settings_rows(self) -> list[RowRef]:
        rows = [
            ("Connection", "Connected" if self.authenticated else "Not connected"),
            ("Sync status", self._sync_text()),
            ("Finance Sheet", self.repository.config.spreadsheet_title),
            ("Finance Sheet URL", self.repository.spreadsheet_url() or "Available after connection"),
            ("Base Currency", self.snapshot.settings.get("base_currency", self.repository.config.base_currency)),
            ("Theme", self.visual_theme),
            ("OAuth storage", "Operating-system credential store or disclosed owner-only file fallback"),
        ]
        validation_errors = getattr(self.repository, "validation_errors", [])
        rows.extend(("Sheet validation", error) for error in validation_errors)
        return [RowRef(f"setting-{index}", (label, value), f"{label}: {value}") for index, (label, value) in enumerate(rows)]

    def _selected_row(self) -> RowRef | None:
        table = self.query_one("#record-list", DataTable)
        if table.cursor_row is None or table.cursor_row >= len(self.current_rows):
            return self.current_rows[0] if self.current_rows else None
        return self.current_rows[table.cursor_row]

    def _update_detail(self) -> None:
        row = self._selected_row()
        self.query_one("#detail", Static).update(
            Panel(row.detail if row else "No records in this view.", title="Details")
        )

    def on_data_table_row_highlighted(self, _event: DataTable.RowHighlighted) -> None:
        self._update_detail()

    def action_switch_view(self, view: str) -> None:
        self.current_view = view
        self._refresh_ui(f"{self._sync_text()} · Viewing {VIEW_LABELS[view]}.")

    def action_reload_data(self) -> None:
        self.repository.clear_cache()
        self._load_data()

    def action_sync_now(self) -> None:
        sync_now = getattr(self.repository, "sync_now", None)
        synchronize = sync_now or getattr(self.repository, "synchronize", None)
        if synchronize is None:
            self.action_reload_data()
            return
        try:
            synchronize()
            self.snapshot = self.repository.load_snapshot()
            self._refresh_ui(self._sync_text())
        except TypeError:
            self.query_one("#status", Static).update("Sync now requires a reachable Finance Sheet connection.")
        except FinanceManagerError as exc:
            self._show_error(str(exc))

    def _periodic_sync(self) -> None:
        if getattr(self.repository, "sync_now", None) is not None:
            self.action_sync_now()

    def action_cycle_theme(self) -> None:
        index = (THEMES.index(self.visual_theme) + 1) % len(THEMES) if self.visual_theme in THEMES else 0
        self.visual_theme = THEMES[index]
        self._apply_theme_class()
        if self.repository.requires_authentication:
            persist_app_state(self.repository.config, theme=self.visual_theme)
        self.query_one("#status", Static).update(f"Theme: {self.visual_theme} · Saved.")

    def _apply_theme_class(self) -> None:
        self.remove_class("theme-light", "theme-contrast")
        if self.visual_theme == "light":
            self.add_class("theme-light")
        elif self.visual_theme == "high-contrast":
            self.add_class("theme-contrast")

    def action_open_sheet(self) -> None:
        url = self.repository.spreadsheet_url()
        if not url:
            self.query_one("#status", Static).update("No Finance Sheet is open.")
            return
        message = "Opened Finance Sheet in browser." if webbrowser.open(url, new=2) else "Could not open a browser."
        self.query_one("#status", Static).update(message)

    def action_add_income(self) -> None:
        self.current_view = "activity"
        self._open_activity_form("income")

    def action_add_expense(self) -> None:
        self.current_view = "activity"
        self._open_activity_form("expense")

    def action_add_transfer(self) -> None:
        self.current_view = "activity"
        self._open_transfer_form()

    def action_add_record(self) -> None:
        if self.current_view == "activity":
            self._open_activity_form("expense")
        elif self.current_view == "plans":
            self._open_plan_form()
        elif self.current_view == "budgets":
            self._open_budget_form()
        elif self.current_view == "accounts":
            self._open_account_form()
        else:
            self.query_one("#status", Static).update("Add is available in Activity, Plans, Budgets, and Accounts.")

    def action_filter_activity(self) -> None:
        self.current_view = "activity"
        self.push_screen(
            RecordFormScreen(
                "Filter Activity",
                [
                    FormField("search", "Search description or notes", value=self.activity_filters.get("search", ""), required=False),
                    FormField("start_date", "Start Date", value=self.activity_filters.get("start_date", ""), input_type="date", required=False),
                    FormField("end_date", "End Date", value=self.activity_filters.get("end_date", ""), input_type="date", required=False),
                    FormField("kind", "Kind", value=self.activity_filters.get("kind", ""), required=False),
                    FormField("account", "Account", value=self.activity_filters.get("account", ""), required=False),
                    FormField("category", "Category", value=self.activity_filters.get("category", ""), required=False),
                ],
                "Leave every field blank to return to the current-month default.",
            ),
            self._apply_activity_filters,
        )

    def _apply_activity_filters(self, data: dict[str, str] | None) -> None:
        if data is None:
            return
        self.activity_filters = {key: value.strip() for key, value in data.items() if value.strip()}
        state = ", ".join(f"{key}={value}" for key, value in self.activity_filters.items()) or "current month"
        self._refresh_ui(f"Activity filters: {state}")

    def action_projection_date(self) -> None:
        self.push_screen(
            RecordFormScreen(
                "Projection Date",
                [FormField("projection_date", "Inclusive end-of-day date", value=self._projection_target().isoformat(), input_type="date")],
            ),
            self._save_projection_date,
        )

    def _save_projection_date(self, data: dict[str, str] | None) -> None:
        if data is None:
            return
        self.projection_date = data["projection_date"]
        if self.repository.requires_authentication:
            persist_app_state(self.repository.config, projection_date=self.projection_date)
        self._refresh_ui(f"Projection Date: {self.projection_date} · Saved.")

    def action_copy_budgets(self) -> None:
        if self.current_view != "budgets":
            self.query_one("#status", Static).update("Open Budgets before copying a month.")
            return
        month = current_month(self.repository.now().date())
        self.push_screen(
            RecordFormScreen(
                "Copy monthly Budgets and Income Targets",
                [
                    FormField("source_month", "Source month", value=month, input_type="month"),
                    FormField("target_month", "Target month", input_type="month"),
                ],
                "Copies are independent and never roll over automatically.",
            ),
            self._copy_budgets,
        )

    def _copy_budgets(self, data: dict[str, str] | None) -> None:
        if data is None:
            return
        try:
            copy = getattr(self.repository, "copy_budgets")
            copied = copy(data["source_month"], data["target_month"])
            self._after_write(f"Copied {len(copied)} Budget/Target record(s).")
        except (FinanceManagerError, ValueError, AttributeError) as exc:
            self._show_error(str(exc))

    def action_reconcile(self) -> None:
        if self.current_view != "accounts":
            self.query_one("#status", Static).update("Open Accounts and select one to reconcile.")
            return
        row = self._selected_row()
        if row is None:
            return
        account = next(item for item in self.snapshot.accounts if item.id == row.record_id)
        calculated = account_balances(self.snapshot)[account.id]
        self.push_screen(
            RecordFormScreen(
                f"Reconcile {account.name}",
                [
                    FormField("observed_balance", "Observed Balance", value=f"{calculated:.2f}", input_type="amount"),
                    FormField("effective_date", "Effective Date", value=self.repository.now().date().isoformat(), input_type="date"),
                ],
                f"Calculated Balance: {calculated:.2f}. A confirmed Balance Adjustment records the difference.",
            ),
            lambda data: self._confirm_reconciliation(account, calculated, data),
        )

    def _confirm_reconciliation(
        self,
        account: Account,
        calculated: Decimal,
        data: dict[str, str] | None,
    ) -> None:
        if data is None:
            return
        observed = Decimal(data["observed_balance"])
        difference = observed - calculated
        self.push_screen(
            ConfirmationScreen(
                "Create Balance Adjustment?",
                f"Observed: {observed:.2f}\nCalculated: {calculated:.2f}\nDifference: {difference:+.2f}\nDate: {data['effective_date']}",
                "Reconcile",
            ),
            lambda confirmed: self._reconcile(account.id, observed, data["effective_date"]) if confirmed else None,
        )

    def _reconcile(self, account_id: str, observed: Decimal, effective_date: str) -> None:
        try:
            reconcile = getattr(self.repository, "reconcile_account")
            reconcile(account_id, observed, effective_date)
            self._after_write("Account reconciled with a visible Balance Adjustment.")
        except (FinanceManagerError, ValueError, AttributeError) as exc:
            self._show_error(str(exc))

    def action_add_recurring(self) -> None:
        self._open_recurring_form()

    def _open_recurring_form(self, record: RecurringPlan | None = None) -> None:
        self.current_view = "plans"
        self.push_screen(
            RecordFormScreen(
                "Recurring Plan",
                [
                    FormField("entry_type", "Kind", value=record.entry_type if record else "expense", options=("income", "expense", "transfer")),
                    FormField("status", "Confidence", value=record.status if record else "planned", options=("planned", "confirmed")),
                    FormField("frequency", "Frequency", value=record.frequency if record else "monthly", options=("weekly", "monthly", "yearly")),
                    FormField("start_date", "Start Date", value=record.start_date if record else self.repository.now().date().isoformat(), input_type="date"),
                    FormField("end_date", "Optional End Date", value=record.end_date or "" if record else "", input_type="date", required=False),
                    FormField("amount", "Amount", value=f"{record.amount:.2f}" if record else "", input_type="amount"),
                    FormField("account", "Account", value=self._account_name(record.account_id) if record else "", options=self._open_account_names()),
                    FormField("category", "Category", value=self._category_name(record.category_id) if record and record.category_id else "", options=self._all_active_category_names(), required=False),
                    FormField("destination_account", "Transfer destination", value=self._account_name(record.destination_account_id) if record and record.destination_account_id else "", required=False),
                    FormField("description", "Description", value=record.description if record else ""),
                    FormField("notes", "Notes", value=record.notes if record else "", required=False),
                ],
                "Monthly rules use month-end when a day is missing, then return to the requested day.",
            ),
            lambda data: self._save_recurring(data, record),
        )

    def _save_recurring(self, data: dict[str, str] | None, record: RecurringPlan | None) -> None:
        if data is None:
            return
        try:
            payload = dict(data)
            if payload["entry_type"] == "transfer":
                payload["source_account"] = payload.pop("account")
            if record:
                update = getattr(self.repository, "update_recurring_plan")
                update(record.id, {**payload, "version": str(record.version)})
            else:
                add = getattr(self.repository, "add_recurring_plan")
                add(payload)
            self._after_write("Recurring Plan saved as one rule.")
        except (FinanceManagerError, ValueError, AttributeError) as exc:
            self._show_error(str(exc))

    def _open_occurrence_exception(self, occurrence_id: str) -> None:
        recurring_plan_id, occurrence_date = occurrence_id.split(":", 1)
        self.push_screen(
            RecordFormScreen(
                "Change one Plan Occurrence",
                [
                    FormField("action", "Action", value="changed", options=("changed", "cancelled")),
                    FormField("replacement_date", "Replacement Date", value=occurrence_date, input_type="date", required=False),
                    FormField("replacement_amount", "Replacement Amount", input_type="amount", required=False),
                ],
                "This creates a Plan Exception and leaves every other occurrence unchanged.",
            ),
            lambda data: self._save_occurrence_exception(recurring_plan_id, occurrence_date, data),
        )

    def _save_occurrence_exception(
        self,
        recurring_plan_id: str,
        occurrence_date: str,
        data: dict[str, str] | None,
    ) -> None:
        if data is None:
            return
        try:
            add = getattr(self.repository, "add_plan_exception")
            add({"recurring_plan_id": recurring_plan_id, "occurrence_date": occurrence_date, **data})
            self._after_write("Plan Exception saved for one occurrence.")
        except (FinanceManagerError, ValueError, AttributeError) as exc:
            self._show_error(str(exc))

    def action_manage_categories(self) -> None:
        names = ", ".join(category.name for category in self.snapshot.categories) or "None yet"
        self.push_screen(
            RecordFormScreen(
                "Manage Categories",
                [
                    FormField("action", "Action", value="create", options=("create", "rename", "archive")),
                    FormField("existing_name", "Existing Category", required=False),
                    FormField("name", "New name", required=False),
                    FormField("kind", "Type for creation", value="expense", options=("income", "expense")),
                ],
                f"Existing: {names}. Used Categories may be renamed or archived, never deleted or type-switched.",
            ),
            self._save_category_action,
        )

    def _save_category_action(self, data: dict[str, str] | None) -> None:
        if data is None:
            return
        try:
            if data["action"] == "create":
                if not data["name"].strip():
                    raise ValueError("New Category name is required.")
                add = getattr(self.repository, "add_category")
                add(data["name"], data["kind"])
                message = f"Created {data['kind']} Category."
            else:
                category = next(
                    item for item in self.snapshot.categories if item.name.casefold() == data["existing_name"].casefold()
                )
                if data["action"] == "rename":
                    if not data["name"].strip():
                        raise ValueError("New Category name is required.")
                    rename = getattr(self.repository, "rename_category")
                    rename(category.id, data["name"])
                    message = "Category renamed; history remains linked."
                else:
                    archive = getattr(self.repository, "archive_category")
                    archive(category.id)
                    message = "Category archived; history remains readable."
            self._after_write(message)
        except (FinanceManagerError, ValueError, AttributeError, StopIteration) as exc:
            self._show_error(str(exc))

    def action_edit_record(self) -> None:
        row = self._selected_row()
        if row is None:
            self.query_one("#status", Static).update("Nothing selected.")
            return
        if self.current_view == "activity":
            activity = self.repository.get_transaction(row.record_id)
            if activity.entry_type == "transfer":
                self._open_transfer_form(activity)
            else:
                self._open_activity_form(activity.entry_type, activity)
        elif self.current_view == "plans":
            recurring = next((item for item in self.snapshot.recurring_plans if item.id == row.record_id), None)
            if recurring:
                self._open_recurring_form(recurring)
            elif ":" in row.record_id:
                self._open_occurrence_exception(row.record_id)
            else:
                self._open_plan_form(self.repository.get_planned_transaction(row.record_id))
        elif self.current_view == "budgets":
            budget = next((item for item in self.snapshot.budgets if item.id == row.record_id), None)
            if budget:
                self._open_budget_form(budget)
        elif self.current_view == "accounts":
            account = next((item for item in self.snapshot.accounts if item.id == row.record_id), None)
            if account:
                self._open_account_form(account)

    def action_complete_plan(self) -> None:
        row = self._selected_row()
        if self.current_view != "plans" or row is None:
            self.query_one("#status", Static).update("Select an active Plan to complete.")
            return
        if ":" in row.record_id:
            recurring_plan_id, occurrence_date = row.record_id.split(":", 1)
            rule = next(item for item in self.snapshot.recurring_plans if item.id == recurring_plan_id)
            occurrence = next(
                item
                for item in expand_recurring_plan(rule, date.fromisoformat(occurrence_date), self.snapshot.plan_exceptions)
                if item.date.isoformat() == occurrence_date
            )
            synthetic = PlannedTransaction(
                row.record_id,
                rule.entry_type,
                rule.status,
                occurrence_date,
                occurrence.amount,
                rule.category_id,
                rule.account_id,
                rule.description,
                rule.notes,
                destination_account_id=rule.destination_account_id,
            )
            self.push_screen(
                RecordFormScreen(
                    "Complete Plan Occurrence",
                    self._completion_fields(synthetic),
                    "Creates linked Activity and a completed Plan Exception atomically.",
                ),
                lambda data: self._confirm_occurrence_completion(recurring_plan_id, occurrence_date, synthetic, data),
            )
            return
        plan = self.repository.get_planned_transaction(row.record_id)
        if plan.status not in {"planned", "confirmed"}:
            self.query_one("#status", Static).update("Only active Plans can be completed.")
            return
        fields = self._completion_fields(plan)
        self.push_screen(
            RecordFormScreen("Complete Plan", fields, "Confirm the actual financial values. Completion is atomic."),
            lambda data: self._confirm_plan_completion(plan, data),
        )

    def _confirm_plan_completion(self, plan: PlannedTransaction, data: dict[str, str] | None) -> None:
        if data is None:
            return
        impact = f"Creates Activity of {self._signed_display(plan.entry_type, Decimal(data['amount']))} and marks the Plan Completed."
        self.push_screen(
            ConfirmationScreen("Complete this Plan?", impact, "Complete Plan"),
            lambda confirmed: self._complete_plan(plan.id, data) if confirmed else None,
        )

    def _complete_plan(self, plan_id: str, data: dict[str, str]) -> None:
        try:
            complete = getattr(self.repository, "complete_plan")
            complete(plan_id, data)
            self._after_write("Plan completed and linked Activity recorded.")
        except (FinanceManagerError, ValueError, KeyError, AttributeError) as exc:
            self._show_error(str(exc))

    def _confirm_occurrence_completion(
        self,
        recurring_plan_id: str,
        occurrence_date: str,
        plan: PlannedTransaction,
        data: dict[str, str] | None,
    ) -> None:
        if data is None:
            return
        self.push_screen(
            ConfirmationScreen(
                "Complete this occurrence?",
                f"Creates linked Activity of {self._signed_display(plan.entry_type, Decimal(data['amount']))}; other occurrences are unchanged.",
                "Complete occurrence",
            ),
            lambda confirmed: self._complete_occurrence(recurring_plan_id, occurrence_date, data) if confirmed else None,
        )

    def _complete_occurrence(self, recurring_plan_id: str, occurrence_date: str, data: dict[str, str]) -> None:
        try:
            complete = getattr(self.repository, "complete_occurrence")
            complete(recurring_plan_id, occurrence_date, data)
            self._after_write("Plan Occurrence completed and linked Activity recorded.")
        except (FinanceManagerError, ValueError, AttributeError) as exc:
            self._show_error(str(exc))

    def action_retire_record(self) -> None:
        row = self._selected_row()
        if row is None:
            self.query_one("#status", Static).update("Nothing selected.")
            return
        if self.current_view == "activity":
            activity = self.repository.get_transaction(row.record_id)
            self.push_screen(
                RecordFormScreen(
                    "Void Activity",
                    [FormField("reason", "Reason", "Why is this Activity invalid?")],
                    f"Voiding removes the {activity.amount:.2f} effect but preserves history.",
                ),
                lambda data: self._confirm_void(activity, data),
            )
        elif self.current_view == "plans":
            plan = self.repository.get_planned_transaction(row.record_id)
            self.push_screen(
                ConfirmationScreen(
                    "Cancel this Plan?",
                    f"The future effect of {self._signed_display(plan.entry_type, plan.amount)} will be removed; history remains.",
                    "Cancel Plan",
                ),
                lambda confirmed: self._cancel_plan(plan.id) if confirmed else None,
            )
        elif self.current_view == "accounts":
            account = next(item for item in self.snapshot.accounts if item.id == row.record_id)
            self.push_screen(
                ConfirmationScreen(
                    "Close this Account?",
                    "Closure requires zero Current Balance and no active Plans. Historical Activity remains reproducible.",
                    "Close Account",
                ),
                lambda confirmed: self._close_account(account.id) if confirmed else None,
            )

    def _confirm_void(self, activity: Transaction, data: dict[str, str] | None) -> None:
        if data is None:
            return
        self.push_screen(
            ConfirmationScreen(
                "Void this Activity?",
                f"Before: {activity.entry_type} {activity.amount:.2f}. After: no balance or report effect. Reason: {data['reason']}",
                "Void Activity",
            ),
            lambda confirmed: self._void_activity(activity.id, data["reason"]) if confirmed else None,
        )

    def _void_activity(self, record_id: str, reason: str) -> None:
        try:
            void = getattr(self.repository, "void_transaction")
            void(record_id, reason)
            self._after_write("Activity voided; history preserved.")
        except (FinanceManagerError, ValueError, KeyError, AttributeError) as exc:
            self._show_error(str(exc))

    def _cancel_plan(self, record_id: str) -> None:
        try:
            self.repository.delete_planned_transaction(record_id)
            self._after_write("Plan cancelled; history preserved.")
        except (FinanceManagerError, ValueError, KeyError) as exc:
            self._show_error(str(exc))

    def _close_account(self, record_id: str) -> None:
        try:
            close = getattr(self.repository, "close_account")
            close(record_id)
            self._after_write("Account closed; history preserved.")
        except (FinanceManagerError, ValueError, KeyError, AttributeError) as exc:
            self._show_error(str(exc))

    def _open_activity_form(self, entry_type: str, record: Transaction | None = None) -> None:
        self.push_screen(
            RecordFormScreen(
                f"Add {entry_type}" if record is None else f"Edit {entry_type}",
                self._activity_fields(entry_type, record=record),
                "Choose an existing open Account and matching Category. Negative balances are allowed with a warning.",
            ),
            lambda data: self._save_activity(data, record, entry_type),
        )

    def _activity_fields(
        self,
        entry_type: str,
        *,
        record: Transaction | None = None,
        plan: PlannedTransaction | None = None,
    ) -> list[FormField]:
        source = record or plan
        return [
            FormField("date", "Date", "YYYY-MM-DD", record.date if record else self.repository.now().date().isoformat(), input_type="date"),
            FormField("amount", "Amount", "0.00", f"{source.amount:.2f}" if source else "", input_type="amount"),
            FormField("account", "Account", value=self._account_name(source.account_id) if source else "", options=self._open_account_names()),
            FormField("category", "Category", value=self._category_name(source.category_id) if source else "", options=self._category_names(entry_type)),
            FormField("description", "Description", "What happened?", source.description if source else ""),
            FormField("notes", "Notes", "Optional", source.notes if source else "", required=False),
        ]

    def _completion_fields(self, plan: PlannedTransaction) -> list[FormField]:
        if plan.entry_type != "transfer":
            return self._activity_fields(plan.entry_type, plan=plan)
        return [
            FormField("date", "Date", value=self.repository.now().date().isoformat(), input_type="date"),
            FormField("amount", "Amount", value=f"{plan.amount:.2f}", input_type="amount"),
            FormField("source_account", "From Account", value=self._account_name(plan.account_id), options=self._open_account_names()),
            FormField("destination_account", "To Account", value=self._account_name(plan.destination_account_id), options=self._open_account_names()),
            FormField("description", "Description", value=plan.description),
            FormField("notes", "Notes", value=plan.notes, required=False),
        ]

    def _open_transfer_form(self, record: Transaction | None = None) -> None:
        accounts = self._open_account_names()
        self.push_screen(
            RecordFormScreen(
                "Add transfer" if record is None else "Edit transfer",
                [
                    FormField("date", "Date", value=record.date if record else self.repository.now().date().isoformat(), input_type="date"),
                    FormField("amount", "Amount", value=f"{record.amount:.2f}" if record else "", input_type="amount"),
                    FormField("source_account", "From Account", value=self._account_name(record.account_id) if record else "", options=accounts),
                    FormField("destination_account", "To Account", value=self._account_name(record.destination_account_id) if record else "", options=accounts),
                    FormField("description", "Description", value=record.description if record else "Transfer"),
                    FormField("notes", "Notes", value=record.notes if record else "", required=False),
                ],
                "Transfers are one Activity event and never count as income, expense, or Budget usage.",
            ),
            lambda data: self._save_transfer(data, record),
        )

    def _save_activity(
        self,
        data: dict[str, str] | None,
        record: Transaction | None,
        entry_type: str,
    ) -> None:
        if data is None:
            return
        payload = {**data, "entry_type": record.entry_type if record else entry_type}
        if record and self._financial_activity_changed(record, payload):
            self.push_screen(
                ConfirmationScreen(
                    "Save financial changes?",
                    f"Before: {record.date}, {record.amount:.2f}, {self._account_name(record.account_id)}. "
                    f"After: {payload['date']}, {payload['amount']}, {payload['account']}.",
                    "Save changes",
                ),
                lambda confirmed: self._write_activity(payload, record.id) if confirmed else None,
            )
            return
        self._write_activity(payload, record.id if record else None)

    def _write_activity(self, data: dict[str, str], record_id: str | None) -> None:
        try:
            if record_id:
                current = self.repository.get_transaction(record_id)
                self.repository.update_transaction(record_id, {**data, "version": str(current.version)})
            else:
                self.repository.add_transaction(data)
            self._after_write("Activity saved.")
        except (FinanceManagerError, ValueError, KeyError) as exc:
            self._show_error(str(exc))

    def _save_transfer(self, data: dict[str, str] | None, record: Transaction | None) -> None:
        if data is None:
            return
        try:
            if record:
                self.repository.update_transaction(record.id, {**data, "version": str(record.version)})
            else:
                add_transfer = getattr(self.repository, "add_transfer")
                add_transfer(data)
            self._after_write("Transfer saved. Total wealth and Budget usage are unchanged.")
        except (FinanceManagerError, ValueError, KeyError, AttributeError) as exc:
            self._show_error(str(exc))

    def _open_plan_form(self, record: PlannedTransaction | None = None) -> None:
        entry_type = record.entry_type if record else "expense"
        self.push_screen(
            RecordFormScreen(
                "Plan future cash movement",
                [
                    FormField("entry_type", "Kind", value=entry_type, options=("income", "expense", "transfer")),
                    FormField("status", "Confidence", value=record.status if record else "planned", options=("planned", "confirmed")),
                    FormField("schedule_precision", "Schedule", value=record.schedule_precision if record else "exact", options=("exact", "month", "unscheduled")),
                    FormField("expected_date", "Exact Date", "YYYY-MM-DD", record.expected_date or "" if record else "", input_type="date", required=False),
                    FormField("scheduled_month", "Month-Only Schedule", "YYYY-MM", record.scheduled_month if record else "", input_type="month", required=False),
                    FormField("amount", "Best-estimate Amount", value=f"{record.amount:.2f}" if record else "", input_type="amount"),
                    FormField("account", "Account", value=self._account_name(record.account_id) if record else "", options=self._open_account_names()),
                    FormField("category", "Category", value=self._category_name(record.category_id) if record and record.category_id else "", options=self._all_active_category_names(), required=False),
                    FormField("destination_account", "Transfer destination", value=self._account_name(record.destination_account_id) if record and record.destination_account_id else "", options=("", *self._open_account_names()), required=False),
                    FormField("description", "Description", value=record.description if record else ""),
                    FormField("notes", "Notes", value=record.notes if record else "", required=False),
                ],
                "Use exact date, calendar month, or Unscheduled. Saved Plans are cancelled rather than deleted.",
            ),
            lambda data: self._save_plan(data, record),
        )

    def _save_plan(self, data: dict[str, str] | None, record: PlannedTransaction | None) -> None:
        if data is None:
            return
        try:
            payload = dict(data)
            if payload["entry_type"] == "transfer":
                payload["source_account"] = payload.pop("account")
            if record:
                self.repository.update_planned_transaction(record.id, {**payload, "version": str(record.version)})
            else:
                self.repository.add_planned_transaction(payload)
            self._after_write("Plan saved.")
        except (FinanceManagerError, ValueError, KeyError) as exc:
            self._show_error(str(exc))

    def _open_budget_form(self, record: Budget | None = None) -> None:
        entry_type = record.entry_type if record else "expense"
        self.push_screen(
            RecordFormScreen(
                "Monthly Budget or Income Target",
                [
                    FormField("month", "Month", value=record.month if record else current_month(self.repository.now().date()), input_type="month"),
                    FormField("entry_type", "Type", value=entry_type, options=("expense", "income")),
                    FormField("category", "Category", value=self._category_name(record.category_id) if record else "", options=self._all_active_category_names()),
                    FormField("amount", "Budget / Target", value=f"{record.amount:.2f}" if record else "", input_type="amount"),
                    FormField("notes", "Notes", value=record.notes if record else "", required=False),
                ],
                "Budgets apply across all Accounts, never roll over, and never block real Activity.",
            ),
            lambda data: self._save_budget(data, record),
        )

    def _save_budget(self, data: dict[str, str] | None, record: Budget | None) -> None:
        if data is None:
            return
        try:
            category = next(item for item in self.snapshot.categories if item.name == data["category"])
            data["entry_type"] = category.kind
            if record:
                self.repository.update_budget(record.id, {**data, "version": str(record.version)})
            else:
                self.repository.add_budget(data)
            self._after_write("Monthly Budget or Income Target saved.")
        except (FinanceManagerError, ValueError, KeyError, StopIteration) as exc:
            self._show_error(str(exc))

    def _open_account_form(self, record: Account | None = None) -> None:
        fields = [
            FormField("name", "Account name", value=record.name if record else ""),
            FormField("account_type", "Type", value=record.account_type if record else "cash", options=("cash", "bank", "e-wallet")),
        ]
        if record is None:
            fields.extend(
                [
                    FormField("currency", "Base Currency", value=self.snapshot.settings.get("base_currency", "IDR")),
                    FormField("opening_date", "Opening Date", value=self.repository.now().date().isoformat(), input_type="date"),
                    FormField("opening_balance", "Opening Balance", value="0.00", input_type="amount"),
                ]
            )
        self.push_screen(
            RecordFormScreen("Account", fields, "Opening Balance is dated; Current Balance is always derived from Activity."),
            lambda data: self._save_account(data, record),
        )

    def _save_account(self, data: dict[str, str] | None, record: Account | None) -> None:
        if data is None:
            return
        try:
            if record:
                self.repository.update_account(record.id, {**data, "version": str(record.version)})
            else:
                self.repository.add_account(data)
            self._after_write("Account saved.")
        except (FinanceManagerError, ValueError, KeyError) as exc:
            self._show_error(str(exc))

    def _after_write(self, message: str) -> None:
        self.snapshot = self.repository.load_snapshot()
        self._refresh_ui(f"{self._sync_text()} · {message}")

    def _show_error(self, message: str) -> None:
        self.error_message = message
        self.query_one("#status", Static).update(f"[ERROR] {message}")

    def _sync_text(self) -> str:
        status = str(getattr(self.repository, "sync_status", "Synced"))
        last = getattr(self.repository, "last_synced_at", None)
        return f"{status} · Last successful sync: {last}" if last else status

    def _open_account_names(self) -> tuple[str, ...]:
        return tuple(account.name for account in self.snapshot.accounts if account.is_active)

    def _category_names(self, kind: str) -> tuple[str, ...]:
        return tuple(category.name for category in self.snapshot.categories if category.is_active and category.kind == kind)

    def _all_active_category_names(self) -> tuple[str, ...]:
        return tuple(category.name for category in self.snapshot.categories if category.is_active)

    def _account_name(self, account_id: str) -> str:
        return next((account.name for account in self.snapshot.accounts if account.id == account_id), account_id)

    def _category_name(self, category_id: str) -> str:
        return next((category.name for category in self.snapshot.categories if category.id == category_id), category_id)

    def _budget_id(self, category_name: str, entry_type: str) -> str:
        category_id = next((category.id for category in self.snapshot.categories if category.name == category_name), "")
        return next(
            (
                budget.id
                for budget in self.snapshot.budgets
                if budget.month == current_month(self.repository.now().date())
                and budget.category_id == category_id
                and budget.entry_type == entry_type
            ),
            f"budget-{category_id}",
        )

    @staticmethod
    def _format_money(amount: Decimal, currency: str) -> str:
        return f"{currency} {amount:,.2f}"

    @staticmethod
    def _signed_display(entry_type: str, amount: Decimal) -> str:
        if entry_type == "income":
            return f"+{amount:.2f}"
        if entry_type == "expense":
            return f"-{amount:.2f}"
        return f"↔ {amount:.2f}"

    def _activity_detail(self, activity: Transaction) -> str:
        detail = [
            f"{activity.entry_type.title()} · {activity.date}",
            f"Amount: {activity.amount:.2f}",
            f"Account: {self._account_name(activity.account_id)}",
            f"Description: {activity.description}",
        ]
        if activity.destination_account_id:
            detail.append(f"Destination: {self._account_name(activity.destination_account_id)}")
        if activity.is_voided:
            detail.append(f"VOIDED: {activity.void_reason}")
        if activity.pending_sync:
            detail.append("PENDING SYNC")
        return "\n".join(detail)

    def _plan_detail(self, plan: PlannedTransaction) -> str:
        schedule = plan.expected_date or plan.scheduled_month or "Unscheduled"
        return "\n".join(
            [
                f"{plan.entry_type.title()} Plan · {plan.status}",
                f"Schedule: {plan.schedule_precision} · {schedule}",
                f"Amount: {plan.amount:.2f}",
                f"Account: {self._account_name(plan.account_id)}",
                "PENDING SYNC" if plan.pending_sync else "Synchronized",
            ]
        )

    def _financial_activity_changed(self, record: Transaction, data: dict[str, str]) -> bool:
        return any(
            (
                data["date"] != record.date,
                Decimal(data["amount"]) != record.amount,
                data["account"] != self._account_name(record.account_id),
                data["category"] != self._category_name(record.category_id),
            )
        )


def run_tui(gateway: FinanceGateway | None = None) -> None:
    FinanceManagerApp(gateway=gateway).run()
