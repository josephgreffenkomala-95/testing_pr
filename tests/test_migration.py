from decimal import Decimal

from finance_manager.services.migration import (
    MagangPlan,
    migrate_magang,
)
from tests.test_repository import build_repo


class FakeCell:
    def __init__(self, value) -> None:
        self.value = value


class FakeGrid:
    """In-memory grid that mimics openpyxl's `worksheet.cell(row, col).value` API."""

    def __init__(self, data: dict[tuple[int, int], object]) -> None:
        self._data = data

    def cell(self, row: int, column: int) -> FakeCell:
        return FakeCell(self._data.get((row, column)))


def _magang_grid() -> FakeGrid:
    # Mirrors the structure of the magang sheet in moneyyy.xlsx.
    cells: dict[tuple[int, int], object] = {}
    # Salary block A6:D16
    salary = [
        (6, 1.0, "Februari", 3250000, "done"),
        (7, 2.0, "Maret", 4250000, "done"),
        (8, 3.0, "April", 5250000, "done"),
        (9, 4.0, "Mei", 4000000, "done"),
        (10, 5.0, "Juni", 5000000, None),
        (11, 6.0, "Juli", 5750000, None),
        (12, 7.0, "Agustus", 1250000, None),
        (13, 8.0, "September", 0.0, None),
        (14, 9.0, "Oktober", 0.0, None),
        (15, 10.0, "November", 0.0, None),
        (16, 11.0, "perkiraan cuti", -1000000.0, None),
    ]
    for row, index, month, amount, status in salary:
        cells[(row, 1)] = index
        cells[(row, 2)] = month
        cells[(row, 3)] = amount
        cells[(row, 4)] = status
    # Perbulan block J6:K15 (cols 10,11)
    monthly = [
        (6, "Makan", 1170000),
        (7, "Kuota", 50000.0),
        (8, "Laundry", 100000.0),
        (9, "Persembahan", 50000.0),
        (11, "transport gereja", 80000.0),
        (12, "transport", 150000.0),
        (13, "jajan", 200000),
        (14, "Kost tambahan kost", 50000.0),
        (15, "keperluan kost", 75000.0),
    ]
    for row, name, amount in monthly:
        cells[(row, 10)] = name
        cells[(row, 11)] = amount
    # Kantong bersama R6:S11 (cols 18,19)
    shared = [
        (6, "Makan malam WFO", 490000),
        (7, "makan wfh", 700000),
        (8, "makan weekend", 630000),
        (9, "main cafe", 640000),
        (10, "main di luar cafe ", 200000),
        (11, "jajan", 600000),
    ]
    for row, name, amount in shared:
        cells[(row, 18)] = name
        cells[(row, 19)] = amount
    # Perpuluhan Mami B23:D29 (cols 2,3,4)
    tithe = [
        (23, 1.0, 500000.0, "done"),
        (24, 2.0, 500000.0, "done"),
        (25, 3.0, 500000.0, "done di gaji bulan 2"),
        (26, 4.0, 500000.0, None),
        (27, 5.0, 500000.0, None),
        (28, 6.0, 500000.0, None),
        (29, 7.0, 500000.0, None),
    ]
    for row, index, amount, status in tithe:
        cells[(row, 2)] = index
        cells[(row, 3)] = amount
        cells[(row, 4)] = status
    return FakeGrid(cells)


def test_magang_plan_parses_all_blocks():
    plan = MagangPlan(_magang_grid())
    assert len(plan.salary_rows) == 11
    assert plan.salary_rows[0].month_label == "Februari"
    assert plan.salary_rows[0].amount == Decimal("3250000.00")
    assert plan.salary_rows[0].is_done is True
    assert plan.salary_rows[4].is_done is False
    assert plan.salary_rows[0].month_number == 2

    assert len(plan.monthly_expenses) == 9
    assert plan.monthly_expenses[0].name == "Makan"
    assert plan.monthly_expenses[0].amount == Decimal("1170000.00")

    assert len(plan.shared_pocket) == 6
    assert plan.shared_pocket[0].name == "Makan malam WFO"

    assert len(plan.tithe_rows) == 7
    assert plan.tithe_rows[0].amount == Decimal("500000.00")
    assert plan.tithe_rows[0].is_done is True
    assert plan.tithe_rows[3].is_done is False


def test_migrate_magang_creates_transactions_planned_and_budgets(tmp_path):
    repo = build_repo(tmp_path)
    repo.bootstrap()
    # Drop the default seeded Cash account so migration creates its own.
    for account in repo.load_snapshot().accounts:
        repo.delete_account(account.id)

    plan = MagangPlan(_magang_grid())
    report = migrate_magang(repo, plan, year=2025)

    snapshot = repo.load_snapshot()

    # 4 completed salary rows + 3 completed tithe rows = 7 transactions
    assert report.transactions_created == 7
    assert len(snapshot.transactions) == 7

    # Pending salary rows with non-zero amount: Juni, Juli, Agustus (3)
    # Pending tithe rows: 4,5,6,7 (4) -> total 7 planned
    assert report.planned_created == 7
    assert len(snapshot.planned_transactions) == 7

    # Budgets: 9 monthly + 6 shared pocket = 15
    assert report.budgets_created == 15
    assert len(snapshot.budgets) == 15

    # Verify a completed salary transaction
    salary_tx = next(
        t for t in snapshot.transactions if t.description == "Gaji magang Februari"
    )
    assert salary_tx.entry_type == "income"
    assert salary_tx.amount == Decimal("3250000.00")
    assert salary_tx.date == "2025-02-01"

    # Verify a pending salary planned transaction
    planned_juni = next(
        t for t in snapshot.planned_transactions if t.description == "Gaji magang Juni"
    )
    assert planned_juni.entry_type == "income"
    assert planned_juni.status == "planned"
    assert planned_juni.expected_date == "2025-06-01"
    assert planned_juni.amount == Decimal("5000000.00")

    # Verify a completed tithe transaction
    tithe_tx = next(
        t for t in snapshot.transactions if t.description == "Perpuluhan Mami ke-1"
    )
    assert tithe_tx.entry_type == "expense"
    assert tithe_tx.amount == Decimal("500000.00")
    assert tithe_tx.date == "2025-02-01"

    # Categories were created as needed
    category_names = {c.name for c in snapshot.categories}
    assert "Salary" in category_names
    assert "Perpuluhan Mami" in category_names
    assert "Makan" in category_names

    # The Cash account should exist
    account_names = {a.name for a in snapshot.accounts}
    assert "Cash" in account_names


def test_migrate_magang_is_idempotent_when_called_twice_on_empty_sheet(tmp_path):
    repo = build_repo(tmp_path)
    repo.bootstrap()
    for account in repo.load_snapshot().accounts:
        repo.delete_account(account.id)

    plan = MagangPlan(_magang_grid())
    first = migrate_magang(repo, plan, year=2025)
    second = migrate_magang(repo, plan, year=2025)

    snapshot = repo.load_snapshot()
    assert first.transactions_created == 7
    assert second.transactions_created == 0
    assert second.planned_created == 0
    assert second.budgets_created == 0
    assert len(snapshot.transactions) == 7
    assert len(snapshot.planned_transactions) == 7
    assert len(snapshot.budgets) == 15
