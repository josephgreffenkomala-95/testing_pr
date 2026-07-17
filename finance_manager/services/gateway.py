from __future__ import annotations

from dataclasses import dataclass, fields, replace
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Protocol, TypeVar, runtime_checkable
from uuid import uuid4

from finance_manager.config.settings import AppConfig
from finance_manager.logic.calculations import account_balances
from finance_manager.models.entities import (
    ACCOUNT_TYPES,
    SCHEDULE_PRECISIONS,
    STATUSES,
    Account,
    Budget,
    Category,
    OfflineChange,
    PlanException,
    PlannedTransaction,
    RecurringPlan,
    Snapshot,
    SyncConflict,
    Transaction,
)


if TYPE_CHECKING:
    from finance_manager.services.local_store import EncryptedLocalStore


Clock = Callable[[], datetime]
RecordIdGenerator = Callable[[str], str]
Record = TypeVar("Record", Transaction, PlannedTransaction, Budget, Account, Category, RecurringPlan, PlanException)


def utc_now() -> datetime:
    return datetime.now(UTC)


def generate_record_id(prefix: str) -> str:
    return f"{prefix}-{uuid4()}"


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
    cleaned = value.strip().lower().replace("ewallet", "e-wallet")
    if cleaned not in valid:
        raise ValueError(f"{field} must be one of: {', '.join(valid)}")
    return cleaned


def _amount(value: str | Decimal, *, allow_negative: bool = False) -> Decimal:
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("Amount must be numeric.") from exc
    if not allow_negative and amount < 0:
        raise ValueError("Amount must be non-negative.")
    return amount.quantize(Decimal("0.01"))


def _date(value: str, *, allow_blank: bool = False) -> str | None:
    cleaned = value.strip()
    if not cleaned and allow_blank:
        return None
    try:
        return date.fromisoformat(cleaned).isoformat()
    except ValueError as exc:
        raise ValueError("Date must use YYYY-MM-DD.") from exc


