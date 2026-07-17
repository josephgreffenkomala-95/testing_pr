from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from finance_manager.config.settings import AppConfig
from finance_manager.models.schemas import SHEET_HEADERS
from finance_manager.services.sheets import GoogleSheetsRepository, InvalidSheetStructureError, StaleRecordError


class SequentialRecordIdGenerator:
    def __init__(self) -> None:
        self.counters: dict[str, int] = {}

    def __call__(self, prefix: str) -> str:
        next_value = self.counters.get(prefix, 0) + 1
        self.counters[prefix] = next_value
        return f"{prefix}{next_value:04d}"


class FakeWorksheet:
    def __init__(self, title: str) -> None:
        self.title = title
        self.rows: list[list[str]] = []
        self.frozen_rows = 0

    def append_row(self, row: list[str]) -> None:
        self.rows.append(list(row))

    def append_rows(self, rows: list[list[str]]) -> None:
        for row in rows:
            self.append_row(row)

    def row_values(self, index: int) -> list[str]:
        if 0 < index <= len(self.rows):
            return self.rows[index - 1]
        return []

    def get_all_records(self) -> list[dict[str, str]]:
        if not self.rows:
            return []
        headers = self.rows[0]
        return [dict(zip(headers, row)) for row in self.rows[1:]]

    def update(self, cell_range: str, values: list[list[str]]) -> None:
        row_ref = cell_range.split(":")[0]
        row_index = int("".join(ch for ch in row_ref if ch.isdigit())) - 1
        self.rows[row_index] = list(values[0])

    def delete_rows(self, index: int) -> None:
        self.rows.pop(index - 1)

    def freeze(self, rows: int) -> None:
        self.frozen_rows = rows


class FakeSpreadsheet:
    def __init__(self, title: str, spreadsheet_id: str = "sheet-1") -> None:
        self.title = title
        self.id = spreadsheet_id
        self.url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
        self._worksheets: dict[str, FakeWorksheet] = {}

    def worksheets(self) -> list[FakeWorksheet]:
        return list(self._worksheets.values())

    def add_worksheet(self, title: str, rows: int, cols: int) -> FakeWorksheet:
        worksheet = FakeWorksheet(title)
        self._worksheets[title] = worksheet
        return worksheet

    def worksheet(self, title: str) -> FakeWorksheet:
        return self._worksheets[title]


class FakeClient:
    def __init__(self) -> None:
        self.spreadsheet = FakeSpreadsheet("Personal Finance Manager")

    def open(self, title: str) -> FakeSpreadsheet:
        return self.spreadsheet

    def open_by_key(self, key: str) -> FakeSpreadsheet:
        return self.spreadsheet

    def create(self, title: str) -> FakeSpreadsheet:
        self.spreadsheet.title = title
        return self.spreadsheet

    def openall(self) -> list[FakeSpreadsheet]:
        return [self.spreadsheet]


def build_repo(tmp_path) -> GoogleSheetsRepository:
    config = AppConfig(
        config_dir=tmp_path,
        config_path=tmp_path / "config.json",
        oauth_client_secret_path=tmp_path / "oauth-client.json",
        oauth_token_path=tmp_path / "oauth-token.json",
        spreadsheet_title="Personal Finance Manager",
        spreadsheet_id=None,
    )
    return GoogleSheetsRepository(
        config=config,
        client_factory=FakeClient,
        clock=lambda: datetime(2026, 7, 17, 8, 30, tzinfo=UTC),
        record_id_generator=SequentialRecordIdGenerator(),
    )


def test_bootstrap_creates_release_schema_categories_and_no_fake_finances(tmp_path) -> None:
    """
    Condition:
    A new dedicated Finance Sheet is created for an empty installation.

    Expected:
    All domain tabs exist with frozen headers and only Settings/common Categories are initialized.
    """
    repo = build_repo(tmp_path)

    spreadsheet_id = repo.create_finance_sheet("IDR")
    snapshot = repo.load_snapshot()

    assert spreadsheet_id == "sheet-1"
    assert {sheet.title for sheet in repo._spreadsheet.worksheets()} == set(SHEET_HEADERS)
    assert all(sheet.frozen_rows == 1 for sheet in repo._spreadsheet.worksheets())
    assert snapshot.settings["base_currency"] == "IDR"
    assert {category.kind for category in snapshot.categories} == {"income", "expense"}
    assert snapshot.accounts == []
    assert snapshot.transactions == []
    assert snapshot.planned_transactions == []
    assert snapshot.budgets == []


