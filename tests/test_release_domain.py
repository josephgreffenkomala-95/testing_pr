from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from finance_manager.logic.calculations import (
    account_balances,
    budget_safe_balance,
    expand_recurring_plan,
    month_budget_report,
    projection_summary,
)
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
from finance_manager.services.gateway import InMemoryFinanceGateway


NOW = datetime(2026, 7, 17, 8, 30, tzinfo=UTC)


def _account(account_id: str, name: str, balance: str) -> Account:
    return Account(
        account_id,
        name,
        "bank",
        "IDR",
        Decimal(balance),
        opening_date="2026-07-01",
    )


def _snapshot() -> Snapshot:
    return Snapshot(
        transactions=[],
        planned_transactions=[],
        budgets=[],
        categories=[
            Category("expense-category", "Food", "expense"),
            Category("income-category", "Salary", "income"),
        ],
        accounts=[_account("checking", "Checking", "1000"), _account("cash", "Cash", "100")],
        settings={"base_currency": "IDR"},
    )


def test_activity_transfer_void_and_reconciliation_preserve_financial_semantics() -> None:
    """
    Condition:
    Income, expense, Transfer, void, and reconciliation Activity affect two Accounts.

    Expected:
    Balances are derived, Transfer is net-zero, void removes its effect, and adjustment is balance-only.
    """
    gateway = InMemoryFinanceGateway(
        snapshot=_snapshot(),
        clock=lambda: NOW,
        record_id_generator=lambda prefix: f"{prefix}-{len(gateway.load_snapshot().transactions) + 1}",
    )
    gateway.add_transaction(
        {
            "entry_type": "income",
            "date": "2026-07-10",
            "amount": "500",
            "category": "Salary",
            "account": "Checking",
            "description": "Pay",
        }
    )
    expense = gateway.add_transaction(
        {
            "entry_type": "expense",
            "date": "2026-07-11",
            "amount": "200",
            "category": "Food",
            "account": "Checking",
            "description": "Groceries",
        }
    )
    gateway.add_transfer(
        {
            "date": "2026-07-12",
            "amount": "300",
            "source_account": "Checking",
            "destination_account": "Cash",
            "description": "ATM",
        }
    )

    assert account_balances(gateway.load_snapshot()) == {
        "checking": Decimal("1000.00"),
        "cash": Decimal("400.00"),
    }

    gateway.void_transaction(expense.id, "Entered twice")
    adjustment = gateway.reconcile_account("cash", Decimal("450"), "2026-07-13")

    assert adjustment.entry_type == "adjustment"
    assert account_balances(gateway.load_snapshot()) == {
        "checking": Decimal("1200.00"),
        "cash": Decimal("450.00"),
    }


def test_activity_rejects_future_pre_opening_and_closed_account_entries() -> None:
    """
    Condition:
    Activity is attempted outside the tracked dates and after Account closure.

    Expected:
    Invalid Activity is rejected before it enters financial history.
    """
    gateway = InMemoryFinanceGateway(snapshot=_snapshot(), clock=lambda: NOW)
    base = {
        "entry_type": "expense",
        "amount": "1",
        "category": "Food",
        "account": "Checking",
        "description": "Invalid",
    }

    with pytest.raises(ValueError, match="Opening Date"):
        gateway.add_transaction({**base, "date": "2026-06-30"})
    with pytest.raises(ValueError, match="future"):
        gateway.add_transaction({**base, "date": "2026-07-18"})

    empty = InMemoryFinanceGateway(
        snapshot=Snapshot([], [], [], [], [_account("empty", "Empty", "0")], {}),
        clock=lambda: NOW,
    )
    empty.close_account("empty")
    with pytest.raises(ValueError, match="closed"):
        empty.add_transaction({**base, "date": "2026-07-17", "account": "Empty"})


def test_plan_completion_is_atomic_idempotent_and_keeps_variance() -> None:
    """
    Condition:
    A confirmed expense Plan is completed twice with differing actual values.

    Expected:
    One linked Activity exists, the Plan remains as completed history, and variance is visible.
    """
    gateway = InMemoryFinanceGateway(snapshot=_snapshot(), clock=lambda: NOW)
    plan = gateway.add_planned_transaction(
        {
            "entry_type": "expense",
            "status": "confirmed",
            "schedule_precision": "exact",
            "expected_date": "2026-07-17",
            "amount": "100",
            "category": "Food",
            "account": "Checking",
            "description": "Dinner",
        }
    )
    actual = {
        "date": "2026-07-17",
        "amount": "125",
        "category": "Food",
        "account": "Checking",
        "description": "Dinner with tip",
    }

    first = gateway.complete_plan(plan.id, actual)
    second = gateway.complete_plan(plan.id, actual)
    completed = gateway.get_planned_transaction(plan.id)

    assert first == second
    assert len(gateway.load_snapshot().transactions) == 1
    assert completed.status == "completed"
    assert completed.completed_activity_id == first.id
    assert gateway.plan_variance(plan.id) == {
        "amount": (Decimal("100.00"), Decimal("125.00")),
        "description": ("Dinner", "Dinner with tip"),
    }


