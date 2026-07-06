from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from .settings import AppConfig


if TYPE_CHECKING:
    from google.oauth2.credentials import Credentials


GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def ensure_client_secret_file(config: AppConfig) -> Path:
    if not config.oauth_client_secret_path.exists():
        raise FileNotFoundError(
            "OAuth client credentials were not found at "
            f"{config.oauth_client_secret_path}."
        )
    return config.oauth_client_secret_path


def load_oauth_credentials(config: AppConfig) -> "Credentials":
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    if config.oauth_token_path.exists():
        credentials = Credentials.from_authorized_user_file(
            str(config.oauth_token_path),
            GOOGLE_SCOPES,
        )
        if credentials.valid:
            return credentials
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            config.oauth_token_path.write_text(credentials.to_json())
            return credentials

    raise FileNotFoundError(
        "OAuth token was not found or is no longer usable. Run `finance-manager auth` "
        f"after placing your OAuth client file at {config.oauth_client_secret_path}."
    )


def run_oauth_flow(config: AppConfig) -> Path:
    from google_auth_oauthlib.flow import InstalledAppFlow

    client_secret_path = ensure_client_secret_file(config)
    flow = InstalledAppFlow.from_client_secrets_file(
        str(client_secret_path),
        GOOGLE_SCOPES,
    )
    credentials = flow.run_local_server(port=0)
    config.oauth_token_path.write_text(credentials.to_json())
    return config.oauth_token_path
