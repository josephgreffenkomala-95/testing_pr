from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from finance_manager.models.entities import Account, Budget, Category, PlannedTransaction, Snapshot, Transaction


def _month_key(value: str) -> str:
    return value[:7]


@dataclass(frozen=True)
class BudgetUsage:
    month: str
    category_name: str
    entry_type: str
    budgeted: Decimal
    actual: Decimal
    planned: Decimal

    @property
    def remaining(self) -> Decimal:
        return self.budgeted - self.actual

    @property
    def projected_remaining(self) -> Decimal:
        return self.budgeted - self.actual - self.planned

    @property
    def is_overspent(self) -> bool:
        return self.actual > self.budgeted

    @property
    def is_projected_overspent(self) -> bool:
        return self.actual + self.planned > self.budgeted


@dataclass(frozen=True)
class ProjectionPoint:
    label: str
    balance: Decimal
    change: Decimal


def month_budget_report(snapshot: Snapshot, month: str) -> list[BudgetUsage]:
    categories = {category.id: category for category in snapshot.categories}
    actual_by_key: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal("0"))
    planned_by_key: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal("0"))

    for item in snapshot.transactions:
        if _month_key(item.date) != month:
            continue
        actual_by_key[(item.category_id, item.entry_type)] += item.amount

    for item in snapshot.planned_transactions:
        if item.status not in {"planned", "confirmed"}:
            continue
        if item.expected_date and _month_key(item.expected_date) != month:
            continue
        planned_by_key[(item.category_id, item.entry_type)] += item.amount

    rows: list[BudgetUsage] = []
    for budget in snapshot.budgets:
        if budget.month != month:
            continue
        category = categories.get(budget.category_id, Category(budget.category_id, budget.category_id, budget.entry_type))
        key = (budget.category_id, budget.entry_type)
        rows.append(
            BudgetUsage(
                month=month,
                category_name=category.name,
                entry_type=budget.entry_type,
                budgeted=budget.amount,
                actual=actual_by_key[key],
                planned=planned_by_key[key],
            )
        )
    return sorted(rows, key=lambda row: (row.entry_type, row.category_name.lower()))


def total_balance(accounts: list[Account]) -> Decimal:
    return sum((account.current_balance for account in accounts), Decimal("0"))


def projection(snapshot: Snapshot, start_on: date | None = None) -> tuple[list[ProjectionPoint], list[ProjectionPoint]]:
    start = start_on or date.today()
    balance = total_balance(snapshot.accounts)
    daily_points: list[ProjectionPoint] = [ProjectionPoint(label=start.isoformat(), balance=balance, change=Decimal("0"))]

    future_items = sorted(
        (
            item
            for item in snapshot.planned_transactions
            if item.status in {"planned", "confirmed"} and item.expected_date
        ),
        key=lambda item: item.expected_date or "",
    )

    monthly_change: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for item in future_items:
        amount = item.amount if item.entry_type == "income" else -item.amount
        balance += amount
        daily_points.append(
            ProjectionPoint(
                label=item.expected_date or "unscheduled",
                balance=balance,
                change=amount,
            )
        )
        monthly_change[_month_key(item.expected_date or start.isoformat())] += amount

    monthly_points: list[ProjectionPoint] = []
    running = total_balance(snapshot.accounts)
    for month in sorted(monthly_change):
        running += monthly_change[month]
        monthly_points.append(ProjectionPoint(label=month, balance=running, change=monthly_change[month]))

    return daily_points, monthly_points


def current_month() -> str:
    return datetime.now().strftime("%Y-%m")
