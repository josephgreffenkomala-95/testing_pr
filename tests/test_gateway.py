from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

from textual.widgets import DataTable, Static

from finance_manager.models.entities import Account, Category, Snapshot
from finance_manager.services.gateway import FinanceGateway, InMemoryFinanceGateway
from finance_manager.ui.app import FinanceManagerApp


FIXED_NOW = datetime(2026, 7, 17, 8, 30, tzinfo=UTC)


def _snapshot() -> Snapshot:
    return Snapshot(
        transactions=[],
        planned_transactions=[],
        budgets=[],
        categories=[Category("category-1", "Groceries", "expense")],
        accounts=[Account("account-1", "Cash", "cash", "IDR", Decimal("1000.00"))],
        settings={},
    )


def test_in_memory_gateway_uses_injected_clock_and_record_id() -> None:
    """
    Condition:
    An in-memory gateway receives deterministic clock and record-ID test doubles.

    Expected:
    A new Transaction uses the supplied ID and UTC timestamp.
    """
    gateway = InMemoryFinanceGateway(
        snapshot=_snapshot(),
        clock=lambda: FIXED_NOW,
        record_id_generator=lambda prefix: f"{prefix}-fixed",
    )

    transaction = gateway.add_transaction(
        {
            "entry_type": "expense",
            "date": "2026-07-17",
            "amount": "125.50",
            "category": "Groceries",
            "description": "Lunch",
            "account": "Cash",
            "notes": "",
        }
    )

    assert isinstance(gateway, FinanceGateway)
    assert transaction.id == "ACT-fixed"
    assert transaction.created_at == "2026-07-17T08:30:00Z"
    assert gateway.load_snapshot().transactions == [transaction]


def test_tui_runs_through_pilot_with_in_memory_gateway() -> None:
    """
    Condition:
    The Textual app is launched with a configured in-memory Finance Gateway.

    Expected:
    The pilot renders gateway data and can navigate to the Accounts view.
    """
    gateway = InMemoryFinanceGateway(snapshot=_snapshot(), clock=lambda: FIXED_NOW)
    app = FinanceManagerApp(gateway=gateway)

    async def exercise_app() -> None:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert app.query_one(DataTable).row_count == 0
            assert "Ready." in str(app.query_one("#status", Static).render())

            await pilot.press("6")

            assert app.query_one(DataTable).row_count == 1
            assert "Accounts" in str(app.query_one("#tabs", Static).render())

    asyncio.run(exercise_app())
