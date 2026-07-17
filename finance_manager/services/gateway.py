from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Protocol, TypeVar, runtime_checkable
from uuid import uuid4

from finance_manager.config.settings import AppConfig
from finance_manager.models.entities import Account, Budget, Category, PlannedTransaction, Snapshot, Transaction


Clock = Callable[[], datetime]
RecordIdGenerator = Callable[[str], str]
Record = TypeVar("Record", Transaction, PlannedTransaction, Budget, Account)


def utc_now() -> datetime:
    return datetime.now(UTC)


def generate_record_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


@dataclass(frozen=True)
class SheetRef:
    spreadsheet_id: str
    title: str


@runtime_checkable
class FinanceGateway(Protocol):
    config: AppConfig
    requires_authentication: bool

    def now(self) -> datetime: ...

    def bootstrap(self) -> str: ...

    def spreadsheet_url(self) -> str: ...

    def list_spreadsheets(self) -> list[SheetRef]: ...

    def use_spreadsheet(self, spreadsheet_id: str, title: str = "") -> str: ...

    def clear_cache(self) -> None: ...

    def load_snapshot(self) -> Snapshot: ...

    def add_transaction(self, data: dict[str, str]) -> Transaction: ...

    def update_transaction(self, record_id: str, data: dict[str, str]) -> Transaction: ...

    def delete_transaction(self, record_id: str) -> None: ...

    def get_transaction(self, record_id: str) -> Transaction: ...

    def add_planned_transaction(self, data: dict[str, str]) -> PlannedTransaction: ...

    def update_planned_transaction(self, record_id: str, data: dict[str, str]) -> PlannedTransaction: ...

    def delete_planned_transaction(self, record_id: str) -> None: ...

    def get_planned_transaction(self, record_id: str) -> PlannedTransaction: ...

    def add_budget(self, data: dict[str, str]) -> Budget: ...

    def update_budget(self, record_id: str, data: dict[str, str]) -> Budget: ...

    def delete_budget(self, record_id: str) -> None: ...

    def add_account(self, data: dict[str, str]) -> Account: ...

    def update_account(self, record_id: str, data: dict[str, str]) -> Account: ...

    def delete_account(self, record_id: str) -> None: ...

    def seed_dummy_data(self) -> int: ...


def _memory_config() -> AppConfig:
    config_dir = Path(".finance-manager-memory")
    return AppConfig(
        config_dir=config_dir,
        config_path=config_dir / "config.json",
        oauth_client_secret_path=config_dir / "oauth-client.json",
        oauth_token_path=config_dir / "oauth-token.json",
        spreadsheet_title="In-memory Finance Sheet",
        spreadsheet_id="in-memory",
    )


def _choice(value: str, valid: tuple[str, ...], field: str) -> str:
    cleaned = value.strip().lower()
    if cleaned not in valid:
        raise ValueError(f"{field} must be one of: {', '.join(valid)}")
    return cleaned


def _amount(value: str) -> Decimal:
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("Amount must be numeric.") from exc
    if amount < 0:
        raise ValueError("Amount must be non-negative.")
    return amount.quantize(Decimal("0.01"))


