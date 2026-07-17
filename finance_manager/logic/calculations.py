from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from finance_manager.models.entities import (
    Account,
    Category,
    PlanException,
    PlanOccurrence,
    PlannedTransaction,
    RecurringPlan,
    Snapshot,
)


ZERO = Decimal("0.00")


def _month_key(value: str) -> str:
    return value[:7]


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


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
        if self.entry_type == "income":
            return self.actual < self.budgeted
        return self.actual > self.budgeted

    @property
    def is_projected_overspent(self) -> bool:
        if self.entry_type == "income":
            return self.actual + self.planned < self.budgeted
        return self.actual + self.planned > self.budgeted


@dataclass(frozen=True)
class ProjectionPoint:
    label: str
    balance: Decimal
    change: Decimal


@dataclass(frozen=True)
class ProjectionEvent:
    date: date
    label: str
    amount: Decimal
    account_id: str
    destination_account_id: str = ""


@dataclass(frozen=True)
class CashShortfall:
    date: date
    balance: Decimal
    account_id: str | None
    contributing_plan_ids: tuple[str, ...]


@dataclass(frozen=True)
class ProjectionSummary:
    current: Decimal
    expected: Decimal
    confirmed: Decimal
    low: Decimal
    high: Decimal
    budget_safe: Decimal
    per_account: dict[str, Decimal]
    events: tuple[ProjectionEvent, ...]
    shortfall: CashShortfall | None


def account_balances(snapshot: Snapshot, as_of: date | None = None) -> dict[str, Decimal]:
    balances = {account.id: account.opening_balance for account in snapshot.accounts}
    opening_dates = {account.id: date.fromisoformat(account.opening_date) for account in snapshot.accounts}
    for activity in sorted(snapshot.transactions, key=lambda item: (item.date, item.created_at, item.id)):
        activity_date = date.fromisoformat(activity.date)
        if activity.is_voided or (as_of is not None and activity_date > as_of):
            continue
        if activity.account_id and activity_date >= opening_dates.get(activity.account_id, date.min):
            if activity.entry_type == "income":
                balances[activity.account_id] += activity.amount
            elif activity.entry_type in {"expense", "transfer"}:
                balances[activity.account_id] -= activity.amount
            elif activity.entry_type == "adjustment":
                balances[activity.account_id] += activity.amount
        if activity.entry_type == "transfer" and activity.destination_account_id:
            balances[activity.destination_account_id] += activity.amount
    return {account_id: _money(balance) for account_id, balance in balances.items()}


def total_balance(accounts: list[Account] | Snapshot) -> Decimal:
    if isinstance(accounts, Snapshot):
        return _money(sum(account_balances(accounts).values(), ZERO))
    return _money(sum((account.current_balance for account in accounts), ZERO))


def month_budget_report(snapshot: Snapshot, month: str) -> list[BudgetUsage]:
    categories = {category.id: category for category in snapshot.categories}
    actual_by_key: dict[tuple[str, str], Decimal] = defaultdict(lambda: ZERO)
    planned_by_key: dict[tuple[str, str], Decimal] = defaultdict(lambda: ZERO)
    for activity in snapshot.transactions:
        if activity.is_voided or activity.entry_type not in {"income", "expense"} or _month_key(activity.date) != month:
            continue
        actual_by_key[(activity.category_id, activity.entry_type)] += activity.amount
    for plan in snapshot.planned_transactions:
        if plan.status not in {"planned", "confirmed"} or plan.schedule_precision == "unscheduled":
            continue
        plan_month = plan.scheduled_month if plan.schedule_precision == "month" else _month_key(plan.expected_date or "")
        if plan_month == month and plan.entry_type in {"income", "expense"}:
            planned_by_key[(plan.category_id, plan.entry_type)] += plan.amount
    rows = []
    for budget in snapshot.budgets:
        if budget.month != month:
            continue
        category = categories.get(budget.category_id, Category(budget.category_id, budget.category_id, budget.entry_type))
        key = (budget.category_id, budget.entry_type)
        rows.append(
            BudgetUsage(
                month,
                category.name,
                budget.entry_type,
                budget.amount,
                actual_by_key[key],
                planned_by_key[key],
            )
        )
    return sorted(rows, key=lambda row: (row.entry_type, row.category_name.casefold()))


