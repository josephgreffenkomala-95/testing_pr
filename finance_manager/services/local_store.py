from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from cryptography.fernet import Fernet, InvalidToken

from finance_manager.models.entities import OfflineChange, Snapshot
from finance_manager.models.schemas import snapshot_from_dict, snapshot_to_dict


MAGIC = b"FM1"


class LocalStoreError(Exception):
    pass


class KeyProvider(Protocol):
    def get_key(self) -> bytes | None: ...


class CredentialBackend(Protocol):
    def get_password(self, service: str, account: str) -> str | None: ...

    def set_password(self, service: str, account: str, value: str) -> None: ...


class KeyringKeyProvider:
    def __init__(self, backend: CredentialBackend | None = None) -> None:
        if backend is None:
            try:
                import keyring
            except ImportError:
                self._backend = None
            else:
                self._backend = keyring
        else:
            self._backend = backend

    def get_key(self) -> bytes | None:
        if self._backend is None:
            return None
        try:
            stored = self._backend.get_password("finance-manager", "offline-encryption")
            if stored:
                return base64.urlsafe_b64decode(stored.encode())
            key = secrets.token_bytes(32)
            self._backend.set_password(
                "finance-manager",
                "offline-encryption",
                base64.urlsafe_b64encode(key).decode(),
            )
            return key
        except Exception:
            return None


@dataclass(frozen=True)
class LocalState:
    snapshot: Snapshot
    changes: list[OfflineChange]
    last_synced_at: str | None


class EncryptedLocalStore:
    def __init__(
        self,
        path: Path,
        key_provider: KeyProvider,
        *,
        passphrase: str | None = None,
    ) -> None:
        key = key_provider.get_key()
        if key is None and not passphrase:
            raise LocalStoreError("Unlock passphrase is required because no credential-store key is available.")
        self.path = path
        if key is not None:
            self._secret = key
        else:
            if passphrase is None:
                raise LocalStoreError("Unlock passphrase is required because no credential-store key is available.")
            self._secret = passphrase.encode()

    @property
    def exists(self) -> bool:
        return self.path.exists()

    def save(
        self,
        snapshot: Snapshot,
        changes: list[OfflineChange],
        last_synced_at: str | None,
    ) -> None:
        salt = os.urandom(16)
        payload = {
            "snapshot": snapshot_to_dict(snapshot),
            "changes": [asdict(change) for change in changes],
            "last_synced_at": last_synced_at,
        }
        plaintext = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        token = Fernet(self._derive_key(salt)).encrypt(plaintext)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_bytes(MAGIC + salt + token)
        temporary.chmod(0o600)
        temporary.replace(self.path)

    def load(self) -> LocalState:
        if not self.path.exists():
            raise LocalStoreError("No offline snapshot is available. Connect once to create it.")
        raw = self.path.read_bytes()
        if not raw.startswith(MAGIC) or len(raw) <= len(MAGIC) + 16:
            raise LocalStoreError("The offline snapshot is corrupted. Reconnect to replace it.")
        salt = raw[len(MAGIC) : len(MAGIC) + 16]
        token = raw[len(MAGIC) + 16 :]
        try:
            plaintext = Fernet(self._derive_key(salt)).decrypt(token)
            payload = json.loads(plaintext)
        except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LocalStoreError("Could not unlock the offline snapshot. Check the key or passphrase.") from exc
        return LocalState(
            snapshot_from_dict(payload["snapshot"]),
            [OfflineChange(**item) for item in payload.get("changes", [])],
            payload.get("last_synced_at"),
        )

    def _derive_key(self, salt: bytes) -> bytes:
        derived = hashlib.pbkdf2_hmac("sha256", self._secret, salt, 600_000, dklen=32)
        return base64.urlsafe_b64encode(derived)
