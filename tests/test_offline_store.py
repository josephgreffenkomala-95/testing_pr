from __future__ import annotations

from pathlib import Path

import pytest

from finance_manager.models.entities import OfflineChange, Snapshot
from finance_manager.services.local_store import EncryptedLocalStore, KeyringKeyProvider, LocalStoreError


class FixedKeyProvider:
    def __init__(self, key: bytes | None) -> None:
        self.key = key

    def get_key(self) -> bytes | None:
        return self.key


class FakeCredentialBackend:
    def __init__(self) -> None:
        self.value: str | None = None

    def get_password(self, service: str, account: str) -> str | None:
        return self.value

    def set_password(self, service: str, account: str, value: str) -> None:
        self.value = value


def test_encrypted_store_round_trips_snapshot_and_ordered_queue(tmp_path: Path) -> None:
    """
    Condition:
    A complete local state and two Offline Changes are saved with an available key.

    Expected:
    Disk contains no financial plaintext and restart restores queue order and atomic metadata.
    """
    path = tmp_path / "offline.fm"
    store = EncryptedLocalStore(path, FixedKeyProvider(b"owner-key"))
    snapshot = Snapshot([], [], [], [], [], {"base_currency": "IDR", "private": "salary note"})
    changes = [
        OfflineChange(1, "add", "activity", "activity-1", 0, {"description": "salary note"}),
        OfflineChange(2, "complete", "plan", "plan-1", 1, {}, atomic_group="completion-1"),
    ]

    store.save(snapshot, changes, "2026-07-17T08:30:00Z")
    raw = path.read_bytes()
    restored = EncryptedLocalStore(path, FixedKeyProvider(b"owner-key")).load()

    assert b"salary note" not in raw
    assert restored.snapshot == snapshot
    assert restored.changes == changes
    assert restored.last_synced_at == "2026-07-17T08:30:00Z"


def test_encrypted_store_requires_key_or_passphrase_and_rejects_wrong_key(tmp_path: Path) -> None:
    """
    Condition:
    No credential-store key is available, then an encrypted snapshot is opened with a wrong key.

    Expected:
    There is no plaintext fallback and recovery errors are actionable.
    """
    path = tmp_path / "offline.fm"
    with pytest.raises(LocalStoreError, match="passphrase"):
        EncryptedLocalStore(path, FixedKeyProvider(None))

    EncryptedLocalStore(path, FixedKeyProvider(None), passphrase="correct horse").save(Snapshot(), [], None)

    with pytest.raises(LocalStoreError, match="unlock"):
        EncryptedLocalStore(path, FixedKeyProvider(None), passphrase="wrong horse").load()


def test_keyring_provider_creates_and_reuses_an_os_credential_key() -> None:
    """
    Condition:
    The operating-system credential backend has no offline encryption key on first access.

    Expected:
    A random key is stored there and the same key is returned after restart.
    """
    backend = FakeCredentialBackend()

    first = KeyringKeyProvider(backend).get_key()
    second = KeyringKeyProvider(backend).get_key()

    assert first is not None
    assert first == second
    assert backend.value is not None
    assert bytes(first) not in backend.value.encode()
