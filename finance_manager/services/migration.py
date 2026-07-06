from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Protocol

from finance_manager.models.entities import Account, Budget, Category, PlannedTransaction, Transaction
from finance_manager.services.sheets import GoogleSheetsRepository


MONTH_NAME_TO_NUMBER = {
    "januari": 1, "jan": 1,
    "februari": 2, "feb": 2,
    "maret": 3, "mar": 3,
    "april": 4, "apr": 4,
    "mei": 5,
    "juni": 6, "jun": 6,
    "juli": 7, "jul": 7,
    "agustus": 8, "aug": 8, "ags": 8,
    "september": 9, "sep": 9, "sept": 9,
    "oktober": 10, "okt": 10, "oct": 10,
    "november": 11, "nov": 11,
    "desember": 12, "des": 12, "dec": 12,
}


class CellLike(Protocol):
    value: object


class CellGrid(Protocol):
    def cell(self, row: int, column: int) -> CellLike: ...


class MagangPlan:
    """Parsed view of the `magang` sheet inside moneyyy.xlsx.

    The sheet is loosely structured and uses Indonesian labels. This parser
    extracts the four blocks that represent the user's financial plan:

    - Gaji magang (internship income) at A6:D16
    - Pengeluaran perbulan (monthly recurring expenses) at J6:K15
    - Kantong bersama (shared-pocket expenses) at R6:S11
    - Perpuluhan Mami (monthly tithe to mother) at B23:D29
    """

    def __init__(self, grid: CellGrid) -> None:
        self._grid = grid
        self.salary_rows: list[SalaryRow] = self._read_salary()
        self.monthly_expenses: list[LineItem] = self._read_block(start_row=6, end_row=15, name_col=10, amount_col=11)
        self.shared_pocket: list[LineItem] = self._read_block(start_row=6, end_row=11, name_col=18, amount_col=19)
        self.tithe_rows: list[TitheRow] = self._read_tithe()

    def _cell(self, row: int, column: int) -> object:
        return self._grid.cell(row, column).value

    def _read_salary(self) -> list[SalaryRow]:
        rows: list[SalaryRow] = []
        for r in range(6, 17):
            index = self._cell(r, 1)
            month_label = self._cell(r, 2)
            amount = self._cell(r, 3)
            status = self._cell(r, 4)
            if index is None and month_label is None and amount is None:
                continue
            rows.append(SalaryRow(index, str(month_label or "").strip(), amount, str(status or "").strip().lower()))
        return rows

    def _read_block(self, start_row: int, end_row: int, name_col: int, amount_col: int) -> list[LineItem]:
        items: list[LineItem] = []
        for r in range(start_row, end_row + 1):
            name = self._cell(r, name_col)
            amount = self._cell(r, amount_col)
            if not name:
                continue
            items.append(LineItem(str(name).strip(), amount))
        return items

    def _read_tithe(self) -> list[TitheRow]:
        rows: list[TitheRow] = []
        for r in range(23, 30):
            index = self._cell(r, 2)
            amount = self._cell(r, 3)
            status = self._cell(r, 4)
            if index is None and amount is None:
                continue
            rows.append(TitheRow(index, amount, str(status or "").strip().lower()))
        return rows


class SalaryRow:
    def __init__(self, index: object, month_label: str, amount: object, status: str) -> None:
        self.index = index
        self.month_label = month_label
        self.amount = _to_decimal(amount)
        self.status = status

    @property
    def is_done(self) -> bool:
        return self.status == "done"

    @property
    def month_number(self) -> int | None:
        if not self.month_label:
            return None
        return MONTH_NAME_TO_NUMBER.get(self.month_label.lower())

    def description(self, year: int) -> str:
        return f"Gaji magang {self.month_label}".strip()


class TitheRow:
    def __init__(self, index: object, amount: object, status: str) -> None:
        self.index = index
        self.amount = _to_decimal(amount)
        self.status = status

    @property
    def is_done(self) -> bool:
        return self.status.startswith("done")


class LineItem:
    def __init__(self, name: str, amount: object) -> None:
        self.name = name
        self.amount = _to_decimal(amount)


def _to_decimal(value: object) -> Decimal:
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except Exception:
        return Decimal("0")


def _default_year() -> int:
    from datetime import UTC, datetime
    return datetime.now(UTC).year


