from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal
from typing import Any, Callable, Iterable, cast

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


SHEET_HEADERS = {
    "Activity": [
        "id",
        "entry_type",
        "date",
        "amount",
        "category_id",
        "account_id",
        "destination_account_id",
        "description",
        "notes",
        "voided_at",
        "void_reason",
        "linked_plan_id",
        "version",
        "created_at",
        "updated_at",
    ],
    "Plans": [
        "id",
        "entry_type",
        "status",
        "schedule_precision",
        "expected_date",
        "scheduled_month",
        "amount",
        "category_id",
        "account_id",
        "destination_account_id",
        "description",
        "notes",
        "completed_activity_id",
        "version",
        "created_at",
        "updated_at",
    ],
    "Recurring Plans": [
        "id",
        "entry_type",
        "status",
        "frequency",
        "start_date",
        "end_date",
        "amount",
        "category_id",
        "account_id",
        "destination_account_id",
        "description",
        "notes",
        "version",
        "created_at",
        "updated_at",
    ],
    "Plan Exceptions": [
        "id",
        "recurring_plan_id",
        "occurrence_date",
        "action",
        "replacement_date",
        "replacement_amount",
        "completed_activity_id",
        "version",
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
        "version",
        "created_at",
        "updated_at",
    ],
    "Categories": ["id", "name", "kind", "is_active", "version", "created_at", "updated_at"],
    "Accounts": [
        "id",
        "name",
        "account_type",
        "currency",
        "opening_date",
        "current_balance",
        "is_active",
        "version",
        "created_at",
        "updated_at",
    ],
    "Settings": ["key", "value"],
}


def _decimal(value: object) -> Decimal:
    return Decimal(str(value or "0"))


def _optional_decimal(value: object) -> Decimal | None:
    return None if value in {None, ""} else _decimal(value)


