# Finance Manager

`finance-manager` is a single-Owner personal finance application. Its primary interface is a keyboard- and mouse-friendly Textual TUI; its durable, directly inspectable data lives in one Google Finance Sheet.

The app keeps completed financial history separate from future Plans and monthly Budgets. All amounts use one Base Currency and Python `Decimal` values. Transfers are one linked event, Balance Adjustments reconcile an Account without becoming income or expense, and normal correction workflows preserve history instead of deleting it.

## Install and launch

Python 3.9 or newer is required.

```bash
python3 -m pip install .
finance-manager
```

The default command opens the TUI. First-run Google connection, Finance Sheet creation, Base Currency selection, and first-Account setup all happen inside it; separate setup commands are not required.

Useful diagnostics remain available:

```bash
finance-manager doctor
finance-manager --no-tui
```

## First-run Google OAuth

Finance Manager uses an OAuth client owned by you. It does not ship a shared identity or send credentials to an application service.

1. Create or select a project in Google Cloud Console.
2. Enable the Google Sheets API and Google Drive API.
3. Configure the OAuth consent screen.
4. Create an OAuth client with application type **Desktop app**.
5. Download its JSON file.
6. Launch `finance-manager`, enter or select that file, and choose **Connect Google**.

The app validates that the JSON is a complete Desktop client before opening browser authorization. OAuth failures are shown as actionable UI errors without logging client secrets, tokens, or financial data.

Refresh credentials are stored in the operating-system credential store through `keyring` when one is available. If it is unavailable, the TUI discloses the fallback and stores the credential file with owner-only `0600` permissions. Credentials never enter the Finance Sheet or `config.json`.

Configuration defaults to `$XDG_CONFIG_HOME/finance-manager`, or `~/.config/finance-manager` when `XDG_CONFIG_HOME` is unset. Supported overrides are:

- `FINANCE_MANAGER_CONFIG_DIR`
- `FINANCE_MANAGER_OAUTH_CLIENT_SECRET`
- `FINANCE_MANAGER_OAUTH_TOKEN`
- `FINANCE_MANAGER_SPREADSHEET_TITLE`
- `FINANCE_MANAGER_SPREADSHEET_ID`

## Finance Sheet behavior

Creating a workspace makes a dedicated Sheet with these tabs:

- `Activity`
- `Plans`
- `Recurring Plans`
- `Plan Exceptions`
- `Budgets`
- `Categories`
- `Accounts`
- `Settings`

The first run adds editable common Categories and your first dated Account only. It never seeds fake Activity, Plans, Budgets, or balances.

Opaque IDs, versions, timestamps, and link columns are managed system fields. They support direct editing, stale-form detection, recurrence, offline synchronization, and linked Plan completion, but stay hidden from normal TUI screens. Headers are frozen and system columns are protected with warnings where the Sheets API supports them.

Direct Finance Sheet editing is an advanced supported workflow. Reload validates records independently and identifies the exact tab, row, column, and invalid value. A malformed unrelated row does not hide safe records; when a relationship could make totals unsafe, the TUI withholds those totals and explains what must be repaired. A TUI form opened on an older record version cannot overwrite a newer Sheet edit.

## Financial model

- **Accounts** have a type (`cash`, `bank`, or `e-wallet`), Base Currency, Opening Date, and Opening Balance. Current and Historical Balances are derived from non-voided Activity.
- **Activity** contains income, expenses, Transfers, and Balance Adjustments. Completed Activity cannot be future-dated or precede an Account's Opening Date. Negative balances are allowed and clearly warned.
- **Transfers** decrease one Account and increase another by the same amount. They do not change total wealth, income, expense, or Budget usage.
- **Voided Activity** keeps its original values and a required reason but no longer affects financial results.
- **Plans** may be planned or confirmed and scheduled for an exact date, calendar month, or left unscheduled. Completed and cancelled Plans remain history.
- **Recurring Plans** support weekly, monthly, and yearly frequencies. Month-end fallback preserves the requested day for later months, and Plan Exceptions change, cancel, or complete one occurrence.
- **Budgets** and **Income Targets** are unique per Category and month, cross-Account, non-rolling, and advisory.
- **Expected**, **Confirmed**, **Projected Balance Range**, and **Budget-Safe Balance** are separate answers. The Dashboard explains each in text and does not rely on a chart or color alone.

## Offline encryption and synchronization

The offline gateway stores the complete synchronized Snapshot and ordered Offline Change queue as authenticated ciphertext. A key comes from the operating-system credential store when available. Without one, an unlock passphrase is required; there is no plaintext financial-data fallback.

Offline Account, Activity, Plan, recurrence, exception, completion, and Budget mutations update local calculations immediately and are marked `PENDING SYNC`. Plan completion is queued atomically with its linked Activity. Restarting restores the same ordered pending state.

Synchronization distinguishes `Synced`, `Syncing`, `Offline`, `Pending changes`, and `Conflict`, with the last successful time when available. Non-conflicting work replays in order. A same-record collision pauses that record and exposes field-level local, Finance Sheet, or manual choices instead of last-write-wins. External deletion is treated as a conflict so Activity can be restored as Voided history and Plans as Cancelled history. Idempotent record IDs and linked completion IDs prevent duplicate retries.

If an encrypted snapshot is missing, corrupt, or cannot be unlocked, Finance Manager fails safely and asks you to reconnect or use the correct unlock secret. It never guesses at financial state.

## TUI controls

- `1` Dashboard
- `2` Activity
- `3` Plans
- `4` Budgets
- `5` Projection
- `6` Accounts
- `7` Settings & Google Sheets
- `i` add income
- `x` add expense
- `t` add Transfer
- `a` add in the current workflow
- `e` edit the selected record
- `c` complete the selected Plan
- `d` void Activity, cancel a Plan, or close an Account with confirmation
- `r` reload
- `Ctrl+S` sync now
- `Ctrl+T` cycle Tokyonight, light, and high-contrast themes
- `o` open the Finance Sheet
- `q` quit

Tokyonight is the default. Theme choice persists, focused controls use a visible border, statuses include text labels, and primary content remains readable at a 60-column narrow-terminal fallback.

## Scope limits

The first release intentionally excludes multiple Owners, shared household roles, mixed currencies and exchange rates, bank feeds, credit/loan/investment modeling, split Transactions, Category hierarchies, receipt/OCR workflows, arbitrary cron recurrence, automatic Budget rollover, fake-data onboarding, general CSV/XLSX import, and the obsolete specialized `magang` migration.

## Verification

```bash
python3 -m pytest -q
python3 -m ruff check finance_manager tests
python3 -m mypy finance_manager
```
