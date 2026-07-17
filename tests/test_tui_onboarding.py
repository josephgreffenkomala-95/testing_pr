from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from textual.widgets import Input, Static

from finance_manager.config.settings import AppConfig
from finance_manager.services.gateway import InMemoryFinanceGateway
from finance_manager.ui.app import FinanceManagerApp
from finance_manager.ui.screens import LoginScreen, SetupScreen, WorkspaceSetupScreen


class AuthenticationGateway(InMemoryFinanceGateway):
    requires_authentication = True


def test_oauth_setup_runs_through_pilot_with_validation_and_browser_fakes(tmp_path) -> None:
    """
    Condition:
    A disconnected TUI receives a valid Desktop OAuth JSON and injected browser authorization adapter.

    Expected:
    Guided setup reaches Finance Sheet creation and discloses protected credential storage without secrets.
    """
    oauth_file = tmp_path / "desktop.json"
    oauth_file.write_text(json.dumps({"installed": {"client_id": "test-client", "client_secret": "not-a-real-secret"}}))
    config = AppConfig(
        tmp_path,
        tmp_path / "config.json",
        tmp_path / "missing.json",
        tmp_path / "token.json",
        "Finance Sheet",
        None,
    )
    gateway = AuthenticationGateway(config=config, clock=lambda: datetime(2026, 7, 17, tzinfo=UTC))
    authorizations: list[AppConfig] = []
    app = FinanceManagerApp(
        gateway=gateway,
        oauth_flow=lambda selected: authorizations.append(selected) or "Credentials protected by fake OS store.",
    )

    async def exercise() -> None:
        async with app.run_test(size=(100, 36)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, SetupScreen)
            app.screen.query_one("#setup-path", Input).value = str(oauth_file)
            await pilot.click("#setup-continue")
            await pilot.pause()
            assert isinstance(app.screen, LoginScreen)

            await pilot.click("#login-btn")
            await pilot.pause()

            assert len(authorizations) == 1
            assert authorizations[0].oauth_client_secret_path == oauth_file
            assert isinstance(app.screen, WorkspaceSetupScreen)
            status = str(app.query_one("#status", Static).render())
            assert "Google connected" in status
            assert "not-a-real-secret" not in status

    asyncio.run(exercise())


def test_invalid_oauth_json_is_rejected_before_authorization(tmp_path) -> None:
    """
    Condition:
    A web OAuth JSON is selected instead of a Desktop client.

    Expected:
    The setup screen remains active with an actionable error and browser authorization never runs.
    """
    oauth_file = tmp_path / "web.json"
    oauth_file.write_text(json.dumps({"web": {"client_id": "client", "client_secret": "secret"}}))
    config = AppConfig(
        tmp_path,
        tmp_path / "config.json",
        tmp_path / "missing.json",
        tmp_path / "token.json",
        "Finance Sheet",
        None,
    )
    gateway = AuthenticationGateway(config=config)
    authorizations: list[AppConfig] = []
    app = FinanceManagerApp(gateway=gateway, oauth_flow=lambda selected: authorizations.append(selected) or "unused")

    async def exercise() -> None:
        async with app.run_test(size=(100, 36)) as pilot:
            await pilot.pause()
            app.screen.query_one("#setup-path", Input).value = str(oauth_file)
            await pilot.click("#setup-continue")
            await pilot.pause()

            assert isinstance(app.screen, SetupScreen)
            assert authorizations == []
            assert "Desktop" in str(app.query_one("#status", Static).render())

    asyncio.run(exercise())