def _bool(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _int(value: object) -> int:
    return int(str(value or 1))


def row_to_transaction(row: dict[str, Any]) -> Transaction:
    return Transaction(
        id=str(row["id"]),
        entry_type=str(row["entry_type"]),
        date=str(row["date"]),
        amount=_decimal(row["amount"]),
        category_id=str(row.get("category_id", "")),
        account_id=str(row["account_id"]),
        description=str(row.get("description", "")),
        notes=str(row.get("notes", "")),
        created_at=str(row.get("created_at", "")),
        updated_at=str(row.get("updated_at", "")),
        destination_account_id=str(row.get("destination_account_id", "")),
        voided_at=str(row.get("voided_at", "")),
        void_reason=str(row.get("void_reason", "")),
        linked_plan_id=str(row.get("linked_plan_id", "")),
        version=_int(row.get("version", 1)),
        pending_sync=_bool(row.get("pending_sync", False)),
    )


def row_to_planned_transaction(row: dict[str, Any]) -> PlannedTransaction:
    return PlannedTransaction(
        id=str(row["id"]),
        entry_type=str(row["entry_type"]),
        status=str(row["status"]),
        expected_date=str(row.get("expected_date") or "") or None,
        amount=_decimal(row["amount"]),
        category_id=str(row.get("category_id", "")),
        account_id=str(row["account_id"]),
        description=str(row.get("description", "")),
        notes=str(row.get("notes", "")),
        created_at=str(row.get("created_at", "")),
        updated_at=str(row.get("updated_at", "")),
        destination_account_id=str(row.get("destination_account_id", "")),
        schedule_precision=str(row.get("schedule_precision", "exact")),
        scheduled_month=str(row.get("scheduled_month", "")),
        completed_activity_id=str(row.get("completed_activity_id", "")),
        version=_int(row.get("version", 1)),
        pending_sync=_bool(row.get("pending_sync", False)),
    )


def row_to_recurring_plan(row: dict[str, Any]) -> RecurringPlan:
    return RecurringPlan(
        id=str(row["id"]),
        entry_type=str(row["entry_type"]),
        status=str(row["status"]),
        frequency=str(row["frequency"]),
        start_date=str(row["start_date"]),
        end_date=str(row.get("end_date") or "") or None,
        amount=_decimal(row["amount"]),
        category_id=str(row.get("category_id", "")),
        account_id=str(row["account_id"]),
        description=str(row.get("description", "")),
        notes=str(row.get("notes", "")),
        destination_account_id=str(row.get("destination_account_id", "")),
        version=_int(row.get("version", 1)),
        created_at=str(row.get("created_at", "")),
        updated_at=str(row.get("updated_at", "")),
        pending_sync=_bool(row.get("pending_sync", False)),
    )


def row_to_plan_exception(row: dict[str, Any]) -> PlanException:
    return PlanException(
        id=str(row["id"]),
        recurring_plan_id=str(row["recurring_plan_id"]),
        occurrence_date=str(row["occurrence_date"]),
        action=str(row["action"]),
        replacement_date=str(row.get("replacement_date") or "") or None,
        replacement_amount=_optional_decimal(row.get("replacement_amount")),
        completed_activity_id=str(row.get("completed_activity_id", "")),
        version=_int(row.get("version", 1)),
        created_at=str(row.get("created_at", "")),
        updated_at=str(row.get("updated_at", "")),
        pending_sync=_bool(row.get("pending_sync", False)),
    )


def row_to_budget(row: dict[str, Any]) -> Budget:
    return Budget(
        id=str(row["id"]),
        month=str(row["month"]),
        category_id=str(row["category_id"]),
        entry_type=str(row["entry_type"]),
        amount=_decimal(row["amount"]),
        notes=str(row.get("notes", "")),
        created_at=str(row.get("created_at", "")),
        updated_at=str(row.get("updated_at", "")),
        version=_int(row.get("version", 1)),
        pending_sync=_bool(row.get("pending_sync", False)),
    )


def row_to_category(row: dict[str, Any]) -> Category:
    return Category(
        id=str(row["id"]),
        name=str(row["name"]),
        kind=str(row["kind"]),
        is_active=_bool(row.get("is_active", True)),
        version=_int(row.get("version", 1)),
        created_at=str(row.get("created_at", "")),
        updated_at=str(row.get("updated_at", "")),
        pending_sync=_bool(row.get("pending_sync", False)),
    )


def row_to_account(row: dict[str, Any]) -> Account:
    return Account(
        id=str(row["id"]),
        name=str(row["name"]),
        account_type=str(row["account_type"]),
        currency=str(row.get("currency", "IDR") or "IDR"),
        current_balance=_decimal(row.get("current_balance", row.get("opening_balance", "0"))),
        is_active=_bool(row.get("is_active", True)),
        opening_date=str(row.get("opening_date", "1970-01-01")),
        version=_int(row.get("version", 1)),
        created_at=str(row.get("created_at", "")),
        updated_at=str(row.get("updated_at", "")),
        pending_sync=_bool(row.get("pending_sync", False)),
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


ROW_PARSERS: dict[str, Callable[[dict[str, Any]], object]] = {
    "Activity": row_to_transaction,
    "Plans": row_to_planned_transaction,
    "Recurring Plans": row_to_recurring_plan,
    "Plan Exceptions": row_to_plan_exception,
    "Budgets": row_to_budget,
    "Categories": row_to_category,
    "Accounts": row_to_account,
}


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


def snapshot_to_dict(snapshot: Snapshot) -> dict[str, Any]:
    return _json_value(asdict(snapshot))


def snapshot_from_dict(data: dict[str, Any]) -> Snapshot:
    return Snapshot(
        transactions=[row_to_transaction(item) for item in data.get("transactions", [])],
        planned_transactions=[row_to_planned_transaction(item) for item in data.get("planned_transactions", [])],
        budgets=[row_to_budget(item) for item in data.get("budgets", [])],
        categories=[row_to_category(item) for item in data.get("categories", [])],
        accounts=[row_to_account(item) for item in data.get("accounts", [])],
        settings={str(key): str(value) for key, value in data.get("settings", {}).items()},
        recurring_plans=[row_to_recurring_plan(item) for item in data.get("recurring_plans", [])],
        plan_exceptions=[row_to_plan_exception(item) for item in data.get("plan_exceptions", [])],
    )
