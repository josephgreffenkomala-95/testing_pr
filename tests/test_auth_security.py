from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from finance_manager.config.auth import FileCredentialStore, validate_oauth_client_file


def test_oauth_client_validation_accepts_desktop_and_rejects_web_or_secretless_files(tmp_path: Path) -> None:
    """
    Condition:
    Desktop, web, and incomplete OAuth client JSON files are selected during setup.

    Expected:
    Only a complete Desktop client is accepted before browser authorization.
    """
    desktop = tmp_path / "desktop.json"
    web = tmp_path / "web.json"
    incomplete = tmp_path / "incomplete.json"
    desktop.write_text(json.dumps({"installed": {"client_id": "client", "client_secret": "secret"}}))
    web.write_text(json.dumps({"web": {"client_id": "client", "client_secret": "secret"}}))
    incomplete.write_text(json.dumps({"installed": {"client_id": "client"}}))

    assert validate_oauth_client_file(desktop) == desktop
    with pytest.raises(ValueError, match="Desktop"):
        validate_oauth_client_file(web)
    with pytest.raises(ValueError, match="client_secret"):
        validate_oauth_client_file(incomplete)


def test_local_credential_fallback_is_permission_restricted(tmp_path: Path) -> None:
    """
    Condition:
    The operating-system credential store is unavailable and OAuth credentials use local fallback.

    Expected:
    The token is saved with owner-only permissions and can be loaded without entering app config.
    """
    path = tmp_path / "credentials.json"
    store = FileCredentialStore(path)

    store.save('{"refresh_token":"private"}')

    assert store.load() == '{"refresh_token":"private"}'
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
