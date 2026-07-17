from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

from textual.widgets import DataTable, Static

from finance_manager.models.entities import Account, Category, PlannedTransaction, Snapshot
from finance_manager.services.gateway import InMemoryFinanceGateway
from finance_manager.ui.app import FinanceManagerApp


NOW = datetime(2026, 7, 17, 8, 30, tzinfo=UTC)


def _gateway() -> InMemoryFinanceGateway:
    return InMemoryFinanceGateway(
        snapshot=Snapshot(
            categories=[Category("food", "Food", "expense")],
            accounts=[
                Account(
                    "cash",
                    "Cash",
                    "cash",
                    "IDR",
                    Decimal("1000"),
                    opening_date="2026-07-01",
                )
            ],
            planned_transactions=[
                PlannedTransaction(
                    "rent",
                    "expense",
                    "confirmed",
                    "2026-07-20",
                    Decimal("250"),
                    "food",
                    "cash",
                    "Rent",
                )
            ],
            settings={"base_currency": "IDR", "theme": "tokyonight"},
        ),
        clock=lambda: NOW,
    )


def test_dashboard_is_default_answer_first_and_navigation_uses_release_language() -> None:
    """
    Condition:
    The complete TUI opens with current money and an upcoming confirmed Plan.

    Expected:
    Dashboard is default, explains projections in text, and navigates to Activity and Accounts.
    """
    app = FinanceManagerApp(gateway=_gateway())

    async def exercise() -> None:
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause()
            assert "Dashboard" in str(app.query_one("#tabs", Static).render())
            sidebar = str(app.query_one("#sidebar", Static).render())
            assert "Current Balance" in sidebar
            assert "Expected" in sidebar
            assert "Confirmed" in sidebar
            assert "Budget-Safe" in sidebar
            assert app.query_one(DataTable).row_count == 1

            await pilot.press("2")
            assert "Activity" in str(app.query_one("#tabs", Static).render())

            await pilot.press("6")
            assert "Accounts" in str(app.query_one("#tabs", Static).render())
            assert app.query_one(DataTable).row_count == 1

    asyncio.run(exercise())


def test_narrow_terminal_and_theme_cycle_keep_non_color_status_text() -> None:
    """
    Condition:
    The Dashboard runs in the documented narrow fallback and the Owner cycles themes.

    Expected:
    Content remains readable and status is expressed with text independently of color.
    """
    app = FinanceManagerApp(gateway=_gateway())

    async def exercise() -> None:
        async with app.run_test(size=(60, 20)) as pilot:
            await pilot.pause()
            assert "Current Balance" in str(app.query_one("#sidebar", Static).render())
            assert "Synced" in str(app.query_one("#status", Static).render())

            await pilot.press("ctrl+t")

            assert app.visual_theme == "light"
            assert "Theme: light" in str(app.query_one("#status", Static).render())

    asyncio.run(exercise())
