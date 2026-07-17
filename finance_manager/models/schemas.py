from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal
from typing import Any, Callable, Iterable, cast

from .entities import Account, Budget, Category, PlannedTransaction, Transaction


SHEET_HEADERS = {
    "Transactions": [
        "id",
        "entry_type",
        "date",
        "amount",
        "category_id",
        "account_id",
        "description",
        "notes",
        "created_at",
        "updated_at",
    ],
    "Planned Transactions": [
        "id",
        "entry_type",
        "status",
        "expected_date",
        "amount",
        "category_id",
        "account_id",
        "description",
        "notes",
        "created_at",
        "updated_at",
    ],
    "Budgets": [
        "id",
        "month",
        "category_id",
        "entry_type",
        "amount",
        "notes",
        "created_at",
        "updated_at",
    ],
    "Categories": ["id", "name", "kind", "is_active"],
    "Accounts": ["id", "name", "account_type", "currency", "current_balance", "is_active"],
    "Settings": ["key", "value"],
}


def _decimal(value: str) -> Decimal:
    return Decimal(value or "0")


def _bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def row_to_transaction(row: dict[str, str]) -> Transaction:
    return Transaction(
        id=row["id"],
        entry_type=row["entry_type"],
        date=row["date"],
        amount=_decimal(row["amount"]),
        category_id=row["category_id"],
        account_id=row["account_id"],
        description=row["description"],
        notes=row.get("notes", ""),
        created_at=row.get("created_at", ""),
        updated_at=row.get("updated_at", ""),
    )


def row_to_planned_transaction(row: dict[str, str]) -> PlannedTransaction:
    return PlannedTransaction(
        id=row["id"],
        entry_type=row["entry_type"],
        status=row["status"],
        expected_date=row.get("expected_date") or None,
        amount=_decimal(row["amount"]),
        category_id=row["category_id"],
        account_id=row["account_id"],
        description=row["description"],
        notes=row.get("notes", ""),
        created_at=row.get("created_at", ""),
        updated_at=row.get("updated_at", ""),
    )


def row_to_budget(row: dict[str, str]) -> Budget:
    return Budget(
        id=row["id"],
        month=row["month"],
        category_id=row["category_id"],
        entry_type=row["entry_type"],
        amount=_decimal(row["amount"]),
        notes=row.get("notes", ""),
        created_at=row.get("created_at", ""),
        updated_at=row.get("updated_at", ""),
    )


def row_to_category(row: dict[str, str]) -> Category:
    return Category(
        id=row["id"],
        name=row["name"],
        kind=row["kind"],
        is_active=_bool(row.get("is_active", "true")),
    )


def row_to_account(row: dict[str, str]) -> Account:
    return Account(
        id=row["id"],
        name=row["name"],
        account_type=row["account_type"],
        currency=row.get("currency", "IDR") or "IDR",
        current_balance=_decimal(row.get("current_balance", "0")),
        is_active=_bool(row.get("is_active", "true")),
    )


def entity_to_row(entity: object, headers: Iterable[str]) -> list[str]:
    raw = asdict(cast(Any, entity))
    values = []
    for header in headers:
        value = raw.get(header, "")
        if isinstance(value, Decimal):
            value = f"{value:.2f}"
        elif value is None:
            value = ""
        elif isinstance(value, bool):
            value = "true" if value else "false"
        values.append(str(value))
    return values


ROW_PARSERS: dict[str, Callable[[dict[str, str]], object]] = {
    "Transactions": row_to_transaction,
    "Planned Transactions": row_to_planned_transaction,
    "Budgets": row_to_budget,
    "Categories": row_to_category,
    "Accounts": row_to_account,
}
