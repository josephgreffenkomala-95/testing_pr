from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


STATUSES = ("planned", "confirmed", "completed", "cancelled")
KINDS = ("income", "expense")


@dataclass(frozen=True)
class Category:
    id: str
    name: str
    kind: str
    is_active: bool = True


@dataclass(frozen=True)
class Account:
    id: str
    name: str
    account_type: str
    currency: str
    current_balance: Decimal
    is_active: bool = True


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


@dataclass(frozen=True)
class PlannedTransaction:
    id: str
    entry_type: str
    status: str
    expected_date: Optional[str]
    amount: Decimal
    category_id: str
    account_id: str
    description: str
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""


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


@dataclass(frozen=True)
class Snapshot:
    transactions: list[Transaction]
    planned_transactions: list[PlannedTransaction]
    budgets: list[Budget]
    categories: list[Category]
    accounts: list[Account]
    settings: dict[str, str]