def test_activity_round_trips_versions_and_void_history(tmp_path) -> None:
    """
    Condition:
    An Account and expense are added, edited with the current version, and voided.

    Expected:
    Exact decimals and versions round-trip while Activity remains as Voided history.
    """
    repo = build_repo(tmp_path)
    repo.create_finance_sheet("IDR")
    repo.add_account(
        {
            "name": "Cash",
            "account_type": "cash",
            "currency": "IDR",
            "opening_date": "2026-07-01",
            "opening_balance": "1000",
        }
    )
    created = repo.add_transaction(
        {
            "entry_type": "expense",
            "date": "2026-07-01",
            "amount": "150.50",
            "category": "Food",
            "description": "Lunch",
            "account": "Cash",
            "notes": "Team lunch",
        }
    )

    updated = repo.update_transaction(
        created.id,
        {
            "version": str(created.version),
            "entry_type": "expense",
            "date": "2026-07-02",
            "amount": "175.00",
            "category": "Food",
            "description": "Lunch with client",
            "account": "Cash",
            "notes": "",
        },
    )

    assert updated.amount == Decimal("175.00")
    assert updated.version == 2
    with pytest.raises(StaleRecordError, match="newer"):
        repo.update_transaction(created.id, {"version": "1", "description": "stale"})

    repo.delete_transaction(created.id)
    activity = repo.load_snapshot().transactions[0]
    assert activity.description == "Lunch with client"
    assert activity.is_voided is True


def test_invalid_headers_and_rows_report_precise_locations_without_hiding_safe_rows(tmp_path) -> None:
    """
    Condition:
    A tab header is malformed, then one Activity row contains an invalid decimal beside a valid row.

    Expected:
    Header failure is explicit; row reload keeps the valid row and reports tab, row, column, and value.
    """
    repo = build_repo(tmp_path)
    repo.create_finance_sheet("IDR")
    activity = repo._spreadsheet.worksheet("Activity")
    headers = activity.rows[0]
    activity.rows[0] = ["wrong", "headers"]
    with pytest.raises(InvalidSheetStructureError, match="Activity"):
        repo._ensure_schema()

    activity.rows[0] = headers
    account_sheet = repo._spreadsheet.worksheet("Accounts")
    account_headers = account_sheet.rows[0]
    account_row = dict.fromkeys(account_headers, "")
    account_row.update(
        {
            "id": "account-1",
            "name": "Cash",
            "account_type": "cash",
            "currency": "IDR",
            "opening_date": "2026-07-01",
            "current_balance": "0.00",
            "is_active": "true",
            "version": "1",
        }
    )
    account_sheet.append_row([account_row[key] for key in account_headers])
    valid = dict.fromkeys(headers, "")
    valid.update(
        {
            "id": "ACT-valid",
            "entry_type": "expense",
            "date": "2026-07-01",
            "amount": "10.00",
            "account_id": "account-1",
            "description": "Valid",
            "version": "1",
        }
    )
    invalid = {**valid, "id": "ACT-invalid", "amount": "not-money"}
    activity.append_rows([[row[key] for key in headers] for row in (valid, invalid)])

    repo.clear_cache()
    snapshot = repo.load_snapshot()

    assert [item.id for item in snapshot.transactions] == ["ACT-valid"]
    assert repo.validation_errors == ["Activity row 3, column amount: invalid value 'not-money'"]


def test_account_close_replaces_normal_deletion(tmp_path) -> None:
    """
    Condition:
    An unused zero-balance Account is removed through the repository API.

    Expected:
    It remains in Sheets as Closed history instead of being physically deleted.
    """
    repo = build_repo(tmp_path)
    repo.create_finance_sheet("IDR")
    account = repo.add_account(
        {
            "name": "Empty",
            "account_type": "bank",
            "currency": "IDR",
            "opening_date": "2026-07-01",
            "opening_balance": "0",
        }
    )

    repo.delete_account(account.id)

    assert len(repo.load_snapshot().accounts) == 1
    assert repo.load_snapshot().accounts[0].is_open is False


def test_seed_dummy_data_is_retired(tmp_path) -> None:
    """
    Condition:
    Legacy dummy-data seeding is invoked against the release schema.

    Expected:
    No fake financial records are created.
    """
    repo = build_repo(tmp_path)
    repo.create_finance_sheet("IDR")

    assert repo.seed_dummy_data() == 0
    assert repo.load_snapshot().transactions == []