def _month(value: str) -> str:
    cleaned = value.strip()
    try:
        datetime.strptime(cleaned, "%Y-%m")
    except ValueError as exc:
        raise ValueError("Month must use YYYY-MM.") from exc
    return cleaned


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
        self._snapshot = snapshot or Snapshot()

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
        entry_type = _choice(data["entry_type"], ("income", "expense"), "Type")
        account = self._account_by_name(data["account"], require_open=True)
        activity_date = self._activity_date(data["date"], account)
        category = self._ensure_category(data["category"], entry_type)
        activity = self._new_activity(
            entry_type,
            activity_date,
            _amount(data["amount"]),
            category.id,
            account.id,
            data.get("description", "").strip(),
            data.get("notes", "").strip(),
        )
        self._snapshot = replace(self._snapshot, transactions=[*self._snapshot.transactions, activity])
        return activity

    def add_transfer(self, data: dict[str, str]) -> Transaction:
        source = self._account_by_name(data["source_account"], require_open=True)
        destination = self._account_by_name(data["destination_account"], require_open=True)
        if source.id == destination.id:
            raise ValueError("Transfer Accounts must be different.")
        activity_date = self._activity_date(data["date"], source)
        if date.fromisoformat(activity_date) < date.fromisoformat(destination.opening_date):
            raise ValueError("Transfer date cannot be before an Account's Opening Date.")
        activity = self._new_activity(
            "transfer",
            activity_date,
            _amount(data["amount"]),
            "",
            source.id,
            data.get("description", "Transfer").strip(),
            data.get("notes", "").strip(),
            destination_account_id=destination.id,
        )
        self._snapshot = replace(self._snapshot, transactions=[*self._snapshot.transactions, activity])
        return activity

    def update_transaction(self, record_id: str, data: dict[str, str]) -> Transaction:
        current = self.get_transaction(record_id)
        if current.entry_type == "transfer":
            source = self._account_by_name(data.get("source_account", self._account_name(current.account_id)), True)
            destination = self._account_by_name(
                data.get("destination_account", self._account_name(current.destination_account_id)),
                True,
            )
            category_id = ""
        else:
            entry_type = _choice(data.get("entry_type", current.entry_type), ("income", "expense"), "Type")
            source = self._account_by_name(data.get("account", self._account_name(current.account_id)), True)
            destination = None
            category_id = self._ensure_category(
                data.get("category", self._category_name(current.category_id)),
                entry_type,
            ).id
        updated = replace(
            current,
            entry_type=current.entry_type if current.entry_type == "transfer" else entry_type,
            date=self._activity_date(data.get("date", current.date), source),
            amount=_amount(data.get("amount", str(current.amount))),
            category_id=category_id,
            account_id=source.id,
            destination_account_id=destination.id if destination else "",
            description=data.get("description", current.description).strip(),
            notes=data.get("notes", current.notes).strip(),
            updated_at=self._timestamp(),
            version=current.version + 1,
        )
        self._replace_transaction(updated)
        return updated

    def void_transaction(self, record_id: str, reason: str) -> Transaction:
        if not reason.strip():
            raise ValueError("A void reason is required.")
        current = self.get_transaction(record_id)
        if current.is_voided:
            return current
        updated = replace(
            current,
            voided_at=self._timestamp(),
            void_reason=reason.strip(),
            updated_at=self._timestamp(),
            version=current.version + 1,
        )
        self._replace_transaction(updated)
        return updated

    def delete_transaction(self, record_id: str) -> None:
        self.void_transaction(record_id, "Voided from Activity")

    def get_transaction(self, record_id: str) -> Transaction:
        return self._find(self._snapshot.transactions, record_id)

    def reconcile_account(self, account_id: str, observed_balance: Decimal, effective_date: str) -> Transaction:
        account = self._find(self._snapshot.accounts, account_id)
        activity_date = self._activity_date(effective_date, account)
        calculated = account_balances(self._snapshot, date.fromisoformat(activity_date))[account_id]
        difference = _amount(observed_balance, allow_negative=True) - calculated
        activity = self._new_activity(
            "adjustment",
            activity_date,
            difference,
            "",
            account_id,
            f"Reconciliation to {observed_balance:.2f}",
            "",
        )
        self._snapshot = replace(self._snapshot, transactions=[*self._snapshot.transactions, activity])
        return activity

    def add_planned_transaction(self, data: dict[str, str]) -> PlannedTransaction:
        entry_type = _choice(data["entry_type"], ("income", "expense", "transfer"), "Type")
        account = self._account_by_name(data.get("account") or data.get("source_account", ""), True)
        destination = None
        category = None
        if entry_type == "transfer":
            destination = self._account_by_name(data["destination_account"], True)
            if destination.id == account.id:
                raise ValueError("Transfer Accounts must be different.")
        else:
            category = self._ensure_category(data["category"], entry_type)
        precision = _choice(data.get("schedule_precision", "exact"), SCHEDULE_PRECISIONS, "Schedule precision")
        expected_date = _date(data.get("expected_date", ""), allow_blank=True)
        if precision == "month" and not data.get("scheduled_month", "").strip():
            raise ValueError("A Month-Only Plan requires a calendar month.")
        scheduled_month = _month(data["scheduled_month"]) if precision == "month" else ""
        if precision == "exact" and not expected_date:
            raise ValueError("An exact Plan requires a date.")
        if precision == "unscheduled":
            expected_date = None
        timestamp = self._timestamp()
        plan = PlannedTransaction(
            self._record_id_generator("PLN"),
            entry_type,
            _choice(data.get("status", "planned"), STATUSES, "Status"),
            expected_date,
            _amount(data["amount"]),
            category.id if category else "",
            account.id,
            data.get("description", "").strip(),
            data.get("notes", "").strip(),
            timestamp,
            timestamp,
            destination.id if destination else "",
            precision,
            scheduled_month,
        )
        self._snapshot = replace(
            self._snapshot,
            planned_transactions=[*self._snapshot.planned_transactions, plan],
        )
        return plan

    def update_planned_transaction(self, record_id: str, data: dict[str, str]) -> PlannedTransaction:
        current = self.get_planned_transaction(record_id)
        if current.status == "completed":
            raise ValueError("Completed Plans preserve their original intent.")
        replacement = self.add_planned_transaction(
            {
                "entry_type": data.get("entry_type", current.entry_type),
                "status": data.get("status", current.status),
                "schedule_precision": data.get("schedule_precision", current.schedule_precision),
                "expected_date": data.get("expected_date", current.expected_date or ""),
                "scheduled_month": data.get("scheduled_month", current.scheduled_month),
                "amount": data.get("amount", str(current.amount)),
                "category": data.get("category", self._category_name(current.category_id)),
                "account": data.get("account", self._account_name(current.account_id)),
                "source_account": data.get("source_account", self._account_name(current.account_id)),
                "destination_account": data.get(
                    "destination_account",
                    self._account_name(current.destination_account_id),
                ),
                "description": data.get("description", current.description),
                "notes": data.get("notes", current.notes),
            }
        )
        updated = replace(replacement, id=current.id, created_at=current.created_at, version=current.version + 1)
        self._snapshot = replace(
            self._snapshot,
            planned_transactions=[
                updated if item.id == current.id else item
                for item in self._snapshot.planned_transactions
                if item.id != replacement.id
            ],
        )
        return updated

    def delete_planned_transaction(self, record_id: str) -> None:
        current = self.get_planned_transaction(record_id)
        if current.status == "completed":
            return
        self._replace_plan(replace(current, status="cancelled", version=current.version + 1, updated_at=self._timestamp()))

    def get_planned_transaction(self, record_id: str) -> PlannedTransaction:
        return self._find(self._snapshot.planned_transactions, record_id)

    def complete_plan(self, record_id: str, actual: dict[str, str]) -> Transaction:
        plan = self.get_planned_transaction(record_id)
        if plan.completed_activity_id:
            return self.get_transaction(plan.completed_activity_id)
        if plan.entry_type == "transfer":
            activity = self.add_transfer(
                {
                    **actual,
                    "source_account": actual.get("source_account", self._account_name(plan.account_id)),
                    "destination_account": actual.get(
                        "destination_account",
                        self._account_name(plan.destination_account_id),
                    ),
                }
            )
        else:
            activity = self.add_transaction(
                {
                    **actual,
                    "entry_type": plan.entry_type,
                    "account": actual.get("account", self._account_name(plan.account_id)),
                    "category": actual.get("category", self._category_name(plan.category_id)),
                }
            )
        activity = replace(activity, linked_plan_id=plan.id)
        self._replace_transaction(activity)
        self._replace_plan(
            replace(
                plan,
                status="completed",
                completed_activity_id=activity.id,
                version=plan.version + 1,
                updated_at=self._timestamp(),
            )
        )
        return activity

    def plan_variance(self, record_id: str) -> dict[str, tuple[object, object]]:
        plan = self.get_planned_transaction(record_id)
        if not plan.completed_activity_id:
            return {}
        activity = self.get_transaction(plan.completed_activity_id)
        candidates = {
            "amount": (plan.amount, activity.amount),
            "date": (plan.expected_date, activity.date),
            "account": (plan.account_id, activity.account_id),
            "category": (plan.category_id, activity.category_id),
            "description": (plan.description, activity.description),
        }
        return {key: value for key, value in candidates.items() if value[0] != value[1]}

    def add_recurring_plan(self, data: dict[str, str]) -> RecurringPlan:
        account = self._account_by_name(data.get("account") or data.get("source_account", ""), True)
        entry_type = _choice(data["entry_type"], ("income", "expense", "transfer"), "Type")
        category = None if entry_type == "transfer" else self._ensure_category(data["category"], entry_type)
        destination = self._account_by_name(data["destination_account"], True) if entry_type == "transfer" else None
        timestamp = self._timestamp()
        rule = RecurringPlan(
            self._record_id_generator("REC"),
            entry_type,
            _choice(data.get("status", "planned"), ("planned", "confirmed", "cancelled"), "Status"),
            _choice(data["frequency"], ("weekly", "monthly", "yearly"), "Frequency"),
            _date(data["start_date"]) or "",
            _date(data.get("end_date", ""), allow_blank=True),
            _amount(data["amount"]),
            category.id if category else "",
            account.id,
            data.get("description", "").strip(),
            data.get("notes", "").strip(),
            destination.id if destination else "",
            created_at=timestamp,
            updated_at=timestamp,
        )
        self._snapshot = replace(self._snapshot, recurring_plans=[*self._snapshot.recurring_plans, rule])
        return rule

    def update_recurring_plan(self, record_id: str, data: dict[str, str]) -> RecurringPlan:
        current = self._find(self._snapshot.recurring_plans, record_id)
        if any(
            exception.recurring_plan_id == record_id and exception.action == "completed"
            for exception in self._snapshot.plan_exceptions
        ):
            raise ValueError("An entire recurring series cannot change after an occurrence is completed.")
        entry_type = _choice(data.get("entry_type", current.entry_type), ("income", "expense", "transfer"), "Type")
        account = self._account_by_name(data.get("account") or data.get("source_account", self._account_name(current.account_id)), True)
        category = None if entry_type == "transfer" else self._ensure_category(
            data.get("category", self._category_name(current.category_id)),
            entry_type,
        )
        destination = None
        if entry_type == "transfer":
            destination = self._account_by_name(
                data.get("destination_account", self._account_name(current.destination_account_id)),
                True,
            )
        updated = replace(
            current,
            entry_type=entry_type,
            status=_choice(data.get("status", current.status), ("planned", "confirmed", "cancelled"), "Status"),
            frequency=_choice(data.get("frequency", current.frequency), ("weekly", "monthly", "yearly"), "Frequency"),
            start_date=_date(data.get("start_date", current.start_date)) or "",
            end_date=_date(data.get("end_date", current.end_date or ""), allow_blank=True),
            amount=_amount(data.get("amount", str(current.amount))),
            category_id=category.id if category else "",
            account_id=account.id,
            destination_account_id=destination.id if destination else "",
            description=data.get("description", current.description).strip(),
            notes=data.get("notes", current.notes).strip(),
            version=current.version + 1,
            updated_at=self._timestamp(),
        )
        self._snapshot = replace(
            self._snapshot,
            recurring_plans=[updated if item.id == record_id else item for item in self._snapshot.recurring_plans],
        )
        return updated

    def get_recurring_plan(self, record_id: str) -> RecurringPlan:
        return self._find(self._snapshot.recurring_plans, record_id)

    def add_plan_exception(self, data: dict[str, str]) -> PlanException:
        exception = PlanException(
            self._record_id_generator("EXC"),
            data["recurring_plan_id"],
            _date(data["occurrence_date"]) or "",
            _choice(data["action"], ("changed", "cancelled", "completed"), "Action"),
            _date(data.get("replacement_date", ""), allow_blank=True),
            _amount(data["replacement_amount"]) if data.get("replacement_amount") else None,
            data.get("completed_activity_id", ""),
            created_at=self._timestamp(),
            updated_at=self._timestamp(),
        )
        self._snapshot = replace(self._snapshot, plan_exceptions=[*self._snapshot.plan_exceptions, exception])
        return exception

    def complete_occurrence(
        self,
        recurring_plan_id: str,
        occurrence_date: str,
        actual: dict[str, str],
    ) -> Transaction:
        existing = next(
            (
                item
                for item in self._snapshot.plan_exceptions
                if item.recurring_plan_id == recurring_plan_id
                and item.occurrence_date == occurrence_date
                and item.completed_activity_id
            ),
            None,
        )
        if existing:
            return self.get_transaction(existing.completed_activity_id)
        rule = self.get_recurring_plan(recurring_plan_id)
        if rule.entry_type == "transfer":
            activity = self.add_transfer(
                {
                    **actual,
                    "source_account": actual.get("source_account", self._account_name(rule.account_id)),
                    "destination_account": actual.get(
                        "destination_account",
                        self._account_name(rule.destination_account_id),
                    ),
                }
            )
        else:
            activity = self.add_transaction(
                {
                    **actual,
                    "entry_type": rule.entry_type,
                    "account": actual.get("account", self._account_name(rule.account_id)),
                    "category": actual.get("category", self._category_name(rule.category_id)),
                }
            )
        self.add_plan_exception(
            {
                "recurring_plan_id": recurring_plan_id,
                "occurrence_date": occurrence_date,
                "action": "completed",
                "completed_activity_id": activity.id,
            }
        )
        return activity

    def add_budget(self, data: dict[str, str]) -> Budget:
        category = self._ensure_category(data["category"], data["entry_type"])
        month = _month(data["month"])
        if any(item.month == month and item.category_id == category.id for item in self._snapshot.budgets):
            raise ValueError(f"A Budget or Income Target already exists for {category.name} in {month}.")
        timestamp = self._timestamp()
        budget = Budget(
            self._record_id_generator("BDG"),
            month,
            category.id,
            category.kind,
            _amount(data["amount"]),
            data.get("notes", "").strip(),
            timestamp,
            timestamp,
        )
        self._snapshot = replace(self._snapshot, budgets=[*self._snapshot.budgets, budget])
        return budget

    def update_budget(self, record_id: str, data: dict[str, str]) -> Budget:
        current = self._find(self._snapshot.budgets, record_id)
        category = self._ensure_category(data["category"], data["entry_type"])
        month = _month(data["month"])
        if any(
            item.id != record_id and item.month == month and item.category_id == category.id
            for item in self._snapshot.budgets
        ):
            raise ValueError(f"A Budget or Income Target already exists for {category.name} in {month}.")
        updated = replace(
            current,
            month=month,
            category_id=category.id,
            entry_type=category.kind,
            amount=_amount(data["amount"]),
            notes=data.get("notes", "").strip(),
            updated_at=self._timestamp(),
            version=current.version + 1,
        )
        self._snapshot = replace(
            self._snapshot,
            budgets=[updated if item.id == record_id else item for item in self._snapshot.budgets],
        )
        return updated

    def delete_budget(self, record_id: str) -> None:
        self._find(self._snapshot.budgets, record_id)
        self._snapshot = replace(self._snapshot, budgets=[item for item in self._snapshot.budgets if item.id != record_id])

    def copy_budgets(self, source_month: str, target_month: str) -> list[Budget]:
        source = [item for item in self._snapshot.budgets if item.month == _month(source_month)]
        copied = []
        for item in source:
            category = self._find(self._snapshot.categories, item.category_id)
            copied.append(
                self.add_budget(
                    {
                        "month": _month(target_month),
                        "entry_type": item.entry_type,
                        "category": category.name,
                        "amount": str(item.amount),
                        "notes": item.notes,
                    }
                )
            )
        return copied

    def add_account(self, data: dict[str, str]) -> Account:
        name = data["name"].strip()
        if not name:
            raise ValueError("Account name is required.")
        if any(item.name.casefold() == name.casefold() for item in self._snapshot.accounts):
            raise ValueError(f"Account '{name}' already exists.")
        currency = data.get("currency", self._snapshot.settings.get("base_currency", "IDR")).strip().upper()
        base_currency = self._snapshot.settings.get("base_currency", currency)
        if currency != base_currency:
            raise ValueError(f"Every Account must use Base Currency {base_currency}.")
        timestamp = self._timestamp()
        account = Account(
            self._record_id_generator("ACC"),
            name,
            _choice(data.get("account_type", "cash"), ACCOUNT_TYPES, "Account type"),
            currency,
            _amount(data.get("opening_balance", data.get("current_balance", "0")), allow_negative=True),
            True,
            _date(data.get("opening_date", self.now().date().isoformat())) or "",
            1,
            timestamp,
            timestamp,
        )
        self._snapshot = replace(self._snapshot, accounts=[*self._snapshot.accounts, account])
        return account

    def update_account(self, record_id: str, data: dict[str, str]) -> Account:
        current = self._find(self._snapshot.accounts, record_id)
        name = data.get("name", current.name).strip()
        if any(item.id != record_id and item.name.casefold() == name.casefold() for item in self._snapshot.accounts):
            raise ValueError(f"Account '{name}' already exists.")
        updated = replace(
            current,
            name=name,
            account_type=_choice(data.get("account_type", current.account_type), ACCOUNT_TYPES, "Account type"),
            updated_at=self._timestamp(),
            version=current.version + 1,
        )
        self._snapshot = replace(
            self._snapshot,
            accounts=[updated if item.id == record_id else item for item in self._snapshot.accounts],
        )
        return updated

    def close_account(self, record_id: str) -> Account:
        account = self._find(self._snapshot.accounts, record_id)
        if not account.is_active:
            return account
        if account_balances(self._snapshot)[record_id] != Decimal("0.00"):
            raise ValueError("Account Current Balance must be zero before closure.")
        if any(
            plan.status in {"planned", "confirmed"}
            and record_id in {plan.account_id, plan.destination_account_id}
            for plan in self._snapshot.planned_transactions
        ) or any(
            rule.status in {"planned", "confirmed"}
            and record_id in {rule.account_id, rule.destination_account_id}
            for rule in self._snapshot.recurring_plans
        ):
            raise ValueError("Move or cancel active Plans before closing this Account.")
        closed = replace(account, is_active=False, version=account.version + 1, updated_at=self._timestamp())
        self._snapshot = replace(
            self._snapshot,
            accounts=[closed if item.id == record_id else item for item in self._snapshot.accounts],
        )
        return closed

    def delete_account(self, record_id: str) -> None:
        self.close_account(record_id)

    def rename_category(self, record_id: str, name: str) -> Category:
        category = self._find(self._snapshot.categories, record_id)
        renamed = replace(category, name=name.strip(), version=category.version + 1, updated_at=self._timestamp())
        self._replace_category(renamed)
        return renamed

    def add_category(self, name: str, kind: str) -> Category:
        return self._ensure_category(name, kind)

    def archive_category(self, record_id: str) -> Category:
        category = self._find(self._snapshot.categories, record_id)
        archived = replace(category, is_active=False, version=category.version + 1, updated_at=self._timestamp())
        self._replace_category(archived)
        return archived

    def seed_dummy_data(self) -> int:
        return 0

    def _new_activity(
        self,
        entry_type: str,
        activity_date: str,
        amount: Decimal,
        category_id: str,
        account_id: str,
        description: str,
        notes: str,
        *,
        destination_account_id: str = "",
    ) -> Transaction:
        timestamp = self._timestamp()
        return Transaction(
            self._record_id_generator("ACT"),
            entry_type,
            activity_date,
            amount,
            category_id,
            account_id,
            description,
            notes,
            timestamp,
            timestamp,
            destination_account_id,
        )

    def _activity_date(self, value: str, account: Account) -> str:
        activity_date = _date(value) or ""
        if date.fromisoformat(activity_date) < date.fromisoformat(account.opening_date):
            raise ValueError("Activity date cannot be before the Account's Opening Date.")
        if date.fromisoformat(activity_date) > self.now().date():
            raise ValueError("Completed Activity cannot use a future date.")
        return activity_date

    def _ensure_category(self, name: str, entry_type: str) -> Category:
        cleaned_name = name.strip()
        cleaned_type = _choice(entry_type, ("income", "expense"), "Type")
        for category in self._snapshot.categories:
            if category.name.casefold() != cleaned_name.casefold():
                continue
            if category.kind != cleaned_type:
                raise ValueError(
                    f"Category '{category.name}' is {category.kind}; choose a {cleaned_type} Category or create another name."
                )
            if category.kind == cleaned_type:
                if not category.is_active:
                    raise ValueError("Archived Categories cannot be used for new entries.")
                return category
        if not cleaned_name:
            raise ValueError("Category is required.")
        timestamp = self._timestamp()
        category = Category(
            self._record_id_generator("CAT"),
            cleaned_name,
            cleaned_type,
            True,
            1,
            timestamp,
            timestamp,
        )
        self._snapshot = replace(self._snapshot, categories=[*self._snapshot.categories, category])
        return category

    def _account_by_name(self, name: str, require_open: bool = False) -> Account:
        for account in self._snapshot.accounts:
            if account.name.casefold() == name.strip().casefold():
                if require_open and not account.is_active:
                    raise ValueError(f"Account '{account.name}' is closed.")
                return account
        raise ValueError(f"Account '{name.strip()}' does not exist. Create it in Accounts first.")

    def _account_name(self, account_id: str) -> str:
        if not account_id:
            return ""
        return self._find(self._snapshot.accounts, account_id).name

    def _category_name(self, category_id: str) -> str:
        if not category_id:
            return ""
        return self._find(self._snapshot.categories, category_id).name

    def _timestamp(self) -> str:
        return self.now().astimezone(UTC).isoformat().replace("+00:00", "Z")

    def _replace_transaction(self, updated: Transaction) -> None:
        self._snapshot = replace(
            self._snapshot,
            transactions=[updated if item.id == updated.id else item for item in self._snapshot.transactions],
        )

    def _replace_plan(self, updated: PlannedTransaction) -> None:
        self._snapshot = replace(
            self._snapshot,
            planned_transactions=[
                updated if item.id == updated.id else item for item in self._snapshot.planned_transactions
            ],
        )

    def _replace_category(self, updated: Category) -> None:
        self._snapshot = replace(
            self._snapshot,
            categories=[updated if item.id == updated.id else item for item in self._snapshot.categories],
        )

    @staticmethod
    def _find(items: list[Record], record_id: str) -> Record:
        for item in items:
            if item.id == record_id:
                return item
        raise KeyError(record_id)


