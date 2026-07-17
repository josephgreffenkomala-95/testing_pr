from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


STATUSES = ("planned", "confirmed", "completed", "cancelled")
KINDS = ("income", "expense", "transfer", "adjustment")
ACCOUNT_TYPES = ("cash", "bank", "e-wallet")
SCHEDULE_PRECISIONS = ("exact", "month", "unscheduled")


@dataclass(frozen=True)
class Category:
    id: str
    name: str
    kind: str
    is_active: bool = True
    version: int = 1
    created_at: str = ""
    updated_at: str = ""
    pending_sync: bool = False


@dataclass(frozen=True)
class Account:
    id: str
    name: str
    account_type: str
    currency: str
    current_balance: Decimal
    is_active: bool = True
    opening_date: str = "1970-01-01"
    version: int = 1
    created_at: str = ""
    updated_at: str = ""
    pending_sync: bool = False

    @property
    def opening_balance(self) -> Decimal:
        return self.current_balance

    @property
    def is_open(self) -> bool:
        return self.is_active


@dataclass(frozen=True)
class Transaction:
    id: str
    entry_type: str
    date: str
    amount: Decimal
    category_id: str
    account_id: str
    description: str
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""
    destination_account_id: str = ""
    voided_at: str = ""
    void_reason: str = ""
    linked_plan_id: str = ""
    version: int = 1
    pending_sync: bool = False

    @property
    def is_voided(self) -> bool:
        return bool(self.voided_at)


@dataclass(frozen=True)
class PlannedTransaction:
    id: str
    entry_type: str
    status: str
    expected_date: str | None
    amount: Decimal
    category_id: str
    account_id: str
    description: str
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""
    destination_account_id: str = ""
    schedule_precision: str = "exact"
    scheduled_month: str = ""
    completed_activity_id: str = ""
    version: int = 1
    pending_sync: bool = False


@dataclass(frozen=True)
class RecurringPlan:
    id: str
    entry_type: str
    status: str
    frequency: str
    start_date: str
    end_date: str | None
    amount: Decimal
    category_id: str
    account_id: str
    description: str
    notes: str = ""
    destination_account_id: str = ""
    version: int = 1
    created_at: str = ""
    updated_at: str = ""
    pending_sync: bool = False


@dataclass(frozen=True)
class PlanException:
    id: str
    recurring_plan_id: str
    occurrence_date: str
    action: str
    replacement_date: str | None = None
    replacement_amount: Decimal | None = None
    completed_activity_id: str = ""
    version: int = 1
    created_at: str = ""
    updated_at: str = ""
    pending_sync: bool = False


@dataclass(frozen=True)
class PlanOccurrence:
    recurring_plan_id: str
    date: date
    amount: Decimal
    entry_type: str
    account_id: str
    category_id: str
    description: str
    destination_account_id: str = ""


@dataclass(frozen=True)
class Budget:
    id: str
    month: str
    category_id: str
    entry_type: str
    amount: Decimal
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""
    version: int = 1
    pending_sync: bool = False


@dataclass(frozen=True)
class OfflineChange:
    sequence: int
    operation: str
    record_type: str
    record_id: str
    base_version: int
    payload: dict[str, str]
    atomic_group: str = ""


@dataclass(frozen=True)
class SyncConflict:
    record_type: str
    record_id: str
    fields: dict[str, tuple[str, str]]


@dataclass(frozen=True)
class Snapshot:
    transactions: list[Transaction] = field(default_factory=list)
    planned_transactions: list[PlannedTransaction] = field(default_factory=list)
    budgets: list[Budget] = field(default_factory=list)
    categories: list[Category] = field(default_factory=list)
    accounts: list[Account] = field(default_factory=list)
    settings: dict[str, str] = field(default_factory=dict)
    recurring_plans: list[RecurringPlan] = field(default_factory=list)
    plan_exceptions: list[PlanException] = field(default_factory=list)
