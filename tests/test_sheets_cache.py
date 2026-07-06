from finance_manager.config.settings import AppConfig
from finance_manager.services.sheets import GoogleSheetsRepository


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
        self.url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
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


def test_clear_cache_allows_external_changes_to_be_visible(tmp_path):
    repo = build_repo(tmp_path)
    repo.bootstrap()

    snapshot1 = repo.load_snapshot()
    assert len(snapshot1.transactions) == 0

    external_worksheet = repo._spreadsheet.worksheet("Transactions")
    external_worksheet.append_row([
        "TX0001", "expense", "2026-07-01", "100.00", "CAT0001", "ACC0001",
        "External", "", "2026-07-01 00:00:00", "2026-07-01 00:00:00"
    ])

    snapshot2 = repo.load_snapshot()
    assert len(snapshot2.transactions) == 0

    repo.clear_cache()
    snapshot3 = repo.load_snapshot()
    assert len(snapshot3.transactions) == 1
    assert snapshot3.transactions[0].description == "External"


def test_cache_is_updated_on_write_operations(tmp_path):
    repo = build_repo(tmp_path)
    repo.bootstrap()

    repo.load_snapshot()
    assert repo._cache is not None

    repo.add_transaction({
        "entry_type": "expense",
        "date": "2026-07-01",
        "amount": "100.00",
        "category": "Test",
        "description": "First",
        "account": "Cash",
        "notes": "",
    })
    assert repo._cache is not None
    assert len(repo._cache.transactions) == 1
    assert repo._cache.transactions[0].description == "First"

    snapshot2 = repo.load_snapshot()
    assert repo._cache is not None
    assert len(snapshot2.transactions) == 1


def test_cache_is_cleared_on_use_spreadsheet(tmp_path):
    repo = build_repo(tmp_path)
    repo.bootstrap()

    repo.load_snapshot()
    assert repo._cache is not None

    repo.use_spreadsheet("new-sheet-id", "New Sheet")
    assert repo._cache is None