RECORD_ATTRIBUTES = {
    "activity": "transactions",
    "plan": "planned_transactions",
    "budget": "budgets",
    "account": "accounts",
    "category": "categories",
    "recurring_plan": "recurring_plans",
    "plan_exception": "plan_exceptions",
}


class OfflineFinanceGateway(InMemoryFinanceGateway):
    def __init__(
        self,
        *,
        local_store: EncryptedLocalStore,
        snapshot: Snapshot | None = None,
        config: AppConfig | None = None,
        clock: Clock = utc_now,
        record_id_generator: RecordIdGenerator = generate_record_id,
        remote: InMemoryFinanceGateway | None = None,
    ) -> None:
        self.local_store = local_store
        self.remote = remote
        self.online = remote is not None
        self.offline_changes: list[OfflineChange]
        self.last_synced_at: str | None
        if snapshot is None and local_store.exists:
            state = local_store.load()
            snapshot = state.snapshot
            self.offline_changes = state.changes
            self.last_synced_at = state.last_synced_at
        else:
            self.offline_changes = []
            self.last_synced_at = None
            if snapshot is None and remote is not None:
                snapshot = remote.load_snapshot()
        super().__init__(
            snapshot=snapshot,
            config=config,
            clock=clock,
            record_id_generator=record_id_generator,
        )
        self.sync_status = "Pending changes" if self.offline_changes else "Offline"
        self.conflicts: list[SyncConflict] = []
        self._suppress_queue = False
        if remote is not None:
            if self.offline_changes:
                self.synchronize(remote)
            else:
                self.sync_status = "Synced"
                self.last_synced_at = self._timestamp()
                self._persist_local()

    def add_account(self, data: dict[str, str]) -> Account:
        account = super().add_account(data)
        return self._queued("add", "account", account, 0)

    def update_account(self, record_id: str, data: dict[str, str]) -> Account:
        base_version = self._find(self._snapshot.accounts, record_id).version
        account = super().update_account(record_id, data)
        return self._queued("update", "account", account, base_version)

    def close_account(self, record_id: str) -> Account:
        base_version = self._find(self._snapshot.accounts, record_id).version
        account = super().close_account(record_id)
        return self._queued("close", "account", account, base_version)

    def add_transaction(self, data: dict[str, str]) -> Transaction:
        activity = super().add_transaction(data)
        return self._queued("add", "activity", activity, 0)

    def add_transfer(self, data: dict[str, str]) -> Transaction:
        activity = super().add_transfer(data)
        return self._queued("add", "activity", activity, 0)

    def update_transaction(self, record_id: str, data: dict[str, str]) -> Transaction:
        base_version = self.get_transaction(record_id).version
        activity = super().update_transaction(record_id, data)
        return self._queued("update", "activity", activity, base_version)

    def void_transaction(self, record_id: str, reason: str) -> Transaction:
        base_version = self.get_transaction(record_id).version
        activity = super().void_transaction(record_id, reason)
        return self._queued("void", "activity", activity, base_version)

    def reconcile_account(self, account_id: str, observed_balance: Decimal, effective_date: str) -> Transaction:
        activity = super().reconcile_account(account_id, observed_balance, effective_date)
        return self._queued("add", "activity", activity, 0)

    def add_planned_transaction(self, data: dict[str, str]) -> PlannedTransaction:
        plan = super().add_planned_transaction(data)
        return self._queued("add", "plan", plan, 0)

    def update_planned_transaction(self, record_id: str, data: dict[str, str]) -> PlannedTransaction:
        base_version = self.get_planned_transaction(record_id).version
        plan = super().update_planned_transaction(record_id, data)
        return self._queued("update", "plan", plan, base_version)

    def delete_planned_transaction(self, record_id: str) -> None:
        base_version = self.get_planned_transaction(record_id).version
        super().delete_planned_transaction(record_id)
        self._queued("cancel", "plan", self.get_planned_transaction(record_id), base_version)

    def complete_plan(self, record_id: str, actual: dict[str, str]) -> Transaction:
        plan = self.get_planned_transaction(record_id)
        if plan.completed_activity_id:
            return self.get_transaction(plan.completed_activity_id)
        self._suppress_queue = True
        try:
            activity = super().complete_plan(record_id, actual)
        finally:
            self._suppress_queue = False
        pending_activity = replace(activity, pending_sync=True)
        pending_plan = replace(self.get_planned_transaction(record_id), pending_sync=True)
        self._set_record("activity", pending_activity)
        self._set_record("plan", pending_plan)
        self._append_change(
            "complete",
            "completion",
            record_id,
            plan.version,
            {"plan_id": record_id, "activity_id": activity.id},
            atomic_group=self._record_id_generator("ATOMIC"),
        )
        return pending_activity

    def add_budget(self, data: dict[str, str]) -> Budget:
        budget = super().add_budget(data)
        return self._queued("add", "budget", budget, 0)

    def update_budget(self, record_id: str, data: dict[str, str]) -> Budget:
        base_version = self._find(self._snapshot.budgets, record_id).version
        budget = super().update_budget(record_id, data)
        return self._queued("update", "budget", budget, base_version)

    def add_recurring_plan(self, data: dict[str, str]) -> RecurringPlan:
        rule = super().add_recurring_plan(data)
        return self._queued("add", "recurring_plan", rule, 0)

    def update_recurring_plan(self, record_id: str, data: dict[str, str]) -> RecurringPlan:
        base_version = self.get_recurring_plan(record_id).version
        rule = super().update_recurring_plan(record_id, data)
        return self._queued("update", "recurring_plan", rule, base_version)

    def add_plan_exception(self, data: dict[str, str]) -> PlanException:
        exception = super().add_plan_exception(data)
        return self._queued("add", "plan_exception", exception, 0)

    def complete_occurrence(
        self,
        recurring_plan_id: str,
        occurrence_date: str,
        actual: dict[str, str],
    ) -> Transaction:
        self._suppress_queue = True
        try:
            activity = super().complete_occurrence(recurring_plan_id, occurrence_date, actual)
        finally:
            self._suppress_queue = False
        exception = next(
            item
            for item in self._snapshot.plan_exceptions
            if item.recurring_plan_id == recurring_plan_id
            and item.occurrence_date == occurrence_date
            and item.completed_activity_id == activity.id
        )
        pending_activity = replace(activity, pending_sync=True)
        pending_exception = replace(exception, pending_sync=True)
        self._set_record("activity", pending_activity)
        self._set_record("plan_exception", pending_exception)
        self._append_change(
            "complete",
            "completion",
            exception.id,
            0,
            {
                "recurring_plan_id": recurring_plan_id,
                "exception_id": exception.id,
                "activity_id": activity.id,
            },
            atomic_group=self._record_id_generator("ATOMIC"),
        )
        return pending_activity

    def rename_category(self, record_id: str, name: str) -> Category:
        base_version = self._find(self._snapshot.categories, record_id).version
        category = super().rename_category(record_id, name)
        return self._queued("update", "category", category, base_version)

    def add_category(self, name: str, kind: str) -> Category:
        category = super().add_category(name, kind)
        return self._queued("add", "category", category, 0)

    def archive_category(self, record_id: str) -> Category:
        base_version = self._find(self._snapshot.categories, record_id).version
        category = super().archive_category(record_id)
        return self._queued("archive", "category", category, base_version)

    def synchronize(self, remote: InMemoryFinanceGateway | None = None) -> list[SyncConflict]:
        if remote is not None:
            self.remote = remote
            self.online = True
        selected_remote = remote or self.remote
        if selected_remote is None or not self.online:
            self.sync_status = "Pending changes" if self.offline_changes else "Offline"
            self._persist_local()
            return []
        self.sync_status = "Syncing"
        remaining: list[OfflineChange] = []
        conflicts: list[SyncConflict] = []
        for change in self.offline_changes:
            if change.record_type == "completion":
                self._sync_completion(change, selected_remote)
                continue
            local_record = self._record(change.record_type, change.record_id)
            if local_record is None:
                raise ValueError(f"Queued {change.record_type} '{change.record_id}' is missing locally.")
            remote_record = self._record(change.record_type, change.record_id, snapshot=selected_remote._snapshot)
            if change.operation == "add" and remote_record is None:
                synced = replace(local_record, pending_sync=False)
                self._set_record(change.record_type, synced, gateway=selected_remote)
                self._set_record(change.record_type, synced)
                continue
            if remote_record is None:
                conflict = SyncConflict(
                    change.record_type,
                    change.record_id,
                    {"deleted": ("local record", "deleted from Finance Sheet")},
                )
                conflicts.append(conflict)
                remaining.append(change)
                continue
            if remote_record.version != change.base_version:
                conflict_fields = self._conflicting_fields(local_record, remote_record)
                if conflict_fields:
                    conflicts.append(SyncConflict(change.record_type, change.record_id, conflict_fields))
                    remaining.append(change)
                    continue
            synced = replace(local_record, pending_sync=False)
            self._set_record(change.record_type, synced, gateway=selected_remote)
            self._set_record(change.record_type, synced)
        selected_remote._snapshot = replace(
            selected_remote._snapshot,
            categories=self._merge_records(selected_remote._snapshot.categories, self._snapshot.categories),
            settings={**selected_remote._snapshot.settings, **self._snapshot.settings},
        )
        queued_keys = {(change.record_type, change.record_id) for change in remaining}
        for record_type in ("activity", "plan"):
            attribute = RECORD_ATTRIBUTES[record_type]
            for local_record in getattr(self._snapshot, attribute):
                if local_record.pending_sync or (record_type, local_record.id) in queued_keys:
                    continue
                if self._record(record_type, local_record.id, snapshot=selected_remote._snapshot) is not None:
                    continue
                conflict = SyncConflict(
                    record_type,
                    local_record.id,
                    {"deleted": ("restore historical record", "deleted from Finance Sheet")},
                )
                conflicts.append(conflict)
                sequence = remaining[-1].sequence + 1 if remaining else 1
                remaining.append(
                    OfflineChange(sequence, "restore_deleted", record_type, local_record.id, local_record.version, {})
                )
                queued_keys.add((record_type, local_record.id))
        self.offline_changes = remaining
        self.conflicts = conflicts
        if conflicts:
            self.sync_status = "Conflict"
        elif remaining:
            self.sync_status = "Pending changes"
        else:
            self.sync_status = "Synced"
            self.last_synced_at = self._timestamp()
        self._persist_local()
        return conflicts

    def restore_deleted(self, conflict: SyncConflict, remote: InMemoryFinanceGateway) -> None:
        local_record = self._record(conflict.record_type, conflict.record_id)
        if local_record is None or "deleted" not in conflict.fields:
            raise ValueError("This conflict is not a deleted historical record.")
        if conflict.record_type == "activity":
            restored = replace(
                local_record,
                voided_at=self._timestamp(),
                void_reason="Restored after direct Finance Sheet deletion",
                version=local_record.version + 1,
                updated_at=self._timestamp(),
                pending_sync=False,
            )
        elif conflict.record_type == "plan":
            restored = replace(
                local_record,
                status="cancelled",
                version=local_record.version + 1,
                updated_at=self._timestamp(),
                pending_sync=False,
            )
        else:
            raise ValueError("Only deleted Activity and Plans can be restored as history.")
        self._set_record(conflict.record_type, restored, gateway=remote)
        self._set_record(conflict.record_type, restored)
        self.offline_changes = [
            change
            for change in self.offline_changes
            if not (change.record_type == conflict.record_type and change.record_id == conflict.record_id)
        ]
        self.conflicts = [item for item in self.conflicts if item != conflict]
        self.sync_status = "Synced" if not self.offline_changes and not self.conflicts else "Pending changes"
        self.last_synced_at = self._timestamp()
        self._persist_local()

    def sync_now(self) -> list[SyncConflict]:
        return self.synchronize()

    def set_online(self, online: bool, remote: InMemoryFinanceGateway | None = None) -> list[SyncConflict]:
        self.online = online
        if remote is not None:
            self.remote = remote
        return self.synchronize() if online else []

    def resolve_conflict(
        self,
        conflict: SyncConflict,
        choices: dict[str, object],
        remote: InMemoryFinanceGateway,
    ) -> None:
        local_record = self._record(conflict.record_type, conflict.record_id)
        remote_record = self._record(conflict.record_type, conflict.record_id, snapshot=remote._snapshot)
        if local_record is None or remote_record is None:
            raise ValueError("Deleted records must be restored as Voided or Cancelled history.")
        updates: dict[str, Any] = {}
        for field_name in conflict.fields:
            choice = choices.get(field_name, "local")
            if choice == "local":
                updates[field_name] = getattr(local_record, field_name)
            elif choice == "sheet":
                updates[field_name] = getattr(remote_record, field_name)
            else:
                updates[field_name] = self._coerce_value(getattr(local_record, field_name), choice)
        resolved = replace(
            remote_record,
            **updates,
            version=max(local_record.version, remote_record.version) + 1,
            updated_at=self._timestamp(),
            pending_sync=False,
        )
        self._set_record(conflict.record_type, resolved, gateway=remote)
        self._set_record(conflict.record_type, resolved)
        self.offline_changes = [
            change
            for change in self.offline_changes
            if not (change.record_type == conflict.record_type and change.record_id == conflict.record_id)
        ]
        self.conflicts = [item for item in self.conflicts if item != conflict]
        self.sync_status = "Synced" if not self.offline_changes and not self.conflicts else "Pending changes"
        if self.sync_status == "Synced":
            self.last_synced_at = self._timestamp()
        self._persist_local()

    def _queued(self, operation: str, record_type: str, record: Record, base_version: int) -> Any:
        if self._suppress_queue:
            return record
        pending = replace(record, pending_sync=True)
        self._set_record(record_type, pending)
        self._append_change(operation, record_type, record.id, base_version, {})
        return pending

    def _append_change(
        self,
        operation: str,
        record_type: str,
        record_id: str,
        base_version: int,
        payload: dict[str, str],
        *,
        atomic_group: str = "",
    ) -> None:
        sequence = self.offline_changes[-1].sequence + 1 if self.offline_changes else 1
        self.offline_changes.append(
            OfflineChange(sequence, operation, record_type, record_id, base_version, payload, atomic_group)
        )
        self.sync_status = "Pending changes"
        self._persist_local()
        if self.online and self.remote is not None:
            self.synchronize(self.remote)

    def _persist_local(self) -> None:
        self.local_store.save(self._snapshot, self.offline_changes, self.last_synced_at)

    def _record(
        self,
        record_type: str,
        record_id: str,
        *,
        snapshot: Snapshot | None = None,
    ) -> Any | None:
        attribute = RECORD_ATTRIBUTES[record_type]
        for record in getattr(snapshot or self._snapshot, attribute):
            if record.id == record_id:
                return record
        return None

    def _set_record(
        self,
        record_type: str,
        record: Any,
        *,
        gateway: InMemoryFinanceGateway | None = None,
    ) -> None:
        target = gateway or self
        attribute = RECORD_ATTRIBUTES[record_type]
        records = getattr(target._snapshot, attribute)
        updated = [record if item.id == record.id else item for item in records]
        if not any(item.id == record.id for item in records):
            updated.append(record)
        target._snapshot = self._snapshot_with_records(target._snapshot, attribute, updated)

    def _sync_completion(self, change: OfflineChange, remote: InMemoryFinanceGateway) -> None:
        activity = self._record("activity", change.payload["activity_id"])
        if "plan_id" in change.payload:
            plan = self._record("plan", change.payload["plan_id"])
            if plan is None or activity is None:
                raise ValueError("Atomic Plan completion is missing its linked records.")
            self._set_record("plan", replace(plan, pending_sync=False), gateway=remote)
            self._set_record("plan", replace(plan, pending_sync=False))
        else:
            exception = self._record("plan_exception", change.payload["exception_id"])
            if exception is None or activity is None:
                raise ValueError("Atomic occurrence completion is missing its linked records.")
            self._set_record("plan_exception", replace(exception, pending_sync=False), gateway=remote)
            self._set_record("plan_exception", replace(exception, pending_sync=False))
        if activity is None:
            raise ValueError("Atomic Plan completion is missing its linked records.")
        self._set_record("activity", replace(activity, pending_sync=False), gateway=remote)
        self._set_record("activity", replace(activity, pending_sync=False))

    @staticmethod
    def _conflicting_fields(local_record: Any, remote_record: Any) -> dict[str, tuple[str, str]]:
        ignored = {"id", "version", "created_at", "updated_at", "pending_sync"}
        return {
            item.name: (str(getattr(local_record, item.name)), str(getattr(remote_record, item.name)))
            for item in fields(local_record)
            if item.name not in ignored and getattr(local_record, item.name) != getattr(remote_record, item.name)
        }

    @staticmethod
    def _coerce_value(example: object, value: object) -> object:
        if isinstance(example, Decimal):
            return Decimal(str(value))
        if isinstance(example, bool):
            return str(value).casefold() in {"true", "yes", "1"}
        if isinstance(example, int):
            return int(str(value))
        return value

    @staticmethod
    def _merge_records(remote: list[Any], local: list[Any]) -> list[Any]:
        merged = {item.id: item for item in remote}
        for item in local:
            merged.setdefault(item.id, replace(item, pending_sync=False))
        return list(merged.values())

    @staticmethod
    def _snapshot_with_records(snapshot: Snapshot, attribute: str, records: list[Any]) -> Snapshot:
        if attribute == "transactions":
            return replace(snapshot, transactions=records)
        if attribute == "planned_transactions":
            return replace(snapshot, planned_transactions=records)
        if attribute == "budgets":
            return replace(snapshot, budgets=records)
        if attribute == "accounts":
            return replace(snapshot, accounts=records)
        if attribute == "categories":
            return replace(snapshot, categories=records)
        if attribute == "recurring_plans":
            return replace(snapshot, recurring_plans=records)
        if attribute == "plan_exceptions":
            return replace(snapshot, plan_exceptions=records)
        raise ValueError(f"Unknown record collection: {attribute}")
