from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from finance_manager.config.auth import load_oauth_credentials
from finance_manager.config.settings import AppConfig, load_app_config, persist_app_state
from finance_manager.models.entities import Account, Budget, Category, PlannedTransaction, Snapshot, Transaction
from finance_manager.models.schemas import ROW_PARSERS, SHEET_HEADERS, entity_to_row


class FinanceManagerError(Exception):
    pass


class MissingCredentialsError(FinanceManagerError):
    pass


class InvalidSheetStructureError(FinanceManagerError):
    pass


class ExternalServiceError(FinanceManagerError):
    pass


def _require_choice(value: str, valid: tuple[str, ...], field: str) -> str:
    cleaned = value.strip().lower()
    if cleaned not in valid:
        raise ValueError(f"{field} must be one of: {', '.join(valid)}")
    return cleaned


def _require_amount(value: str) -> Decimal:
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("Amount must be numeric.") from exc
    if amount < 0:
        raise ValueError("Amount must be non-negative.")
    return amount.quantize(Decimal("0.01"))


def _require_date(value: str, *, allow_blank: bool = False) -> str | None:
    cleaned = value.strip()
    if not cleaned and allow_blank:
        return None
    try:
        return datetime.strptime(cleaned, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("Date must use YYYY-MM-DD.") from exc


def _require_month(value: str) -> str:
    cleaned = value.strip()
    try:
        return datetime.strptime(cleaned, "%Y-%m").strftime("%Y-%m")
    except ValueError as exc:
        raise ValueError("Month must use YYYY-MM.") from exc


class GoogleSheetsRepository:
    def __init__(
        self,
        config: AppConfig | None = None,
        *,
        client_factory: Any | None = None,
    ) -> None:
        self.config = config or load_app_config()
        self._client_factory = client_factory
        self._client = None
        self._spreadsheet = None

    def bootstrap(self) -> str:
        self._spreadsheet = self._open_or_create_spreadsheet()
        self._ensure_schema()
        self._seed_defaults()
        spreadsheet_id = getattr(self._spreadsheet, "id", None)
        if spreadsheet_id:
            persist_app_state(self.config, spreadsheet_id=spreadsheet_id, spreadsheet_title=self.config.spreadsheet_title)
        return spreadsheet_id or ""

    def load_snapshot(self) -> Snapshot:
        self._require_ready()
        return Snapshot(
            transactions=self._read_entities("Transactions"),
            planned_transactions=self._read_entities("Planned Transactions"),
            budgets=self._read_entities("Budgets"),
            categories=self._read_entities("Categories"),
            accounts=self._read_entities("Accounts"),
            settings=self._read_settings(),
        )

    def add_transaction(self, data: dict[str, str]) -> Transaction:
        snapshot = self.load_snapshot()
        category = self.ensure_category(data["category"], data["entry_type"])
        account = self.ensure_account(data["account"])
        entry = Transaction(
            id=self._next_id("Transactions", "TX"),
            entry_type=_require_choice(data["entry_type"], ("income", "expense"), "Type"),
            date=_require_date(data["date"]) or "",
            amount=_require_amount(data["amount"]),
            category_id=category.id,
            account_id=account.id,
            description=data["description"].strip(),
            notes=data.get("notes", "").strip(),
            created_at=self._now(),
            updated_at=self._now(),
        )
        self._append_entity("Transactions", entry)
        return entry

    def update_transaction(self, record_id: str, data: dict[str, str]) -> Transaction:
        current = self.get_transaction(record_id)
        category = self.ensure_category(data["category"], data["entry_type"])
        account = self.ensure_account(data["account"])
        updated = replace(
            current,
            entry_type=_require_choice(data["entry_type"], ("income", "expense"), "Type"),
            date=_require_date(data["date"]) or "",
            amount=_require_amount(data["amount"]),
            category_id=category.id,
            account_id=account.id,
            description=data["description"].strip(),
            notes=data.get("notes", "").strip(),
            updated_at=self._now(),
        )
        self._replace_entity("Transactions", updated)
        return updated

    def delete_transaction(self, record_id: str) -> None:
        self._delete_entity("Transactions", record_id)

    def add_planned_transaction(self, data: dict[str, str]) -> PlannedTransaction:
        category = self.ensure_category(data["category"], data["entry_type"])
        account = self.ensure_account(data["account"])
        entry = PlannedTransaction(
            id=self._next_id("Planned Transactions", "PLN"),
            entry_type=_require_choice(data["entry_type"], ("income", "expense"), "Type"),
            status=_require_choice(data["status"], ("planned", "confirmed", "completed", "cancelled"), "Status"),
            expected_date=_require_date(data.get("expected_date", ""), allow_blank=True),
            amount=_require_amount(data["amount"]),
            category_id=category.id,
            account_id=account.id,
            description=data["description"].strip(),
            notes=data.get("notes", "").strip(),
            created_at=self._now(),
            updated_at=self._now(),
        )
        self._append_entity("Planned Transactions", entry)
        return entry

    def update_planned_transaction(self, record_id: str, data: dict[str, str]) -> PlannedTransaction:
        current = self.get_planned_transaction(record_id)
        category = self.ensure_category(data["category"], data["entry_type"])
        account = self.ensure_account(data["account"])
        updated = replace(
            current,
            entry_type=_require_choice(data["entry_type"], ("income", "expense"), "Type"),
            status=_require_choice(data["status"], ("planned", "confirmed", "completed", "cancelled"), "Status"),
            expected_date=_require_date(data.get("expected_date", ""), allow_blank=True),
            amount=_require_amount(data["amount"]),
            category_id=category.id,
            account_id=account.id,
            description=data["description"].strip(),
            notes=data.get("notes", "").strip(),
            updated_at=self._now(),
        )
        self._replace_entity("Planned Transactions", updated)
        return updated

    def delete_planned_transaction(self, record_id: str) -> None:
        self._delete_entity("Planned Transactions", record_id)

    def add_budget(self, data: dict[str, str]) -> Budget:
        category = self.ensure_category(data["category"], data["entry_type"])
        budget = Budget(
            id=self._next_id("Budgets", "BDG"),
            month=_require_month(data["month"]),
            category_id=category.id,
            entry_type=_require_choice(data["entry_type"], ("income", "expense"), "Type"),
            amount=_require_amount(data["amount"]),
            notes=data.get("notes", "").strip(),
            created_at=self._now(),
            updated_at=self._now(),
        )
        self._append_entity("Budgets", budget)
        return budget

    def update_budget(self, record_id: str, data: dict[str, str]) -> Budget:
        current = self.get_budget(record_id)
        category = self.ensure_category(data["category"], data["entry_type"])
        updated = replace(
            current,
            month=_require_month(data["month"]),
            category_id=category.id,
            entry_type=_require_choice(data["entry_type"], ("income", "expense"), "Type"),
            amount=_require_amount(data["amount"]),
            notes=data.get("notes", "").strip(),
            updated_at=self._now(),
        )
        self._replace_entity("Budgets", updated)
        return updated

    def delete_budget(self, record_id: str) -> None:
        self._delete_entity("Budgets", record_id)

    def ensure_category(self, name: str, entry_type: str) -> Category:
        cleaned_name = name.strip()
        cleaned_type = _require_choice(entry_type, ("income", "expense"), "Type")
        for category in self._read_entities("Categories"):
            if category.name.lower() == cleaned_name.lower() and category.kind == cleaned_type:
                return category
        category = Category(id=self._next_id("Categories", "CAT"), name=cleaned_name, kind=cleaned_type, is_active=True)
        self._append_entity("Categories", category)
        return category

    def ensure_account(self, name: str) -> Account:
        cleaned_name = name.strip()
        for account in self._read_entities("Accounts"):
            if account.name.lower() == cleaned_name.lower():
                return account
        account = Account(
            id=self._next_id("Accounts", "ACC"),
            name=cleaned_name,
            account_type="cash",
            currency="IDR",
            current_balance=Decimal("0.00"),
            is_active=True,
        )
        self._append_entity("Accounts", account)
        return account

    def get_transaction(self, record_id: str) -> Transaction:
        return self._get_entity("Transactions", record_id)

    def get_planned_transaction(self, record_id: str) -> PlannedTransaction:
        return self._get_entity("Planned Transactions", record_id)

    def get_budget(self, record_id: str) -> Budget:
        return self._get_entity("Budgets", record_id)

    def _require_ready(self) -> None:
        if self._spreadsheet is None:
            self.bootstrap()

    def _open_or_create_spreadsheet(self):
        client = self._get_client()
        try:
            if self.config.spreadsheet_id:
                return client.open_by_key(self.config.spreadsheet_id)
            return client.open(self.config.spreadsheet_title)
        except Exception as exc:
            try:
                created = client.create(self.config.spreadsheet_title)
                return created
            except Exception as create_exc:
                raise ExternalServiceError(str(create_exc)) from exc

    def _get_client(self):
        if self._client is not None:
            return self._client
        if self._client_factory is not None:
            self._client = self._client_factory()
            return self._client
        try:
            import gspread
        except ImportError as exc:
            raise MissingCredentialsError("Package dependency `gspread` is missing.") from exc
        try:
            credentials = load_oauth_credentials(self.config)
        except FileNotFoundError as exc:
            raise MissingCredentialsError(str(exc)) from exc
        try:
            self._client = gspread.authorize(credentials)
        except Exception as exc:
            raise MissingCredentialsError(str(exc)) from exc
        return self._client

    def _ensure_schema(self) -> None:
        existing = {worksheet.title: worksheet for worksheet in self._spreadsheet.worksheets()}
        for title, headers in SHEET_HEADERS.items():
            if title not in existing:
                worksheet = self._spreadsheet.add_worksheet(title=title, rows=100, cols=max(8, len(headers)))
                worksheet.append_row(headers)
            else:
                worksheet = existing[title]
                row = worksheet.row_values(1)
                if not row:
                    worksheet.append_row(headers)
                elif row != headers:
                    raise InvalidSheetStructureError(
                        f"Worksheet `{title}` has invalid headers. Expected: {headers}. Found: {row}."
                    )

    def _seed_defaults(self) -> None:
        if not self._read_entities("Categories"):
            for category in [
                Category("CAT0001", "Salary", "income", True),
                Category("CAT0002", "Freelance", "income", True),
                Category("CAT0003", "Groceries", "expense", True),
                Category("CAT0004", "Rent", "expense", True),
                Category("CAT0005", "Transport", "expense", True),
            ]:
                self._append_entity("Categories", category)
        if not self._read_entities("Accounts"):
            self._append_entity(
                "Accounts",
                Account("ACC0001", "Cash", "cash", "IDR", Decimal("0.00"), True),
            )
        settings_sheet = self._worksheet("Settings")
        existing = settings_sheet.get_all_records()
        if not existing:
            settings_sheet.append_rows(
                [
                    ["default_currency", "IDR"],
                    ["created_by", "finance-manager"],
                ]
            )

    def _worksheet(self, title: str):
        return self._spreadsheet.worksheet(title)

    def _read_entities(self, title: str):
        worksheet = self._worksheet(title)
        records = worksheet.get_all_records()
        parser = ROW_PARSERS[title]
        return [parser({key: str(value) for key, value in row.items()}) for row in records if row]

    def _read_settings(self) -> dict[str, str]:
        worksheet = self._worksheet("Settings")
        settings: dict[str, str] = {}
        for row in worksheet.get_all_records():
            key = str(row.get("key", "")).strip()
            if key:
                settings[key] = str(row.get("value", ""))
        return settings

    def _append_entity(self, title: str, entity: object) -> None:
        worksheet = self._worksheet(title)
        worksheet.append_row(entity_to_row(entity, SHEET_HEADERS[title]))

    def _replace_entity(self, title: str, entity: object) -> None:
        worksheet = self._worksheet(title)
        records = worksheet.get_all_records()
        headers = SHEET_HEADERS[title]
        entity_id = getattr(entity, "id")
        for index, row in enumerate(records, start=2):
            if str(row.get("id")) == entity_id:
                worksheet.update(f"A{index}:{self._col_name(len(headers))}{index}", [entity_to_row(entity, headers)])
                return
        raise KeyError(entity_id)

    def _delete_entity(self, title: str, record_id: str) -> None:
        worksheet = self._worksheet(title)
        records = worksheet.get_all_records()
        for index, row in enumerate(records, start=2):
            if str(row.get("id")) == record_id:
                worksheet.delete_rows(index)
                return
        raise KeyError(record_id)

    def _get_entity(self, title: str, record_id: str):
        for entity in self._read_entities(title):
            if entity.id == record_id:
                return entity
        raise KeyError(record_id)

    def _next_id(self, title: str, prefix: str) -> str:
        values = [entity.id for entity in self._read_entities(title)]
        highest = 0
        for value in values:
            if value.startswith(prefix):
                try:
                    highest = max(highest, int(value[len(prefix):]))
                except ValueError:
                    continue
        return f"{prefix}{highest + 1:04d}"

    @staticmethod
    def _col_name(index: int) -> str:
        label = ""
        while index:
            index, remainder = divmod(index - 1, 26)
            label = chr(65 + remainder) + label
        return label

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
