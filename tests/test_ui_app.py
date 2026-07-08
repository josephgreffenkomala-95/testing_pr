import asyncio

from finance_manager.ui.app import FinanceManagerApp, LIGHT_CSS, LIGHT_CONFIRM_CSS, LIGHT_LOGIN_CSS, TOKYONIGHT_CONFIRM_CSS
from finance_manager.ui.forms import ConfirmScreen
from finance_manager.ui.screens import LoginScreen
from tests.test_repository import build_repo


def build_app(tmp_path):
    repository = build_repo(tmp_path)
    repository.config.oauth_client_secret_path.write_text("{}")
    repository.config.oauth_token_path.write_text("token")
    repository.bootstrap()
    return FinanceManagerApp(repository=repository)


def test_toggle_theme_refreshes_main_detail_and_open_modal(tmp_path):
    async def run() -> None:
        app = build_app(tmp_path)

        async with app.run_test() as pilot:
            await pilot.pause()

            app.action_seed_dummy()
            await pilot.pause()

            detail = app.query_one("#detail")
            panel = detail.content
            assert str(panel.border_style) == "#7aa2f7"

            app.action_delete_record()
            await pilot.pause()

            screen = app.screen
            assert isinstance(screen, ConfirmScreen)
            assert screen.css == TOKYONIGHT_CONFIRM_CSS

            app.action_toggle_theme()
            await pilot.pause()

            panel = app.query_one("#detail").content
            assert app.CSS == LIGHT_CSS
            assert str(panel.border_style) == "#4a90d9"
            assert screen.css == LIGHT_CONFIRM_CSS

    asyncio.run(run())


def test_new_modal_uses_active_theme_after_toggle(tmp_path):
    async def run() -> None:
        app = build_app(tmp_path)

        async with app.run_test() as pilot:
            await pilot.pause()

            app.action_toggle_theme()
            await pilot.pause()

            app.action_login()
            await pilot.pause()

            screen = app.screen
            assert isinstance(screen, LoginScreen)
            assert screen.css == LIGHT_LOGIN_CSS

    asyncio.run(run())