def migrate_magang(
    repository: GoogleSheetsRepository,
    plan: MagangPlan,
    *,
    year: int | None = None,
    account_name: str = "Cash",
    tithe_account_name: str = "Cash",
) -> MigrationReport:
    """Migrate a parsed `magang` plan into the repository.

    - completed salary / tithe rows become Transactions
    - pending salary / tithe rows become PlannedTransactions
    - monthly recurring expenses and shared-pocket items become Budgets for the
      corresponding month (default: the current month)
    """
    year = year or _default_year()
    report = MigrationReport()

    snapshot = repository.load_snapshot()
    accounts_by_name = {a.name: a for a in snapshot.accounts}
    cash_account = accounts_by_name.get(account_name) or _ensure_account(repository, account_name)
    tithe_account = accounts_by_name.get(tithe_account_name) or _ensure_account(repository, tithe_account_name)

    month_budget_repo = _build_monthly_budgets(repository, plan.monthly_expenses + plan.shared_pocket, year)
    report.budgets_created = len(month_budget_repo)

    for row in plan.salary_rows:
        if row.amount <= 0:
            continue
        month_number = row.month_number
        if month_number is None:
            continue
        category = _ensure_category(repository, "Salary", "income")
        if row.is_done:
            transaction = _append_transaction(
                repository,
                entry_type="income",
                date=_date(year, month_number, 1),
                amount=row.amount,
                category=category,
                account=cash_account,
                description=row.description(year),
            )
            report.transactions_created += 1
            report.transactions.append(transaction)
        else:
            planned = _append_planned(
                repository,
                entry_type="income",
                status="planned",
                expected_date=_date(year, month_number, 1),
                amount=row.amount,
                category=category,
                account=cash_account,
                description=row.description(year),
            )
            report.planned_created += 1
            report.planned.append(planned)

    tithe_category = _ensure_category(repository, "Perpuluhan Mami", "expense")
    for index, tithe in enumerate(plan.tithe_rows, start=1):
        if tithe.amount <= 0:
            continue
        month_number = _tithe_month_number(index)
        if month_number is None:
            continue
        if tithe.is_done:
            transaction = _append_transaction(
                repository,
                entry_type="expense",
                date=_date(year, month_number, 1),
                amount=tithe.amount,
                category=tithe_category,
                account=tithe_account,
                description=f"Perpuluhan Mami ke-{index}",
            )
            report.transactions_created += 1
            report.transactions.append(transaction)
        else:
            planned = _append_planned(
                repository,
                entry_type="expense",
                status="planned",
                expected_date=_date(year, month_number, 1),
                amount=tithe.amount,
                category=tithe_category,
                account=tithe_account,
                description=f"Perpuluhan Mami ke-{index}",
            )
            report.planned_created += 1
            report.planned.append(planned)

    return report


def _tithe_month_number(index: int) -> int:
    # Perpuluhan rows start at the same month as the first salary (Februari=2).
    base = 2
    return base + (index - 1)


def _build_monthly_budgets(
    repository: GoogleSheetsRepository,
    items: list[LineItem],
    year: int,
) -> list[Budget]:
    from datetime import UTC, datetime
    current_month = datetime.now(UTC).strftime("%Y-%m")
    created: list[Budget] = []
    for item in items:
        if item.amount <= 0:
            continue
        _ensure_category(repository, item.name, "expense")
        budget = repository.add_budget(
            {
                "month": current_month,
                "category": item.name,
                "entry_type": "expense",
                "amount": str(item.amount),
                "notes": f"Migrated from magang plan ({year})",
            }
        )
        created.append(budget)
    return created


def _ensure_account(repository: GoogleSheetsRepository, name: str) -> Account:
    snapshot = repository.load_snapshot()
    for account in snapshot.accounts:
        if account.name.lower() == name.lower():
            return account
    return repository.add_account(
        {"name": name, "account_type": "cash", "currency": "IDR", "current_balance": "0"}
    )


def _ensure_category(repository: GoogleSheetsRepository, name: str, entry_type: str) -> Category:
    return repository.ensure_category(name, entry_type)


def _date(year: int, month: int, day: int) -> str:
    return f"{year:04d}-{month:02d}-{day:02d}"


def _append_transaction(
    repository: GoogleSheetsRepository,
    *,
    entry_type: str,
    date: str,
    amount: Decimal,
    category: Category,
    account: Account,
    description: str,
) -> Transaction:
    return repository.add_transaction(
        {
            "entry_type": entry_type,
            "date": date,
            "amount": str(amount),
            "category": category.name,
            "account": account.name,
            "description": description,
            "notes": "Migrated from magang sheet",
        }
    )


def _append_planned(
    repository: GoogleSheetsRepository,
    *,
    entry_type: str,
    status: str,
    expected_date: str,
    amount: Decimal,
    category: Category,
    account: Account,
    description: str,
) -> PlannedTransaction:
    return repository.add_planned_transaction(
        {
            "entry_type": entry_type,
            "status": status,
            "expected_date": expected_date,
            "amount": str(amount),
            "category": category.name,
            "account": account.name,
            "description": description,
            "notes": "Migrated from magang sheet",
        }
    )


class MigrationReport:
    def __init__(self) -> None:
        self.transactions_created = 0
        self.planned_created = 0
        self.budgets_created = 0
        self.transactions: list[Transaction] = []
        self.planned: list[PlannedTransaction] = []

    def summary(self) -> str:
        return (
            f"Migration complete: "
            f"{self.transactions_created} transactions, "
            f"{self.planned_created} planned transactions, "
            f"{self.budgets_created} budgets."
        )


def load_magang_from_path(path: str, sheet: str = "magang") -> MagangPlan:
    """Read the `magang` sheet from an .xlsx workbook on disk."""
    import openpyxl

    workbook = openpyxl.load_workbook(path, data_only=True)
    if sheet not in workbook.sheetnames:
        raise KeyError(f"Sheet '{sheet}' not found in {path}. Available: {workbook.sheetnames}")
    worksheet = workbook[sheet]
    return MagangPlan(worksheet)


def iter_magang_salary(rows: Iterable[SalaryRow]) -> Iterable[SalaryRow]:
    for row in rows:
        if row.amount and row.month_number:
            yield row