# AGENTS.md

Guidance for AI agents working in this repository.

## Project

`finance-manager` — a personal finance CLI/TUI app backed by Google Sheets. Python >= 3.9. Lives in the `finance_manager/` package. See `README.md` for the user-facing overview.

## Layout

- `finance_manager/services/sheets.py` — `GoogleSheetsRepository`, the storage layer.
- `finance_manager/models/` — entities, schemas.
- `finance_manager/logic/calculations.py` — balances, budget report, projection.
- `finance_manager/config/` — app config, OAuth auth.
- `finance_manager/ui/` — Textual TUI (`app.py`, `screens.py`, `forms.py`).
- `finance_manager/cli.py` — `finance-manager` entry point.
- `tests/` — pytest suite.

## Setup

Install the package and test/lint tooling:

```bash
python3 -m pip install .
python3 -m pip install pytest ruff mypy
```

## Verification commands

Run these before declaring a task complete. Use Bash.

- Tests: `python3 -m pytest -q`
- Lint: `python3 -m ruff check finance_manager tests`
- Type check: `python3 -m mypy finance_manager`

`pyproject.toml` declares `pytest` only as the configured test runner (`testpaths = ["tests"]`). There is no `lint`/`typecheck` npm-style script defined; invoke the tools directly as shown above.

## Conventions

- No code comments unless requested.
- Match existing style: `from __future__ import annotations`, type hints, frozen dataclasses for models.
- Tests live in `tests/` and use the `FakeClient`/`FakeSpreadsheet`/`FakeWorksheet` doubles in `tests/test_repository.py` as the in-memory backend for repository tests.
- Do not commit secrets or the OAuth token.