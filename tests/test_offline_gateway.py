from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from finance_manager.services.gateway import InMemoryFinanceGateway, OfflineFinanceGateway
from finance_manager.services.local_store import EncryptedLocalStore


class FixedKeyProvider:
    def get_key(self) -> bytes:
        return b"offline-test-key"


NOW = datetime(2026, 7, 17, 8, 30, tzinfo=UTC)


def _store(path: Path) -> EncryptedLocalStore:
    return EncryptedLocalStore(path, FixedKeyProvider())


def _gateway(path: Path) -> OfflineFinanceGateway:
    gateway = OfflineFinanceGateway(local_store=_store(path), clock=lambda: NOW)
    gateway.add_account(
        {
            "name": "Cash",
            "account_type": "cash",
            "currency": "IDR",
            "opening_date": "2026-07-01",
            "opening_balance": "1000",
        }
    )
    return gateway


def test_offline_activity_is_pending_and_survives_restart(tmp_path: Path) -> None:
    """
    Condition:
    An expense is recorded while offline and the application restarts before synchronization.

    Expected:
    The encrypted queue and pending Activity reconstruct the same local financial state in order.
    """
    path = tmp_path / "offline.fm"
    gateway = _gateway(path)
    activity = gateway.add_transaction(
        {
            "entry_type": "expense",
            "date": "2026-07-17",
            "amount": "125",
            "category": "Food",
            "account": "Cash",
            "description": "Lunch",
        }
    )

    restarted = OfflineFinanceGateway(local_store=_store(path), clock=lambda: NOW)

    assert activity.pending_sync is True
    assert restarted.sync_status == "Pending changes"
    assert [change.sequence for change in restarted.offline_changes] == [1, 2]
    assert restarted.load_snapshot().transactions[0].description == "Lunch"
    assert restarted.load_snapshot().transactions[0].pending_sync is True


def test_offline_plan_completion_queues_one_atomic_change(tmp_path: Path) -> None:
    """
    Condition:
    A Plan is created and completed offline into linked Activity.

    Expected:
    Completion persists as one atomic queue item linking the Activity and Completed Plan.
    """
    gateway = _gateway(tmp_path / "offline.fm")
    plan = gateway.add_planned_transaction(
        {
            "entry_type": "expense",
            "status": "confirmed",
            "schedule_precision": "exact",
            "expected_date": "2026-07-17",
            "amount": "100",
            "category": "Food",
            "account": "Cash",
            "description": "Dinner",
        }
    )

    gateway.complete_plan(
        plan.id,
        {
            "date": "2026-07-17",
            "amount": "110",
            "category": "Food",
            "account": "Cash",
            "description": "Dinner",
        },
    )

    completion = gateway.offline_changes[-1]
    assert completion.operation == "complete"
    assert completion.atomic_group
    assert completion.payload["plan_id"] == plan.id
    assert completion.payload["activity_id"] == gateway.load_snapshot().transactions[0].id


def test_sync_replays_non_conflicts_and_resolves_field_level_collision(tmp_path: Path) -> None:
    """
    Condition:
    Pending changes reconnect once without collision, then a local edit collides with a Sheet-side edit.

    Expected:
    Replay clears pending state; collision pauses only that record and supports per-field local/Sheet choices.
    """
    path = tmp_path / "offline.fm"
    local = _gateway(path)
    activity = local.add_transaction(
        {
            "entry_type": "expense",
            "date": "2026-07-17",
            "amount": "125",
            "category": "Food",
            "account": "Cash",
            "description": "Lunch",
        }
    )
    remote = InMemoryFinanceGateway(clock=lambda: NOW)

    local.synchronize(remote)

    assert local.sync_status == "Synced"
    assert local.offline_changes == []
    assert remote.get_transaction(activity.id).pending_sync is False

    local.set_online(False)
    local.update_transaction(
        activity.id,
        {
            "entry_type": "expense",
            "date": "2026-07-17",
            "amount": "130",
            "category": "Food",
            "account": "Cash",
            "description": "Local lunch",
        },
    )
    remote.update_transaction(
        activity.id,
        {
            "entry_type": "expense",
            "date": "2026-07-17",
            "amount": "140",
            "category": "Food",
            "account": "Cash",
            "description": "Sheet lunch",
        },
    )

    conflicts = local.synchronize(remote)

    assert local.sync_status == "Conflict"
    assert set(conflicts[0].fields) >= {"amount", "description"}

    local.resolve_conflict(
        conflicts[0],
        {"amount": "local", "description": "sheet"},
        remote,
    )

    resolved = remote.get_transaction(activity.id)
    assert resolved.amount == local.get_transaction(activity.id).amount
    assert resolved.description == "Sheet lunch"
    assert local.sync_status == "Synced"


def test_sync_detects_direct_deletion_and_restores_cancelled_or_voided_history(tmp_path: Path) -> None:
    """
    Condition:
    Synchronized Activity is physically deleted from the remote Finance Sheet.

    Expected:
    Reconnect reports deletion and restoration recreates it as Voided history.
    """
    local = _gateway(tmp_path / "offline.fm")
    activity = local.add_transaction(
        {
            "entry_type": "expense",
            "date": "2026-07-17",
            "amount": "25",
            "category": "Food",
            "account": "Cash",
            "description": "History",
        }
    )
    remote = InMemoryFinanceGateway(clock=lambda: NOW)
    local.synchronize(remote)
    remote._snapshot = replace(remote.load_snapshot(), transactions=[])

    conflicts = local.synchronize(remote)

    assert conflicts[0].fields == {"deleted": ("restore historical record", "deleted from Finance Sheet")}

    local.restore_deleted(conflicts[0], remote)

    restored = remote.get_transaction(activity.id)
    assert restored.is_voided is True
    assert "direct Finance Sheet deletion" in restored.void_reason
