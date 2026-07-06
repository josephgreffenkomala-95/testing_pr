from decimal import Decimal

from finance_manager.config.settings import AppConfig
from finance_manager.services.sheets import GoogleSheetsRepository, InvalidSheetStructureError


class FakeWorksheet:
    def __init__(self, title):
        self.title = title
        self.rows = []

    def append_row(self, row):
        self.rows.append(list(row))

    def append_rows(self, rows):
        for row in rows:
            self.append_row(row)

    def row_values(self, index):
        if 0 < index <= len(self.rows):
            return self.rows[index - 1]
        return []

    def get_all_records(self):
        if not self.rows:
            return []
        headers = self.rows[0]
        return [dict(zip(headers, row)) for row in self.rows[1:]]

    def update(self, cell_range, values):
        row_ref = cell_range.split(":")[0]
        row_index = int("".join(ch for ch in row_ref if ch.isdigit())) - 1
        self.rows[row_index] = list(values[0])

    def delete_rows(self, index):
        self.rows.pop(index - 1)


class FakeSpreadsheet:
    def __init__(self, title, spreadsheet_id="sheet-1"):
        self.title = title
        self.id = spreadsheet_id
        self._worksheets = {}

    def worksheets(self):
        return list(self._worksheets.values())

    def add_worksheet(self, title, rows, cols):
        worksheet = FakeWorksheet(title)
        self._worksheets[title] = worksheet
        return worksheet

    def worksheet(self, title):
        return self._worksheets[title]


class FakeClient:
    def __init__(self):
        self.spreadsheet = FakeSpreadsheet("Personal Finance Manager")

    def open(self, title):
        return self.spreadsheet

    def open_by_key(self, key):
        return self.spreadsheet

    def create(self, title):
        return self.spreadsheet


def build_repo(tmp_path):
    config = AppConfig(
        config_dir=tmp_path,
        config_path=tmp_path / "config.json",
        oauth_client_secret_path=tmp_path / "oauth-client.json",
        oauth_token_path=tmp_path / "oauth-token.json",
        spreadsheet_title="Personal Finance Manager",
        spreadsheet_id=None,
    )
    return GoogleSheetsRepository(config=config, client_factory=FakeClient)


def test_bootstrap_creates_schema_and_defaults(tmp_path):
    repo = build_repo(tmp_path)

    spreadsheet_id = repo.bootstrap()
    snapshot = repo.load_snapshot()

    assert spreadsheet_id == "sheet-1"
    assert {sheet.title for sheet in repo._spreadsheet.worksheets()} == {
        "Transactions",
        "Planned Transactions",
        "Budgets",
        "Categories",
        "Accounts",
        "Settings",
    }
    assert len(snapshot.categories) >= 1
    assert len(snapshot.accounts) == 1


def test_transaction_crud_works_against_sheet_backend(tmp_path):
    repo = build_repo(tmp_path)
    repo.bootstrap()

    created = repo.add_transaction(
        {
            "entry_type": "expense",
            "date": "2026-07-01",
            "amount": "150.50",
            "category": "Dining",
            "description": "Lunch",
            "account": "Cash",
            "notes": "Team lunch",
        }
    )
    assert created.id == "TX0001"

    updated = repo.update_transaction(
        created.id,
        {
            "entry_type": "expense",
            "date": "2026-07-02",
            "amount": "175.00",
            "category": "Dining",
            "description": "Lunch with client",
            "account": "Cash",
            "notes": "",
        },
    )
    assert updated.amount == Decimal("175.00")

    snapshot = repo.load_snapshot()
    assert snapshot.transactions[0].description == "Lunch with client"

    repo.delete_transaction(created.id)
    assert repo.load_snapshot().transactions == []


def test_invalid_headers_raise_error(tmp_path):
    repo = build_repo(tmp_path)
    repo.bootstrap()
    repo._spreadsheet.worksheet("Transactions").rows[0] = ["wrong", "headers"]

    try:
        repo._ensure_schema()
    except InvalidSheetStructureError:
        pass
    else:
        raise AssertionError("Expected InvalidSheetStructureError")


def test_add_multiple_accounts_and_crud(tmp_path):
    repo = build_repo(tmp_path)
    repo.bootstrap()
    repo.delete_account("ACC0001")

    first = repo.add_account({"name": "Bank BCA", "account_type": "bank", "currency": "IDR", "current_balance": "5000000.00"})
    second = repo.add_account({"name": "Cash", "account_type": "cash", "currency": "IDR", "current_balance": "250000.00"})
    third = repo.add_account({"name": "Bank Mandiri", "account_type": "bank", "currency": "IDR", "current_balance": "1200000.00"})

    accounts = repo.load_snapshot().accounts
    assert {account.name for account in accounts} == {"Bank BCA", "Cash", "Bank Mandiri"}
    assert first.id != second.id != third.id

    duplicate = False
    try:
        repo.add_account({"name": "Bank BCA", "account_type": "bank", "currency": "IDR", "current_balance": "0"})
    except ValueError:
        duplicate = True
    assert duplicate

    updated = repo.update_account(first.id, {"name": "Bank BCA", "account_type": "bank", "currency": "IDR", "current_balance": "7500000.00"})
    assert updated.current_balance == Decimal("7500000.00")

    repo.delete_account(second.id)
    remaining = {account.name for account in repo.load_snapshot().accounts}
    assert remaining == {"Bank BCA", "Bank Mandiri"}


def test_seed_dummy_data_populates_sheet(tmp_path):
    repo = build_repo(tmp_path)
    repo.bootstrap()
    for account in repo.load_snapshot().accounts:
        repo.delete_account(account.id)

    created = repo.seed_dummy_data()
    snapshot = repo.load_snapshot()

    assert created > 0
    assert len(snapshot.accounts) == 3
    assert len(snapshot.categories) >= 5
    assert len(snapshot.transactions) == 7
    assert {account.name for account in snapshot.accounts} == {"Cash", "Bank BCA", "Bank Mandiri"}

    second = repo.seed_dummy_data()
    assert second == 0
