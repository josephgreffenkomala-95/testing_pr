from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_SPREADSHEET_TITLE = "Personal Finance Manager"


@dataclass(frozen=True)
class AppConfig:
    config_dir: Path
    config_path: Path
    oauth_client_secret_path: Path
    oauth_token_path: Path
    spreadsheet_title: str
    spreadsheet_id: str | None


def _default_config_dir() -> Path:
    override = os.environ.get("FINANCE_MANAGER_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "finance-manager"


def load_app_config() -> AppConfig:
    config_dir = _default_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.json"
    stored: dict[str, Any] = {}
    if config_path.exists():
        stored = json.loads(config_path.read_text())

    oauth_client_secret_path = Path(
        os.environ.get(
            "FINANCE_MANAGER_OAUTH_CLIENT_SECRET",
            stored.get("oauth_client_secret_path", str(config_dir / "google-oauth-client-secret.json")),
        )
    ).expanduser()
    oauth_token_path = Path(
        os.environ.get(
            "FINANCE_MANAGER_OAUTH_TOKEN",
            str(config_dir / "google-oauth-token.json"),
        )
    ).expanduser()
    spreadsheet_title = os.environ.get(
        "FINANCE_MANAGER_SPREADSHEET_TITLE",
        stored.get("spreadsheet_title", DEFAULT_SPREADSHEET_TITLE),
    )
    spreadsheet_id = os.environ.get(
        "FINANCE_MANAGER_SPREADSHEET_ID",
        stored.get("spreadsheet_id"),
    )

    return AppConfig(
        config_dir=config_dir,
        config_path=config_path,
        oauth_client_secret_path=oauth_client_secret_path,
        oauth_token_path=oauth_token_path,
        spreadsheet_title=spreadsheet_title,
        spreadsheet_id=spreadsheet_id,
    )


def persist_app_state(config: AppConfig, **updates: Any) -> None:
    current: dict[str, Any] = {}
    if config.config_path.exists():
        current = json.loads(config.config_path.read_text())
    current.setdefault("spreadsheet_title", config.spreadsheet_title)
    current.update(updates)
    if "oauth_client_secret_path" in updates:
        current["oauth_client_secret_path"] = str(updates["oauth_client_secret_path"])
    config.config_path.write_text(json.dumps(current, indent=2))
