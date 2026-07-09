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


def _is_spreadsheet_not_found(exc: BaseException) -> bool:
    """Return True when ``exc`` indicates the spreadsheet does not exist."""
    try:
        import gspread
    except ImportError:
        return False
    return isinstance(exc, gspread.SpreadsheetNotFound)


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
        self._cache: Snapshot | None = None
        self._id_counters: dict[str, int] = {}

    def bootstrap(self) -> str:
        if self._spreadsheet is not None:
            return getattr(self._spreadsheet, "id", "") or ""
        self._spreadsheet = self._open_or_create_spreadsheet()
        self._ensure_schema()
        self._seed_defaults()
        self._cache = None
        spreadsheet_id = getattr(self._spreadsheet, "id", None)
        if spreadsheet_id:
            persist_app_state(self.config, spreadsheet_id=spreadsheet_id, spreadsheet_title=self.config.spreadsheet_title)
        return spreadsheet_id or ""

    def spreadsheet_url(self) -> str:
        if self._spreadsheet is None:
            return ""
        return getattr(self._spreadsheet, "url", "") or ""

    def list_spreadsheets(self) -> list[tuple[str, str]]:
        client = self._get_client()
        try:
            spreadsheets = client.openall()
        except Exception as exc:
            raise ExternalServiceError(str(exc)) from exc
        return [(getattr(spreadsheet, "id", ""), getattr(spreadsheet, "title", "")) for spreadsheet in spreadsheets]

    def use_spreadsheet(self, spreadsheet_id: str, title: str = "") -> str:
        self.config = replace(self.config, spreadsheet_id=spreadsheet_id, spreadsheet_title=title or spreadsheet_id)
        self._spreadsheet = None
        self._cache = None
        return self.bootstrap()

    def clear_cache(self) -> None:
        self._cache = None

    def load_snapshot(self) -> Snapshot:
        self._require_ready()
        if self._cache is not None:
            return self._cache
        snapshot = Snapshot(
            transactions=self._read_entities("Transactions"),
            planned_transactions=self._read_entities("Planned Transactions"),
            budgets=self._read_entities("Budgets"),
            categories=self._read_entities("Categories"),
            accounts=self._read_entities("Accounts"),
            settings=self._read_settings(),
        )
        self._cache = snapshot
        self._init_id_counters(snapshot)
        return snapshot

    def add_transaction(self, data: dict[str, str]) -> Transaction:
        snapshot = self.load_snapshot()
        category = self.ensure_category(data["category"], data["entry_type"], categories=snapshot.categories)
        account = self.ensure_account(data["account"], accounts=snapshot.accounts)
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
        snapshot = self.load_snapshot()
        category = self.ensure_category(data["category"], data["entry_type"], categories=snapshot.categories)
        account = self.ensure_account(data["account"], accounts=snapshot.accounts)
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
        snapshot = self.load_snapshot()
        category = self.ensure_category(data["category"], data["entry_type"], categories=snapshot.categories)
        account = self.ensure_account(data["account"], accounts=snapshot.accounts)
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
        snapshot = self.load_snapshot()
        category = self.ensure_category(data["category"], data["entry_type"], categories=snapshot.categories)
        account = self.ensure_account(data["account"], accounts=snapshot.accounts)
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
        snapshot = self.load_snapshot()
        category = self.ensure_category(data["category"], data["entry_type"], categories=snapshot.categories)
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
        snapshot = self.load_snapshot()
        category = self.ensure_category(data["category"], data["entry_type"], categories=snapshot.categories)
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

    def ensure_category(self, name: str, entry_type: str, *, categories: list[Category] | None = None) -> Category:
        cleaned_name = name.strip()
        cleaned_type = _require_choice(entry_type, ("income", "expense"), "Type")
        existing = categories if categories is not None else self._read_entities("Categories")
        for category in existing:
            if category.name.lower() == cleaned_name.lower() and category.kind == cleaned_type:
                return category
        category = Category(id=self._next_id("Categories", "CAT"), name=cleaned_name, kind=cleaned_type, is_active=True)
        self._append_entity("Categories", category)
        return category

    def ensure_account(self, name: str, *, accounts: list[Account] | None = None) -> Account:
        cleaned_name = name.strip()
        existing = accounts if accounts is not None else self._read_entities("Accounts")
        for account in existing:
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

    def add_account(self, data: dict[str, str]) -> Account:
        cleaned_name = data["name"].strip()
        if not cleaned_name:
            raise ValueError("Account name is required.")
        account_type = data.get("account_type", "cash").strip().lower() or "cash"
        currency = data.get("currency", "IDR").strip().upper() or "IDR"
        balance = _require_amount(data.get("current_balance", "0"))
        snapshot = self.load_snapshot()
        for account in snapshot.accounts:
            if account.name.lower() == cleaned_name.lower():
                raise ValueError(f"Account '{cleaned_name}' already exists.")
        account = Account(
            id=self._next_id("Accounts", "ACC"),
            name=cleaned_name,
            account_type=account_type,
            currency=currency,
            current_balance=balance,
            is_active=True,
        )
        self._append_entity("Accounts", account)
        return account

    def update_account(self, record_id: str, data: dict[str, str]) -> Account:
        snapshot = self.load_snapshot()
        current = next((item for item in snapshot.accounts if item.id == record_id), None)
        if current is None:
            raise KeyError(record_id)
        new_name = data["name"].strip() or current.name
        for account in snapshot.accounts:
            if account.id != record_id and account.name.lower() == new_name.lower():
                raise ValueError(f"Account '{new_name}' already exists.")
        updated = replace(
            current,
            name=new_name,
            account_type=data.get("account_type", current.account_type).strip().lower() or current.account_type,
            currency=data.get("currency", current.currency).strip().upper() or current.currency,
            current_balance=_require_amount(data.get("current_balance", f"{current.current_balance:.2f}")),
        )
        self._replace_entity("Accounts", updated)
        return updated

    def delete_account(self, record_id: str) -> None:
        self._delete_entity("Accounts", record_id)

    def get_account(self, record_id: str) -> Account:
        snapshot = self.load_snapshot()
        for account in snapshot.accounts:
            if account.id == record_id:
                return account
        raise KeyError(record_id)

    def seed_dummy_data(self) -> int:
        snapshot = self.load_snapshot()
        created = 0
        if not snapshot.accounts:
            accounts = [
                Account("ACC0001", "Cash", "cash", "IDR", Decimal("1250000.00"), True),
                Account("ACC0002", "Bank BCA", "bank", "IDR", Decimal("8750000.00"), True),
                Account("ACC0003", "Bank Mandiri", "bank", "IDR", Decimal("3200000.00"), True),
            ]
            for account in accounts:
                self._append_entity("Accounts", account)
                created += 1
            snapshot = self.load_snapshot()
        accounts = snapshot.accounts
        needed_categories = ["Salary", "Freelance", "Groceries", "Rent", "Transport", "Dining", "Utilities"]
        existing_category_names = {category.name.lower() for category in snapshot.categories}
        for name in needed_categories:
            if name.lower() in existing_category_names:
                continue
            entry_type = "income" if name in {"Salary", "Freelance"} else "expense"
            category = Category(self._next_id("Categories", "CAT"), name, entry_type, True)
            self._append_entity("Categories", category)
            created += 1
        snapshot = self.load_snapshot()
        categories = snapshot.categories
        cat_by_name = {category.name: category for category in categories}
        accounts_by_name = {account.name: account for account in accounts}
        month = datetime.now(UTC).strftime("%Y-%m")
        if not snapshot.budgets:
            budgets = [
                ("Groceries", "expense", Decimal("1500000.00")),
                ("Rent", "expense", Decimal("3000000.00")),
                ("Transport", "expense", Decimal("500000.00")),
                ("Dining", "expense", Decimal("750000.00")),
                ("Utilities", "expense", Decimal("600000.00")),
            ]
            for index, (name, entry_type, amount) in enumerate(budgets, start=1):
                category = cat_by_name.get(name)
                if category is None:
                    continue
                budget = Budget(
                    id=f"BDG{index:04d}",
                    month=month,
                    category_id=category.id,
                    entry_type=entry_type,
                    amount=amount,
                )
                self._append_entity("Budgets", budget)
                created += 1
        if not snapshot.transactions:
            today = datetime.now(UTC)
            samples = [
                ("income", (today.replace(day=1)).strftime("%Y-%m-%d"), Decimal("12000000.00"), "Salary", "Bank BCA", "Monthly salary"),
                ("income", (today.replace(day=3)).strftime("%Y-%m-%d"), Decimal("2500000.00"), "Freelance", "Bank Mandiri", "Side project"),
                ("expense", (today.replace(day=2)).strftime("%Y-%m-%d"), Decimal("3000000.00"), "Rent", "Bank BCA", "Apartment rent"),
                ("expense", (today.replace(day=4)).strftime("%Y-%m-%d"), Decimal("425000.00"), "Groceries", "Cash", "Weekly groceries"),
                ("expense", (today.replace(day=5)).strftime("%Y-%m-%d"), Decimal("120000.00"), "Transport", "Cash", "Fuel"),
                ("expense", (today.replace(day=6)).strftime("%Y-%m-%d"), Decimal("185000.00"), "Dining", "Cash", "Dinner with friends"),
                ("expense", (today.replace(day=7)).strftime("%Y-%m-%d"), Decimal("320000.00"), "Utilities", "Bank BCA", "Electricity bill"),
            ]
            for index, (entry_type, date_str, amount, category_name, account_name, description) in enumerate(samples, start=1):
                category: Category | None = cat_by_name.get(category_name)
                account: Account | None = accounts_by_name.get(account_name)
                if category is None or account is None:
                    continue
                transaction = Transaction(
                    id=f"TX{index:04d}",
                    entry_type=entry_type,
                    date=date_str,
                    amount=amount,
                    category_id=category.id,
                    account_id=account.id,
                    description=description,
                    created_at=self._now(),
                    updated_at=self._now(),
                )
                self._append_entity("Transactions", transaction)
                created += 1
        return created

    def get_transaction(self, record_id: str) -> Transaction:
        return self._get_entity("Transactions", record_id)

    def get_planned_transaction(self, record_id: str) -> PlannedTransaction:
        return self._get_entity("Planned Transactions", record_id)

    def get_budget(self, record_id: str) -> Budget:
        return self._get_entity("Budgets", record_id)

    def _require_ready(self) -> bool:
        """Ensure a spreadsheet is open, bootstrapping one if needed.

        Returns True when ``bootstrap()`` was just invoked so callers know the
        spreadsheet was lazily initialised. Failures from ``bootstrap()`` are
        not swallowed — they propagate to the original caller so the error is
        visible instead of silently masking the read with an empty result.
        """
        if self._spreadsheet is None:
            self.bootstrap()
            return True
        return False

    def _open_or_create_spreadsheet(self):
        client = self._get_client()
        try:
            if self.config.spreadsheet_id:
                return client.open_by_key(self.config.spreadsheet_id)
            return client.open(self.config.spreadsheet_title)
        except Exception as exc:
            # Only attempt to create a new spreadsheet when the existing one
            # cannot be found. For auth/network/permission errors we surface
            # the original cause instead of masking it with a create attempt.
            if not _is_spreadsheet_not_found(exc):
                raise
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
        self._append_entity_cache_update(title, entity)

    def _append_entity_cache_update(self, title: str, entity: object) -> None:
        if self._cache is not None and hasattr(entity, "id"):
            entity_list = self._entity_list_for_title(self._cache, title)
            if entity_list is not None:
                entity_list.append(entity)
                self._bump_counter(self._id_counters, getattr(entity, "id", ""), self._prefix_for_title(title))

    def _replace_entity(self, title: str, entity: object) -> None:
        worksheet = self._worksheet(title)
        records = worksheet.get_all_records()
        headers = SHEET_HEADERS[title]
        entity_id = getattr(entity, "id")
        for index, row in enumerate(records, start=2):
            if str(row.get("id")) == entity_id:
                worksheet.update(f"A{index}:{self._col_name(len(headers))}{index}", [entity_to_row(entity, headers)])
                if self._cache is not None:
                    entity_list = self._entity_list_for_title(self._cache, title)
                    if entity_list is not None:
                        for idx, existing in enumerate(entity_list):
                            if existing.id == entity_id:
                                entity_list[idx] = entity
                                break
                return
        raise KeyError(entity_id)

    def _delete_entity(self, title: str, record_id: str) -> None:
        worksheet = self._worksheet(title)
        records = worksheet.get_all_records()
        for index, row in enumerate(records, start=2):
            if str(row.get("id")) == record_id:
                worksheet.delete_rows(index)
                if self._cache is not None:
                    entity_list = self._entity_list_for_title(self._cache, title)
                    if entity_list is not None:
                        entity_list[:] = [e for e in entity_list if e.id != record_id]
                return
        raise KeyError(record_id)

    def _init_id_counters(self, snapshot: Snapshot) -> None:
        counters = self._id_counters
        for tx in snapshot.transactions:
            self._bump_counter(counters, tx.id, "TX")
        for planned in snapshot.planned_transactions:
            self._bump_counter(counters, planned.id, "PLN")
        for budget in snapshot.budgets:
            self._bump_counter(counters, budget.id, "BDG")
        for category in snapshot.categories:
            self._bump_counter(counters, category.id, "CAT")
        for account in snapshot.accounts:
            self._bump_counter(counters, account.id, "ACC")

    @staticmethod
    def _bump_counter(counters: dict[str, int], value: str, prefix: str) -> None:
        if not value.startswith(prefix):
            return
        try:
            current = int(value[len(prefix):])
        except ValueError:
            return
        if current > counters.get(prefix, 0):
            counters[prefix] = current

    def _get_entity(self, title: str, record_id: str):
        if self._cache is not None:
            entity_list = self._entity_list_for_title(self._cache, title)
            if entity_list is not None:
                for entity in entity_list:
                    if entity.id == record_id:
                        return entity
        else:
            for entity in self._read_entities(title):
                if entity.id == record_id:
                    return entity
        raise KeyError(record_id)

    @staticmethod
    def _entity_list_for_title(snapshot: Snapshot, title: str):
        mapping = {
            "Transactions": snapshot.transactions,
            "Planned Transactions": snapshot.planned_transactions,
            "Budgets": snapshot.budgets,
            "Categories": snapshot.categories,
            "Accounts": snapshot.accounts,
        }
        return mapping.get(title)

    def _next_id(self, title: str, prefix: str) -> str:
        highest = self._id_counters.get(prefix, 0)
        next_value = highest + 1
        self._id_counters[prefix] = next_value
        return f"{prefix}{next_value:04d}"

    @staticmethod
    def _prefix_for_title(title: str) -> str:
        mapping = {
            "Transactions": "TX",
            "Planned Transactions": "PLN",
            "Budgets": "BDG",
            "Categories": "CAT",
            "Accounts": "ACC",
        }
        return mapping.get(title, "")

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
