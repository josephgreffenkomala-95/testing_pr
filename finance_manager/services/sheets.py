from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from finance_manager.config.auth import load_oauth_credentials
from finance_manager.config.settings import AppConfig, load_app_config, persist_app_state
from finance_manager.models.entities import (
    Account,
    Budget,
    Category,
    PlanException,
    PlannedTransaction,
    RecurringPlan,
    Snapshot,
    Transaction,
)
from finance_manager.models.schemas import ROW_PARSERS, SHEET_HEADERS, entity_to_row
from finance_manager.services.gateway import (
    Clock,
    InMemoryFinanceGateway,
    RecordIdGenerator,
    SheetRef,
    generate_record_id,
    utc_now,
)


class FinanceManagerError(Exception):
    pass


class MissingCredentialsError(FinanceManagerError):
    pass


class InvalidSheetStructureError(FinanceManagerError):
    pass


class StaleRecordError(FinanceManagerError):
    pass


class ExternalServiceError(FinanceManagerError):
    pass


ENTITY_LISTS = {
    "Activity": "transactions",
    "Plans": "planned_transactions",
    "Recurring Plans": "recurring_plans",
    "Plan Exceptions": "plan_exceptions",
    "Budgets": "budgets",
    "Categories": "categories",
    "Accounts": "accounts",
}


DEFAULT_CATEGORIES = (
    ("Salary", "income"),
    ("Other income", "income"),
    ("Food", "expense"),
    ("Housing", "expense"),
    ("Transport", "expense"),
    ("Utilities", "expense"),
    ("Health", "expense"),
    ("Other expense", "expense"),
)


