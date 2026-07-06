from datetime import date
from decimal import Decimal

from finance_manager.logic.calculations import month_budget_report, projection, total_balance
from finance_manager.models.entities import Account, Budget, Category, PlannedTransaction, Snapshot, Transaction


def make_snapshot() -> Snapshot:
    return Snapshot(
        transactions=[
            Transaction("TX0001", "expense", "2026-07-02", Decimal("120.00"), "CAT1000", "ACC1000", "Groceries"),
            Transaction("TX0002", "income", "2026-07-03", Decimal("500.00"), "CAT2000", "ACC1000", "Salary"),
        ],
        planned_transactions=[
            PlannedTransaction("PLN0001", "expense", "planned", "2026-07-10", Decimal("80.00"), "CAT1000", "ACC1000", "More groceries"),
            PlannedTransaction("PLN0002", "income", "confirmed", "2026-07-15", Decimal("200.00"), "CAT2000", "ACC1000", "Bonus"),
            PlannedTransaction("PLN0003", "expense", "cancelled", "2026-07-20", Decimal("999.00"), "CAT1000", "ACC1000", "Ignored"),
        ],
        budgets=[
            Budget("BDG0001", "2026-07", "CAT1000", "expense", Decimal("300.00")),
            Budget("BDG0002", "2026-07", "CAT2000", "income", Decimal("1000.00")),
        ],
        categories=[
            Category("CAT1000", "Groceries", "expense"),
            Category("CAT2000", "Salary", "income"),
        ],
        accounts=[
            Account("ACC1000", "Cash", "cash", "IDR", Decimal("1000.00")),
            Account("ACC2000", "Bank", "bank", "IDR", Decimal("250.00")),
        ],
        settings={},
    )


def test_month_budget_report_combines_actual_and_planned():
    snapshot = make_snapshot()

    report = month_budget_report(snapshot, "2026-07")

    groceries = next(row for row in report if row.category_name == "Groceries")
    assert groceries.budgeted == Decimal("300.00")
    assert groceries.actual == Decimal("120.00")
    assert groceries.planned == Decimal("80.00")
    assert groceries.projected_remaining == Decimal("100.00")


def test_total_balance_sums_accounts():
    snapshot = make_snapshot()

    assert total_balance(snapshot.accounts) == Decimal("1250.00")


def test_projection_uses_future_planned_transactions():
    snapshot = make_snapshot()

    daily, monthly = projection(snapshot, start_on=date(2026, 7, 5))

    assert daily[0].balance == Decimal("1250.00")
    assert daily[1].label == "2026-07-10"
    assert daily[1].balance == Decimal("1170.00")
    assert daily[2].balance == Decimal("1370.00")
    assert monthly[0].label == "2026-07"
    assert monthly[0].balance == Decimal("1370.00")
