from unittest.mock import MagicMock, patch

import pytest

import finance_manager.cli as cli


def test_doctor_prints_summary(capsys):
    repository = MagicMock()
    repository.bootstrap.return_value = "sheet123"
    repository.load_snapshot.return_value = MagicMock(
        transactions=[1],
        planned_transactions=[1, 2],
        budgets=[],
        categories=[1, 2, 3],
        accounts=[1],
    )

    with patch("finance_manager.cli.GoogleSheetsRepository", return_value=repository):
        cli.main(["doctor"])

    out = capsys.readouterr().out
    assert "Configuration OK" in out
    assert "Spreadsheet ID: sheet123" in out
    assert "Planned transactions: 2" in out


def test_auth_runs_oauth_flow(capsys):
    repository = MagicMock()
    repository.config = MagicMock()
    with patch("finance_manager.cli.GoogleSheetsRepository", return_value=repository):
        with patch("finance_manager.cli.run_oauth_flow", return_value="/tmp/token.json") as run_auth:
            cli.main(["auth"])

    run_auth.assert_called_once_with(repository.config)
    out = capsys.readouterr().out
    assert "Saved OAuth token to: /tmp/token.json" in out


def test_default_command_runs_tui():
    repository = MagicMock()
    with patch("finance_manager.cli.GoogleSheetsRepository", return_value=repository):
        with patch("finance_manager.cli.launch_tui") as launch_tui:
            cli.main([])

    launch_tui.assert_called_once_with(repository)


def test_migration_command_is_not_supported(capsys) -> None:
    """
    Condition:
    The removed specialized workbook migration command is passed to the CLI.

    Expected:
    Argument parsing rejects the unsupported command.
    """
    with pytest.raises(SystemExit, match="2"):
        cli.main(["migrate", "moneyyy.xlsx"])

    assert "invalid choice: 'migrate'" in capsys.readouterr().err