@pytest.mark.parametrize(
    ("horizon", "expected"),
    [
        (date(2026, 2, 28), [date(2026, 1, 31), date(2026, 2, 28)]),
        (date(2026, 3, 31), [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)]),
    ],
)
def test_monthly_recurrence_uses_month_end_then_returns_to_requested_day(
    horizon: date,
    expected: list[date],
) -> None:
    """
    Condition:
    A monthly Recurring Plan starts on the 31st and expands across shorter months.

    Expected:
    Missing days use month-end without changing the requested day in later months.
    """
    rule = RecurringPlan(
        "recurring-1",
        "expense",
        "planned",
        "monthly",
        "2026-01-31",
        None,
        Decimal("50"),
        "expense-category",
        "checking",
        "Subscription",
    )

    occurrences = expand_recurring_plan(rule, horizon)

    assert [occurrence.date for occurrence in occurrences] == expected


def test_recurring_exception_changes_one_occurrence_only() -> None:
    """
    Condition:
    One monthly occurrence has an amount/date exception and a second is cancelled.

    Expected:
    Expansion applies only those exceptions and leaves the rule unchanged.
    """
    rule = RecurringPlan(
        "recurring-1",
        "income",
        "confirmed",
        "monthly",
        "2026-01-15",
        "2026-03-31",
        Decimal("100"),
        "income-category",
        "checking",
        "Retainer",
    )
    exceptions = [
        PlanException("exception-1", rule.id, "2026-02-15", "changed", "2026-02-16", Decimal("125")),
        PlanException("exception-2", rule.id, "2026-03-15", "cancelled"),
    ]

    occurrences = expand_recurring_plan(rule, date(2026, 3, 31), exceptions)

    assert [(item.date, item.amount) for item in occurrences] == [
        (date(2026, 1, 15), Decimal("100")),
        (date(2026, 2, 16), Decimal("125")),
    ]


def test_projection_distinguishes_expected_confirmed_range_shortfall_and_budget_safe() -> None:
    """
    Condition:
    Exact, month-only, planned, confirmed, expense Budget, and Income Target data coexist.

    Expected:
    Projection answers remain distinct and the conservative Budget reserve is not double-counted.
    """
    snapshot = _snapshot()
    snapshot.planned_transactions.extend(
        [
            PlannedTransaction(
                "planned-income",
                "income",
                "planned",
                "2026-07-20",
                Decimal("500"),
                "income-category",
                "cash",
                "Maybe bonus",
            ),
            PlannedTransaction(
                "confirmed-expense",
                "expense",
                "confirmed",
                None,
                Decimal("1200"),
                "expense-category",
                "checking",
                "Rent",
                schedule_precision="month",
                scheduled_month="2026-07",
            ),
        ]
    )
    snapshot.budgets.extend(
        [
            Budget("budget", "2026-07", "expense-category", "expense", Decimal("1500")),
            Budget("target", "2026-07", "income-category", "income", Decimal("9000")),
        ]
    )

    result = projection_summary(snapshot, date(2026, 7, 20), today=date(2026, 7, 17))

    assert result.expected == Decimal("400.00")
    assert result.confirmed == Decimal("-100.00")
    assert (result.low, result.high) == (Decimal("400.00"), Decimal("1600.00"))
    assert result.budget_safe == Decimal("100.00")
    assert result.shortfall is not None
    assert result.shortfall.account_id == "checking"
    assert budget_safe_balance(snapshot, result.expected, "2026-07") == Decimal("100.00")


def test_budget_month_category_is_unique_and_copy_is_independent() -> None:
    """
    Condition:
    A monthly Category Budget is duplicated and then copied to another month.

    Expected:
    Duplicate creation is rejected and the copied record can change independently.
    """
    gateway = InMemoryFinanceGateway(snapshot=_snapshot(), clock=lambda: NOW)
    original = gateway.add_budget(
        {
            "month": "2026-07",
            "entry_type": "expense",
            "category": "Food",
            "amount": "500",
        }
    )
    with pytest.raises(ValueError, match="already exists"):
        gateway.add_budget(
            {
                "month": "2026-07",
                "entry_type": "expense",
                "category": "Food",
                "amount": "600",
            }
        )

    copied = gateway.copy_budgets("2026-07", "2026-08")
    gateway.update_budget(
        copied[0].id,
        {
            "month": "2026-08",
            "entry_type": "expense",
            "category": "Food",
            "amount": "700",
        },
    )

    assert gateway.load_snapshot().budgets[0] == original
    assert gateway.load_snapshot().budgets[1].amount == Decimal("700.00")


def test_category_type_is_permanent_and_income_target_progress_counts_down() -> None:
    """
    Condition:
    An expense Category is reused for income and an Income Target has actual plus planned progress.

    Expected:
    Category type reuse is rejected and target remaining decreases as income is received or planned.
    """
    gateway = InMemoryFinanceGateway(snapshot=_snapshot(), clock=lambda: NOW)
    with pytest.raises(ValueError, match="is expense"):
        gateway.add_transaction(
            {
                "entry_type": "income",
                "date": "2026-07-17",
                "amount": "10",
                "category": "Food",
                "account": "Checking",
                "description": "Wrong category",
            }
        )

    snapshot = _snapshot()
    snapshot.transactions.append(
        Transaction(
            "income",
            "income",
            "2026-07-10",
            Decimal("300"),
            "income-category",
            "checking",
            "Salary",
        )
    )
    snapshot.planned_transactions.append(
        PlannedTransaction(
            "more-income",
            "income",
            "confirmed",
            "2026-07-20",
            Decimal("200"),
            "income-category",
            "checking",
            "More salary",
        )
    )
    snapshot.budgets.append(Budget("target", "2026-07", "income-category", "income", Decimal("1000")))

    usage = month_budget_report(snapshot, "2026-07")[0]

    assert usage.projected_remaining == Decimal("500")