def _next_occurrence(current: date, frequency: str, requested_day: int) -> date:
    if frequency == "weekly":
        return current + timedelta(days=7)
    if frequency == "yearly":
        year = current.year + 1
        day = min(requested_day, calendar.monthrange(year, current.month)[1])
        return date(year, current.month, day)
    year = current.year + (1 if current.month == 12 else 0)
    month = 1 if current.month == 12 else current.month + 1
    day = min(requested_day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def expand_recurring_plan(
    rule: RecurringPlan,
    horizon: date,
    exceptions: list[PlanException] | None = None,
) -> list[PlanOccurrence]:
    if rule.frequency not in {"weekly", "monthly", "yearly"}:
        raise ValueError("Frequency must be weekly, monthly, or yearly.")
    current = date.fromisoformat(rule.start_date)
    requested_day = current.day
    end = date.fromisoformat(rule.end_date) if rule.end_date else horizon
    exception_by_date = {
        item.occurrence_date: item
        for item in (exceptions or [])
        if item.recurring_plan_id == rule.id
    }
    occurrences = []
    while current <= min(end, horizon):
        exception = exception_by_date.get(current.isoformat())
        if exception is None or exception.action != "cancelled":
            occurrence_date = date.fromisoformat(exception.replacement_date) if exception and exception.replacement_date else current
            amount = exception.replacement_amount if exception and exception.replacement_amount is not None else rule.amount
            occurrences.append(
                PlanOccurrence(
                    rule.id,
                    occurrence_date,
                    amount,
                    rule.entry_type,
                    rule.account_id,
                    rule.category_id,
                    rule.description,
                    rule.destination_account_id,
                )
            )
        current = _next_occurrence(current, rule.frequency, requested_day)
    return occurrences


def _plan_date(plan: PlannedTransaction, target: date, today: date) -> date | None:
    if plan.schedule_precision == "unscheduled":
        return None
    if plan.schedule_precision == "month":
        month = plan.scheduled_month
        year, month_number = (int(part) for part in month.split("-"))
        month_end = date(year, month_number, calendar.monthrange(year, month_number)[1])
        if target.strftime("%Y-%m") == month:
            return target
        return today if month_end < today else month_end
    planned_date = date.fromisoformat(plan.expected_date or "")
    return today if planned_date < today else planned_date


def _signed_amount(entry_type: str, amount: Decimal) -> Decimal:
    if entry_type == "income":
        return amount
    if entry_type == "expense":
        return -amount
    return ZERO


def budget_safe_balance(snapshot: Snapshot, expected: Decimal, month: str) -> Decimal:
    reserve = ZERO
    for usage in month_budget_report(snapshot, month):
        if usage.entry_type != "expense":
            continue
        reserve += max(usage.budgeted - usage.actual - usage.planned, ZERO)
    return _money(expected - reserve)


def projection_summary(snapshot: Snapshot, target: date, *, today: date | None = None) -> ProjectionSummary:
    current_date = today or date.today()
    current_by_account = account_balances(snapshot, as_of=min(target, current_date))
    current = _money(sum(current_by_account.values(), ZERO))
    if target < current_date:
        return ProjectionSummary(current, current, current, current, current, current, current_by_account, (), None)
    expected = current
    confirmed = current
    low = current
    high = current
    per_account = dict(current_by_account)
    events: list[ProjectionEvent] = []
    shortfall = None
    active_plans: list[tuple[str, PlannedTransaction, date]] = []
    for plan in snapshot.planned_transactions:
        if plan.status not in {"planned", "confirmed"}:
            continue
        event_date = _plan_date(plan, target, current_date)
        if event_date is None or event_date > target:
            continue
        active_plans.append((plan.id, plan, event_date))
    for rule in snapshot.recurring_plans:
        if rule.status not in {"planned", "confirmed"}:
            continue
        for occurrence in expand_recurring_plan(rule, target, snapshot.plan_exceptions):
            plan = PlannedTransaction(
                f"{rule.id}:{occurrence.date.isoformat()}",
                occurrence.entry_type,
                rule.status,
                occurrence.date.isoformat(),
                occurrence.amount,
                occurrence.category_id,
                occurrence.account_id,
                occurrence.description,
                destination_account_id=occurrence.destination_account_id,
            )
            active_plans.append((plan.id, plan, max(occurrence.date, current_date)))
    for plan_id, plan, event_date in sorted(active_plans, key=lambda item: (item[2], item[0])):
        change = _signed_amount(plan.entry_type, plan.amount)
        expected += change
        if plan.status == "confirmed":
            confirmed += change
        if plan.schedule_precision == "month" and event_date.month == target.month and event_date.year == target.year:
            if plan.entry_type == "expense":
                low += change
            elif plan.entry_type == "income":
                high += change
        else:
            low += change
            high += change
        if plan.entry_type == "transfer":
            per_account[plan.account_id] = per_account.get(plan.account_id, ZERO) - plan.amount
            per_account[plan.destination_account_id] = per_account.get(plan.destination_account_id, ZERO) + plan.amount
        else:
            per_account[plan.account_id] = per_account.get(plan.account_id, ZERO) + change
        events.append(ProjectionEvent(event_date, plan.description, change, plan.account_id, plan.destination_account_id))
        if shortfall is None:
            for account_id, balance in per_account.items():
                if balance < ZERO:
                    shortfall = CashShortfall(event_date, _money(balance), account_id, (plan_id,))
                    break
            if shortfall is None and expected < ZERO:
                shortfall = CashShortfall(event_date, _money(expected), None, (plan_id,))
    month = target.strftime("%Y-%m")
    return ProjectionSummary(
        current,
        _money(expected),
        _money(confirmed),
        _money(low),
        _money(high),
        budget_safe_balance(snapshot, expected, month),
        {key: _money(value) for key, value in per_account.items()},
        tuple(events),
        shortfall,
    )


def projection(snapshot: Snapshot, start_on: date | None = None) -> tuple[list[ProjectionPoint], list[ProjectionPoint]]:
    start = start_on or date.today()
    balance = total_balance(snapshot)
    daily_points = [ProjectionPoint(start.isoformat(), balance, ZERO)]
    monthly_change: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for item in sorted(snapshot.planned_transactions, key=lambda plan: plan.expected_date or ""):
        if item.status not in {"planned", "confirmed"} or not item.expected_date:
            continue
        amount = _signed_amount(item.entry_type, item.amount)
        balance += amount
        daily_points.append(ProjectionPoint(item.expected_date, balance, amount))
        monthly_change[_month_key(item.expected_date)] += amount
    monthly_points = []
    running = total_balance(snapshot)
    for month in sorted(monthly_change):
        running += monthly_change[month]
        monthly_points.append(ProjectionPoint(month, running, monthly_change[month]))
    return daily_points, monthly_points


def current_month(today: date | None = None) -> str:
    return (today or datetime.now().date()).strftime("%Y-%m")