def _date(value: str, *, allow_blank: bool = False) -> str | None:
    cleaned = value.strip()
    if not cleaned and allow_blank:
        return None
    try:
        return datetime.strptime(cleaned, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("Date must use YYYY-MM-DD.") from exc


def _month(value: str) -> str:
    try:
        return datetime.strptime(value.strip(), "%Y-%m").strftime("%Y-%m")
    except ValueError as exc:
        raise ValueError("Month must use YYYY-MM.") from exc


class InMemoryFinanceGateway:
    requires_authentication = False

    def __init__(
        self,
        snapshot: Snapshot | None = None,
        *,
        config: AppConfig | None = None,
        clock: Clock = utc_now,
        record_id_generator: RecordIdGenerator = generate_record_id,
    ) -> None:
        self.config = config or _memory_config()
        self._clock = clock
        self._record_id_generator = record_id_generator
        self._snapshot = snapshot or Snapshot([], [], [], [], [], {})

    def now(self) -> datetime:
        return self._clock()

    def bootstrap(self) -> str:
        return self.config.spreadsheet_id or "in-memory"

    def spreadsheet_url(self) -> str:
        return ""

    def list_spreadsheets(self) -> list[SheetRef]:
        return [SheetRef(self.bootstrap(), self.config.spreadsheet_title)]

    def use_spreadsheet(self, spreadsheet_id: str, title: str = "") -> str:
        self.config = replace(
            self.config,
            spreadsheet_id=spreadsheet_id,
            spreadsheet_title=title or self.config.spreadsheet_title,
        )
        return spreadsheet_id

    def clear_cache(self) -> None:
        return None

    def load_snapshot(self) -> Snapshot:
        return self._snapshot

    def add_transaction(self, data: dict[str, str]) -> Transaction:
        category = self._ensure_category(data["category"], data["entry_type"])
        account = self._ensure_account(data["account"])
        timestamp = self._timestamp()
        transaction = Transaction(
            id=self._record_id_generator("TX"),
            entry_type=_choice(data["entry_type"], ("income", "expense"), "Type"),
            date=_date(data["date"]) or "",
            amount=_amount(data["amount"]),
            category_id=category.id,
            account_id=account.id,
            description=data["description"].strip(),
            notes=data.get("notes", "").strip(),
            created_at=timestamp,
            updated_at=timestamp,
        )
        self._snapshot = replace(self._snapshot, transactions=[*self._snapshot.transactions, transaction])
        return transaction

    def update_transaction(self, record_id: str, data: dict[str, str]) -> Transaction:
        current = self.get_transaction(record_id)
        category = self._ensure_category(data["category"], data["entry_type"])
        account = self._ensure_account(data["account"])
        updated = replace(
            current,
            entry_type=_choice(data["entry_type"], ("income", "expense"), "Type"),
            date=_date(data["date"]) or "",
            amount=_amount(data["amount"]),
            category_id=category.id,
            account_id=account.id,
            description=data["description"].strip(),
            notes=data.get("notes", "").strip(),
            updated_at=self._timestamp(),
        )
        self._snapshot = replace(
            self._snapshot,
            transactions=[updated if item.id == record_id else item for item in self._snapshot.transactions],
        )
        return updated

    def delete_transaction(self, record_id: str) -> None:
        self.get_transaction(record_id)
        self._snapshot = replace(
            self._snapshot,
            transactions=[item for item in self._snapshot.transactions if item.id != record_id],
        )

    def get_transaction(self, record_id: str) -> Transaction:
        return self._find(self._snapshot.transactions, record_id)

    def add_planned_transaction(self, data: dict[str, str]) -> PlannedTransaction:
        category = self._ensure_category(data["category"], data["entry_type"])
        account = self._ensure_account(data["account"])
        timestamp = self._timestamp()
        plan = PlannedTransaction(
            id=self._record_id_generator("PLN"),
            entry_type=_choice(data["entry_type"], ("income", "expense"), "Type"),
            status=_choice(data["status"], ("planned", "confirmed", "completed", "cancelled"), "Status"),
            expected_date=_date(data.get("expected_date", ""), allow_blank=True),
            amount=_amount(data["amount"]),
            category_id=category.id,
            account_id=account.id,
            description=data["description"].strip(),
            notes=data.get("notes", "").strip(),
            created_at=timestamp,
            updated_at=timestamp,
        )
        self._snapshot = replace(self._snapshot, planned_transactions=[*self._snapshot.planned_transactions, plan])
        return plan

    def update_planned_transaction(self, record_id: str, data: dict[str, str]) -> PlannedTransaction:
        current = self.get_planned_transaction(record_id)
        category = self._ensure_category(data["category"], data["entry_type"])
        account = self._ensure_account(data["account"])
        updated = replace(
            current,
            entry_type=_choice(data["entry_type"], ("income", "expense"), "Type"),
            status=_choice(data["status"], ("planned", "confirmed", "completed", "cancelled"), "Status"),
            expected_date=_date(data.get("expected_date", ""), allow_blank=True),
            amount=_amount(data["amount"]),
            category_id=category.id,
            account_id=account.id,
            description=data["description"].strip(),
            notes=data.get("notes", "").strip(),
            updated_at=self._timestamp(),
        )
        self._snapshot = replace(
            self._snapshot,
            planned_transactions=[
                updated if item.id == record_id else item for item in self._snapshot.planned_transactions
            ],
        )
        return updated

    def delete_planned_transaction(self, record_id: str) -> None:
        self.get_planned_transaction(record_id)
        self._snapshot = replace(
            self._snapshot,
            planned_transactions=[item for item in self._snapshot.planned_transactions if item.id != record_id],
        )

    def get_planned_transaction(self, record_id: str) -> PlannedTransaction:
        return self._find(self._snapshot.planned_transactions, record_id)

    def add_budget(self, data: dict[str, str]) -> Budget:
        category = self._ensure_category(data["category"], data["entry_type"])
        timestamp = self._timestamp()
        budget = Budget(
            id=self._record_id_generator("BDG"),
            month=_month(data["month"]),
            category_id=category.id,
            entry_type=_choice(data["entry_type"], ("income", "expense"), "Type"),
            amount=_amount(data["amount"]),
            notes=data.get("notes", "").strip(),
            created_at=timestamp,
            updated_at=timestamp,
        )
        self._snapshot = replace(self._snapshot, budgets=[*self._snapshot.budgets, budget])
        return budget

    def update_budget(self, record_id: str, data: dict[str, str]) -> Budget:
        current = self._find(self._snapshot.budgets, record_id)
        category = self._ensure_category(data["category"], data["entry_type"])
        updated = replace(
            current,
            month=_month(data["month"]),
            category_id=category.id,
            entry_type=_choice(data["entry_type"], ("income", "expense"), "Type"),
            amount=_amount(data["amount"]),
            notes=data.get("notes", "").strip(),
            updated_at=self._timestamp(),
        )
        self._snapshot = replace(
            self._snapshot,
            budgets=[updated if item.id == record_id else item for item in self._snapshot.budgets],
        )
        return updated

    def delete_budget(self, record_id: str) -> None:
        self._find(self._snapshot.budgets, record_id)
        self._snapshot = replace(
            self._snapshot,
            budgets=[item for item in self._snapshot.budgets if item.id != record_id],
        )

    def add_account(self, data: dict[str, str]) -> Account:
        name = data["name"].strip()
        if not name:
            raise ValueError("Account name is required.")
        if any(account.name.casefold() == name.casefold() for account in self._snapshot.accounts):
            raise ValueError(f"Account '{name}' already exists.")
        account = Account(
            id=self._record_id_generator("ACC"),
            name=name,
            account_type=data.get("account_type", "cash").strip().lower() or "cash",
            currency=data.get("currency", "IDR").strip().upper() or "IDR",
            current_balance=_amount(data.get("current_balance", "0")),
        )
        self._snapshot = replace(self._snapshot, accounts=[*self._snapshot.accounts, account])
        return account

    def update_account(self, record_id: str, data: dict[str, str]) -> Account:
        current = self._find(self._snapshot.accounts, record_id)
        name = data["name"].strip() or current.name
        if any(
            account.id != record_id and account.name.casefold() == name.casefold()
            for account in self._snapshot.accounts
        ):
            raise ValueError(f"Account '{name}' already exists.")
        updated = replace(
            current,
            name=name,
            account_type=data.get("account_type", current.account_type).strip().lower() or current.account_type,
            currency=data.get("currency", current.currency).strip().upper() or current.currency,
            current_balance=_amount(data.get("current_balance", str(current.current_balance))),
        )
        self._snapshot = replace(
            self._snapshot,
            accounts=[updated if item.id == record_id else item for item in self._snapshot.accounts],
        )
        return updated

    def delete_account(self, record_id: str) -> None:
        self._find(self._snapshot.accounts, record_id)
        self._snapshot = replace(
            self._snapshot,
            accounts=[item for item in self._snapshot.accounts if item.id != record_id],
        )

    def seed_dummy_data(self) -> int:
        return 0

    def _ensure_category(self, name: str, entry_type: str) -> Category:
        cleaned_name = name.strip()
        cleaned_type = _choice(entry_type, ("income", "expense"), "Type")
        for category in self._snapshot.categories:
            if category.name.casefold() == cleaned_name.casefold() and category.kind == cleaned_type:
                return category
        category = Category(self._record_id_generator("CAT"), cleaned_name, cleaned_type)
        self._snapshot = replace(self._snapshot, categories=[*self._snapshot.categories, category])
        return category

    def _ensure_account(self, name: str) -> Account:
        cleaned_name = name.strip()
        for account in self._snapshot.accounts:
            if account.name.casefold() == cleaned_name.casefold():
                return account
        account = Account(self._record_id_generator("ACC"), cleaned_name, "cash", "IDR", Decimal("0.00"))
        self._snapshot = replace(self._snapshot, accounts=[*self._snapshot.accounts, account])
        return account

    def _timestamp(self) -> str:
        return self.now().astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _find(items: list[Record], record_id: str) -> Record:
        for item in items:
            if getattr(item, "id", None) == record_id:
                return item
        raise KeyError(record_id)
