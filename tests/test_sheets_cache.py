from __future__ import annotations

from tests.test_repository import build_repo


def test_clear_cache_allows_safe_external_activity_to_be_visible(tmp_path) -> None:
    """
    Condition:
    A valid Activity row is added directly to the Finance Sheet after an initial read.

    Expected:
    Cached data stays stable until reload and then exposes the direct edit.
    """
    repo = build_repo(tmp_path)
    repo.create_finance_sheet("IDR")
    first = repo.load_snapshot()
    assert first.transactions == []
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
    worksheet = repo._spreadsheet.worksheet("Activity")
    headers = worksheet.rows[0]
    row = dict.fromkeys(headers, "")
    row.update(
        {
            "id": "ACT-external",
            "entry_type": "expense",
            "date": "2026-07-01",
            "amount": "100.00",
            "account_id": "account-1",
            "description": "External",
            "version": "1",
        }
    )
    worksheet.append_row([row[key] for key in headers])

    assert repo.load_snapshot().transactions == []
    repo.clear_cache()
    assert repo.load_snapshot().transactions[0].description == "External"


def test_cache_is_cleared_on_write_and_sheet_selection(tmp_path) -> None:
    """
    Condition:
    Data is cached before a write and before selecting another Finance Sheet.

    Expected:
    Both operations invalidate the cached snapshot.
    """
    repo = build_repo(tmp_path)
    repo.create_finance_sheet("IDR")
    repo.load_snapshot()
    assert repo._cache is not None

    repo.add_account(
        {
            "name": "Cash",
            "account_type": "cash",
            "currency": "IDR",
            "opening_date": "2026-07-01",
            "opening_balance": "0",
        }
    )
    assert repo._cache is None

    repo.load_snapshot()
    repo.use_spreadsheet("new-sheet-id", "New Sheet")
    assert repo._cache is None
