from __future__ import annotations

import argparse
import sys

from finance_manager.config.auth import run_oauth_flow
from finance_manager.services.gateway import FinanceGateway
from finance_manager.services.sheets import GoogleSheetsRepository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="finance-manager",
        description="Personal finance manager backed by Google Sheets.",
    )
    parser.add_argument(
        "--no-tui",
        action="store_true",
        help="Bootstrap the sheet and exit without opening the TUI.",
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("auth", help="Run Google OAuth login and store a refreshable token.")
    sub.add_parser("init", help="Create or validate the Google Sheets database.")
    sub.add_parser("doctor", help="Run a configuration and connectivity check.")
    return parser


def launch_tui(repository: FinanceGateway) -> None:
    from finance_manager.ui.app import run_tui

    run_tui(repository)


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    repository = GoogleSheetsRepository()

    if args.command == "auth":
        token_path = run_oauth_flow(repository.config)
        print(f"Saved OAuth token to: {token_path}")
        return

    if args.command == "init" or args.no_tui:
        spreadsheet_id = repository.bootstrap()
        print(f"Initialized Google Sheets database: {spreadsheet_id or '(created/opened successfully)'}")
        return

    if args.command == "doctor":
        spreadsheet_id = repository.bootstrap()
        snapshot = repository.load_snapshot()
        print("Configuration OK")
        print(f"Spreadsheet ID: {spreadsheet_id or 'unknown'}")
        print(f"Activity: {len(snapshot.transactions)}")
        print(f"Plans: {len(snapshot.planned_transactions)}")
        print(f"Budgets: {len(snapshot.budgets)}")
        print(f"Categories: {len(snapshot.categories)}")
        print(f"Accounts: {len(snapshot.accounts)}")
        return

    try:
        launch_tui(repository)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