class GoogleSheetsRepository:
    requires_authentication = True

    def __init__(
        self,
        config: AppConfig | None = None,
        *,
        client_factory: Any | None = None,
        clock: Clock = utc_now,
        record_id_generator: RecordIdGenerator = generate_record_id,
    ) -> None:
        self.config = config or load_app_config()
        self._client_factory = client_factory
        self._clock = clock
        self._record_id_generator = record_id_generator
        self._client: Any | None = None
        self._spreadsheet: Any | None = None
        self._cache: Snapshot | None = None
        self.validation_errors: list[str] = []

    def now(self) -> datetime:
        return self._clock()

    def bootstrap(self) -> str:
        if self._spreadsheet is None:
            self._spreadsheet = self._open_or_create_spreadsheet()
        self._ensure_schema()
        self._seed_foundation(self.config.spreadsheet_title, "IDR")
        spreadsheet_id = getattr(self._spreadsheet, "id", "") or ""
        if spreadsheet_id:
            persist_app_state(
                self.config,
                spreadsheet_id=spreadsheet_id,
                spreadsheet_title=getattr(self._spreadsheet, "title", self.config.spreadsheet_title),
            )
            self.config = replace(self.config, spreadsheet_id=spreadsheet_id)
        return spreadsheet_id

    def create_finance_sheet(self, base_currency: str = "IDR", title: str | None = None) -> str:
        currency = base_currency.strip().upper()
        if not currency or len(currency) != 3 or not currency.isalpha():
            raise ValueError("Base Currency must be a three-letter currency code.")
        sheet_title = title or self.config.spreadsheet_title
        try:
            self._spreadsheet = self._get_client().create(sheet_title)
        except Exception as exc:
            raise ExternalServiceError(f"Could not create the Finance Sheet: {exc}") from exc
        self._cache = None
        self._ensure_schema()
        self._seed_foundation(sheet_title, currency)
        spreadsheet_id = getattr(self._spreadsheet, "id", "") or ""
        persist_app_state(
            self.config,
            spreadsheet_id=spreadsheet_id,
            spreadsheet_title=sheet_title,
            base_currency=currency,
        )
        self.config = replace(self.config, spreadsheet_id=spreadsheet_id, spreadsheet_title=sheet_title)
        return spreadsheet_id

    def spreadsheet_url(self) -> str:
        return getattr(self._spreadsheet, "url", "") if self._spreadsheet is not None else ""

    def list_spreadsheets(self) -> list[SheetRef]:
        try:
            spreadsheets = self._get_client().openall()
        except Exception as exc:
            raise ExternalServiceError(f"Could not list Google Sheets: {exc}") from exc
        return [
            SheetRef(getattr(spreadsheet, "id", ""), getattr(spreadsheet, "title", ""))
            for spreadsheet in spreadsheets
        ]

    def use_spreadsheet(self, spreadsheet_id: str, title: str = "") -> str:
        self.config = replace(
            self.config,
            spreadsheet_id=spreadsheet_id,
            spreadsheet_title=title or self.config.spreadsheet_title,
        )
        self._spreadsheet = None
        self._cache = None
        return self.bootstrap()

    def clear_cache(self) -> None:
        self._cache = None

    def load_snapshot(self) -> Snapshot:
        self._require_ready()
        if self._cache is not None:
            return self._cache
        self.validation_errors = []
        values: dict[str, Any] = {}
        for title, attribute in ENTITY_LISTS.items():
            values[attribute] = self._read_entities(title)
        snapshot = Snapshot(
            transactions=values["transactions"],
            planned_transactions=values["planned_transactions"],
            budgets=values["budgets"],
            categories=values["categories"],
            accounts=values["accounts"],
            settings=self._read_settings(),
            recurring_plans=values["recurring_plans"],
            plan_exceptions=values["plan_exceptions"],
        )
        self._validate_relationships(snapshot)
        self._cache = snapshot
        return snapshot

    def add_transaction(self, data: dict[str, str]) -> Transaction:
        return self._mutate("add_transaction", data)

    def add_transfer(self, data: dict[str, str]) -> Transaction:
        return self._mutate("add_transfer", data)

    def update_transaction(self, record_id: str, data: dict[str, str]) -> Transaction:
        self.clear_cache()
        self._ensure_current_version("transactions", record_id, data)
        return self._mutate("update_transaction", record_id, data)

    def void_transaction(self, record_id: str, reason: str) -> Transaction:
        return self._mutate("void_transaction", record_id, reason)

    def delete_transaction(self, record_id: str) -> None:
        self._mutate("void_transaction", record_id, "Voided from Activity")

    def get_transaction(self, record_id: str) -> Transaction:
        return self._find(self.load_snapshot().transactions, record_id)

    def reconcile_account(self, account_id: str, observed_balance: Decimal, effective_date: str) -> Transaction:
        return self._mutate("reconcile_account", account_id, observed_balance, effective_date)

    def add_planned_transaction(self, data: dict[str, str]) -> PlannedTransaction:
        return self._mutate("add_planned_transaction", data)

    def update_planned_transaction(self, record_id: str, data: dict[str, str]) -> PlannedTransaction:
        self.clear_cache()
        self._ensure_current_version("planned_transactions", record_id, data)
        return self._mutate("update_planned_transaction", record_id, data)

    def delete_planned_transaction(self, record_id: str) -> None:
        self._mutate("delete_planned_transaction", record_id)

    def get_planned_transaction(self, record_id: str) -> PlannedTransaction:
        return self._find(self.load_snapshot().planned_transactions, record_id)

    def complete_plan(self, record_id: str, actual: dict[str, str]) -> Transaction:
        return self._mutate("complete_plan", record_id, actual)

    def plan_variance(self, record_id: str) -> dict[str, tuple[object, object]]:
        gateway = self._memory_gateway(self.load_snapshot())
        return gateway.plan_variance(record_id)

    def add_recurring_plan(self, data: dict[str, str]) -> RecurringPlan:
        return self._mutate("add_recurring_plan", data)

    def update_recurring_plan(self, record_id: str, data: dict[str, str]) -> RecurringPlan:
        self.clear_cache()
        self._ensure_current_version("recurring_plans", record_id, data)
        return self._mutate("update_recurring_plan", record_id, data)

    def get_recurring_plan(self, record_id: str) -> RecurringPlan:
        return self._find(self.load_snapshot().recurring_plans, record_id)

    def add_plan_exception(self, data: dict[str, str]) -> PlanException:
        return self._mutate("add_plan_exception", data)

    def complete_occurrence(
        self,
        recurring_plan_id: str,
        occurrence_date: str,
        actual: dict[str, str],
    ) -> Transaction:
        return self._mutate("complete_occurrence", recurring_plan_id, occurrence_date, actual)

    def add_budget(self, data: dict[str, str]) -> Budget:
        return self._mutate("add_budget", data)

    def update_budget(self, record_id: str, data: dict[str, str]) -> Budget:
        self.clear_cache()
        self._ensure_current_version("budgets", record_id, data)
        return self._mutate("update_budget", record_id, data)

    def delete_budget(self, record_id: str) -> None:
        self._mutate("delete_budget", record_id)

    def copy_budgets(self, source_month: str, target_month: str) -> list[Budget]:
        return self._mutate("copy_budgets", source_month, target_month)

    def get_budget(self, record_id: str) -> Budget:
        return self._find(self.load_snapshot().budgets, record_id)

    def add_account(self, data: dict[str, str]) -> Account:
        return self._mutate("add_account", data)

    def update_account(self, record_id: str, data: dict[str, str]) -> Account:
        self.clear_cache()
        self._ensure_current_version("accounts", record_id, data)
        return self._mutate("update_account", record_id, data)

    def close_account(self, record_id: str) -> Account:
        return self._mutate("close_account", record_id)

    def delete_account(self, record_id: str) -> None:
        self._mutate("close_account", record_id)

    def get_account(self, record_id: str) -> Account:
        return self._find(self.load_snapshot().accounts, record_id)

    def rename_category(self, record_id: str, name: str) -> Category:
        return self._mutate("rename_category", record_id, name)

    def add_category(self, name: str, kind: str) -> Category:
        return self._mutate("add_category", name, kind)

    def archive_category(self, record_id: str) -> Category:
        return self._mutate("archive_category", record_id)

    def seed_dummy_data(self) -> int:
        return 0

    def _mutate(self, method_name: str, *args: Any) -> Any:
        self.clear_cache()
        snapshot = self.load_snapshot()
        if self.validation_errors:
            raise InvalidSheetStructureError(
                "Resolve Finance Sheet validation errors before writing: " + "; ".join(self.validation_errors)
            )
        gateway = self._memory_gateway(snapshot)
        method: Callable[..., Any] = getattr(gateway, method_name)
        result = method(*args)
        self._persist_snapshot(gateway.load_snapshot())
        self._cache = None
        return result

    def _memory_gateway(self, snapshot: Snapshot) -> InMemoryFinanceGateway:
        return InMemoryFinanceGateway(
            snapshot=snapshot,
            config=self.config,
            clock=self._clock,
            record_id_generator=self._record_id_generator,
        )

    def _ensure_current_version(self, attribute: str, record_id: str, data: dict[str, str]) -> None:
        supplied = data.get("version")
        if supplied is None:
            return
        current = self._find(getattr(self.load_snapshot(), attribute), record_id)
        if int(supplied) != current.version:
            raise StaleRecordError(
                f"This form used version {supplied}, but the Finance Sheet has newer version {current.version}. Reload first."
            )

    def _persist_snapshot(self, snapshot: Snapshot) -> None:
        for title, attribute in ENTITY_LISTS.items():
            worksheet = self._worksheet(title)
            headers = SHEET_HEADERS[title]
            self._replace_rows(worksheet, [entity_to_row(item, headers) for item in getattr(snapshot, attribute)])
        settings = [[key, value] for key, value in sorted(snapshot.settings.items())]
        self._replace_rows(self._worksheet("Settings"), settings)

    @staticmethod
    def _replace_rows(worksheet: Any, rows: list[list[str]]) -> None:
        if hasattr(worksheet, "clear"):
            worksheet.clear()
            worksheet.append_row(SHEET_HEADERS[worksheet.title])
        else:
            while len(getattr(worksheet, "rows", [])) > 1:
                worksheet.delete_rows(2)
        if rows:
            worksheet.append_rows(rows)

    def _read_entities(self, title: str) -> list[Any]:
        worksheet = self._worksheet(title)
        parser = ROW_PARSERS[title]
        parsed = []
        for row_number, row in enumerate(worksheet.get_all_records(), start=2):
            normalized = {str(key): value for key, value in row.items()}
            validation_error = self._validate_row(title, row_number, normalized)
            if validation_error:
                self.validation_errors.append(validation_error)
                continue
            try:
                parsed.append(parser(normalized))
            except (KeyError, ValueError, TypeError, InvalidOperation):
                self.validation_errors.append(self._row_error(title, row_number, normalized))
        return parsed

    @staticmethod
    def _validate_row(title: str, row_number: int, row: dict[str, Any]) -> str:
        choice_fields = {
            "Activity": {"entry_type": {"income", "expense", "transfer", "adjustment"}},
            "Plans": {
                "entry_type": {"income", "expense", "transfer"},
                "status": {"planned", "confirmed", "completed", "cancelled"},
                "schedule_precision": {"exact", "month", "unscheduled"},
            },
            "Recurring Plans": {
                "entry_type": {"income", "expense", "transfer"},
                "status": {"planned", "confirmed", "cancelled"},
                "frequency": {"weekly", "monthly", "yearly"},
            },
            "Plan Exceptions": {"action": {"changed", "cancelled", "completed"}},
            "Budgets": {"entry_type": {"income", "expense"}},
            "Categories": {"kind": {"income", "expense"}},
            "Accounts": {"account_type": {"cash", "bank", "e-wallet"}},
        }
        for column, allowed in choice_fields.get(title, {}).items():
            value = str(row.get(column, ""))
            if value not in allowed:
                return f"{title} row {row_number}, column {column}: invalid value '{value}'"
        date_fields = {
            "Activity": ("date",),
            "Plans": ("expected_date",),
            "Recurring Plans": ("start_date", "end_date"),
            "Plan Exceptions": ("occurrence_date", "replacement_date"),
            "Accounts": ("opening_date",),
        }
        for column in date_fields.get(title, ()):
            value = str(row.get(column, ""))
            if not value and column in {"expected_date", "end_date", "replacement_date"}:
                continue
            try:
                date.fromisoformat(value)
            except ValueError:
                return f"{title} row {row_number}, column {column}: invalid value '{value}'"
        month_fields = {
            "Plans": ("scheduled_month",),
            "Budgets": ("month",),
        }
        for column in month_fields.get(title, ()):
            value = str(row.get(column, ""))
            if not value and title == "Plans":
                continue
            try:
                datetime.strptime(value, "%Y-%m")
            except ValueError:
                return f"{title} row {row_number}, column {column}: invalid value '{value}'"
        return ""

    def _validate_relationships(self, snapshot: Snapshot) -> None:
        account_ids = {account.id for account in snapshot.accounts}
        category_ids = {category.id for category in snapshot.categories}
        for row_number, activity in enumerate(snapshot.transactions, start=2):
            if activity.account_id not in account_ids:
                self.validation_errors.append(
                    f"Activity row {row_number}, column account_id: invalid value '{activity.account_id}'"
                )
            if activity.category_id and activity.category_id not in category_ids:
                self.validation_errors.append(
                    f"Activity row {row_number}, column category_id: invalid value '{activity.category_id}'"
                )
            if activity.destination_account_id and activity.destination_account_id not in account_ids:
                self.validation_errors.append(
                    f"Activity row {row_number}, column destination_account_id: invalid value "
                    f"'{activity.destination_account_id}'"
                )

    @staticmethod
    def _row_error(title: str, row_number: int, row: dict[str, Any]) -> str:
        decimal_fields = {
            "Activity": ("amount",),
            "Plans": ("amount",),
            "Recurring Plans": ("amount",),
            "Plan Exceptions": ("replacement_amount",),
            "Budgets": ("amount",),
            "Accounts": ("current_balance",),
        }
        for column in decimal_fields.get(title, ()):
            value = row.get(column, "")
            if value == "" and title == "Plan Exceptions":
                continue
            try:
                Decimal(str(value))
            except InvalidOperation:
                return f"{title} row {row_number}, column {column}: invalid value '{value}'"
        for required in ("id",):
            if not row.get(required):
                return f"{title} row {row_number}, column {required}: invalid value '{row.get(required, '')}'"
        return f"{title} row {row_number}: record contains invalid values"

    def _read_settings(self) -> dict[str, str]:
        return {
            str(row.get("key", "")): str(row.get("value", ""))
            for row in self._worksheet("Settings").get_all_records()
            if row.get("key")
        }

    def _ensure_schema(self) -> None:
        spreadsheet = self._require_spreadsheet()
        existing = {worksheet.title: worksheet for worksheet in spreadsheet.worksheets()}
        for title, headers in SHEET_HEADERS.items():
            if title not in existing:
                worksheet = spreadsheet.add_worksheet(title=title, rows=100, cols=max(8, len(headers)))
                worksheet.append_row(headers)
            else:
                worksheet = existing[title]
                found = worksheet.row_values(1)
                if not found:
                    worksheet.append_row(headers)
                elif found != headers:
                    raise InvalidSheetStructureError(
                        f"Finance Sheet tab '{title}' row 1 has invalid headers. Expected {headers}; found {found}."
                    )
            self._format_worksheet(worksheet, title)

    @staticmethod
    def _format_worksheet(worksheet: Any, title: str) -> None:
        if hasattr(worksheet, "freeze"):
            worksheet.freeze(rows=1)
        if hasattr(worksheet, "set_basic_filter"):
            worksheet.set_basic_filter()
        if hasattr(worksheet, "format"):
            worksheet.format("1:1", {"textFormat": {"bold": True}})
        if hasattr(worksheet, "add_protected_range") and title != "Settings":
            system_columns = [
                index + 1
                for index, header in enumerate(SHEET_HEADERS[title])
                if header in {"id", "version", "created_at", "updated_at", "linked_plan_id", "completed_activity_id"}
            ]
            for column in system_columns:
                try:
                    worksheet.add_protected_range(f"{column}:{column}", "Managed by Finance Manager", warning_only=True)
                except TypeError:
                    break

    def _seed_foundation(self, title: str, base_currency: str) -> None:
        settings = self._read_settings()
        if not settings:
            self._replace_rows(
                self._worksheet("Settings"),
                [["base_currency", base_currency], ["finance_sheet_title", title], ["schema_version", "1"]],
            )
        if not self._read_entities("Categories"):
            timestamp = self._timestamp()
            categories = [
                Category(self._record_id_generator("CAT"), name, kind, True, 1, timestamp, timestamp)
                for name, kind in DEFAULT_CATEGORIES
            ]
            headers = SHEET_HEADERS["Categories"]
            self._replace_rows(
                self._worksheet("Categories"),
                [entity_to_row(category, headers) for category in categories],
            )
        self._cache = None

    def _open_or_create_spreadsheet(self) -> Any:
        client = self._get_client()
        try:
            if self.config.spreadsheet_id:
                return client.open_by_key(self.config.spreadsheet_id)
            return client.open(self.config.spreadsheet_title)
        except Exception as exc:
            try:
                return client.create(self.config.spreadsheet_title)
            except Exception as create_exc:
                raise ExternalServiceError(f"Could not open or create the Finance Sheet: {create_exc}") from exc

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if self._client_factory is not None:
            self._client = self._client_factory()
            return self._client
        try:
            import gspread
        except ImportError as exc:
            raise MissingCredentialsError("Package dependency 'gspread' is missing.") from exc
        try:
            self._client = gspread.authorize(load_oauth_credentials(self.config))
        except FileNotFoundError as exc:
            raise MissingCredentialsError(str(exc)) from exc
        except Exception as exc:
            raise MissingCredentialsError("Google authorization failed. Connect Google again.") from exc
        return self._client

    def _require_ready(self) -> None:
        if self._spreadsheet is None:
            self.bootstrap()

    def _require_spreadsheet(self) -> Any:
        if self._spreadsheet is None:
            raise ExternalServiceError("No Finance Sheet is open.")
        return self._spreadsheet

    def _worksheet(self, title: str) -> Any:
        try:
            return self._require_spreadsheet().worksheet(title)
        except Exception as exc:
            raise InvalidSheetStructureError(f"Finance Sheet is missing the '{title}' tab.") from exc

    def _timestamp(self) -> str:
        return self.now().astimezone(UTC).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _find(items: list[Any], record_id: str) -> Any:
        for item in items:
            if item.id == record_id:
                return item
        raise KeyError(record_id)
