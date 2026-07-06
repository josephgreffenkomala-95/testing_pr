# Finance Manager

`finance-manager` is a personal finance CLI application with a Textual TUI and Google Sheets as its storage backend. On first run it can create the spreadsheet automatically, initialize a normalized multi-sheet structure, and then use that sheet as the app database.

## Features

- Track income and expenses with date, amount, category, description, account, and optional notes.
- Manage planned transactions with optional dates and statuses: `planned`, `confirmed`, `completed`, `cancelled`.
- Maintain monthly budgets per category and compare actual and planned spending against them.
- View a balance timeline and monthly cash projection from current account balances plus planned cash movements.
- Keep the data inspectable in Google Sheets with separate tabs for `Transactions`, `Planned Transactions`, `Budgets`, `Categories`, `Accounts`, and `Settings`.

## Installation

```bash
python3 -m pip install .
```

After installation, launch the app from anywhere with:

```bash
finance-manager
```

You can also run health checks or initialize the sheet without opening the TUI:

```bash
finance-manager doctor
finance-manager init
```

## Google Sheets Authentication

The app uses OAuth for an installed desktop app, so it can act as your own Google account after you sign in once.

1. Create a Google Cloud project.
2. Enable the Google Sheets API and Google Drive API.
3. Configure the OAuth consent screen.
4. Create an OAuth client of type `Desktop app`.
5. Download the client JSON file.
6. Place that file at:

```text
~/.config/finance-manager/google-oauth-client-secret.json
```

7. Run:

```bash
finance-manager auth
```

That opens a browser-based Google login and stores your refreshable token at:

```text
~/.config/finance-manager/google-oauth-token.json
```

You can override the paths with:

- `FINANCE_MANAGER_OAUTH_CLIENT_SECRET`
- `FINANCE_MANAGER_OAUTH_TOKEN`

Optional environment variables:

- `FINANCE_MANAGER_CONFIG_DIR`
- `FINANCE_MANAGER_SPREADSHEET_TITLE`
- `FINANCE_MANAGER_SPREADSHEET_ID`

The app stores local state in `~/.config/finance-manager/config.json`, including the last known spreadsheet ID.

After `finance-manager auth`, run:

```bash
finance-manager init
finance-manager
```

## Google Sheet Layout

The app ensures the following tabs exist with fixed headers:

- `Transactions`
- `Planned Transactions`
- `Budgets`
- `Categories`
- `Accounts`
- `Settings`

The schema is normalized: records store `category_id` and `account_id`, while the corresponding lookup tables remain editable and easy to inspect manually.

## TUI Controls

- `1` Transactions
- `2` Planned transactions
- `3` Budgets
- `4` Projection
- `5` Setup / status
- `a` Add record in the current view
- `e` Edit selected record
- `d` Delete selected record
- `r` Reload from Google Sheets
- `q` Quit

## Error Handling

The app includes explicit handling for:

- missing OAuth client credentials
- missing or expired OAuth token
- import/authentication failures
- network/API errors
- invalid worksheet headers
- empty database state

If credentials are missing or invalid, the TUI opens in a setup/error state with instructions instead of crashing.
