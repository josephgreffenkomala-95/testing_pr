from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from finance_manager.config.settings import AppConfig


if TYPE_CHECKING:
    from google.oauth2.credentials import Credentials


GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
SERVICE_NAME = "finance-manager"
ACCOUNT_NAME = "google-oauth"


class CredentialStore(Protocol):
    disclosure: str

    def load(self) -> str | None: ...

    def save(self, value: str) -> None: ...


class FileCredentialStore:
    disclosure = "The operating-system credential store is unavailable; credentials use an owner-only local file."

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> str | None:
        return self.path.read_text() if self.path.exists() else None

    def save(self, value: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(mode=0o600, exist_ok=True)
        self.path.chmod(0o600)
        self.path.write_text(value)
        self.path.chmod(0o600)


class KeyringCredentialStore:
    disclosure = "Refresh credentials are protected by the operating-system credential store."

    def __init__(self) -> None:
        import keyring

        self._keyring = keyring

    def load(self) -> str | None:
        return self._keyring.get_password(SERVICE_NAME, ACCOUNT_NAME)

    def save(self, value: str) -> None:
        self._keyring.set_password(SERVICE_NAME, ACCOUNT_NAME, value)


def credential_store(config: AppConfig) -> CredentialStore:
    try:
        store = KeyringCredentialStore()
        store.load()
    except Exception:
        return FileCredentialStore(config.oauth_token_path)
    return store


def validate_oauth_client_file(path: Path) -> Path:
    if not path.exists():
        raise ValueError(f"OAuth client file was not found: {path}")
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("OAuth client file must contain valid JSON.") from exc
    if "installed" not in payload:
        raise ValueError("Select a Google OAuth client JSON created for a Desktop app.")
    installed = payload["installed"]
    if not isinstance(installed, dict) or not installed.get("client_id") or not installed.get("client_secret"):
        raise ValueError("Desktop OAuth JSON must contain client_id and client_secret.")
    return path


def ensure_client_secret_file(config: AppConfig) -> Path:
    try:
        return validate_oauth_client_file(config.oauth_client_secret_path)
    except ValueError as exc:
        raise FileNotFoundError(str(exc)) from exc


def load_oauth_credentials(
    config: AppConfig,
    store: CredentialStore | None = None,
) -> Credentials:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    selected_store = store or credential_store(config)
    raw = selected_store.load()
    if raw:
        try:
            credentials = Credentials.from_authorized_user_info(json.loads(raw), GOOGLE_SCOPES)
        except (ValueError, json.JSONDecodeError) as exc:
            raise FileNotFoundError("Stored OAuth credentials are invalid. Connect Google again.") from exc
        if credentials.valid:
            return credentials
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            selected_store.save(credentials.to_json())
            return credentials
    raise FileNotFoundError("Google is not connected. Use Connect Google in Finance Manager.")


def run_oauth_flow(
    config: AppConfig,
    store: CredentialStore | None = None,
) -> Path:
    from google_auth_oauthlib.flow import InstalledAppFlow

    client_secret_path = ensure_client_secret_file(config)
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), GOOGLE_SCOPES)
    credentials = flow.run_local_server(port=0, open_browser=True)
    selected_store = store or credential_store(config)
    selected_store.save(credentials.to_json())
    return config.oauth_token_path
