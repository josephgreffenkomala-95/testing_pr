---
name: pr-revise
description: Monitor a PR for new review comments, analyze changes with a powerful model, and implement fixes after your approval. Trigger on PR revision, review comments, or watching a PR.
---

# PR Revise Skill

## Auto Review PR Orchestrator Boundaries

When this skill is invoked by the `auto-review-pr` application, the Python
orchestrator owns workflow state and external side effects.

Supported orchestrated modes:

- **Planning mode**: analyze only. Produce the requested revision-plan markdown
  with summary, file changes, one reply per reviewer comment, commit message,
  and `READY_TO_APPLY` or `NEEDS_DISCUSSION`. Do not edit files.
- **Apply mode**: edit files only for the approved file changes supplied by the
  parent prompt. Do not produce review markdown.
- **Review-draft feedback mode**: help revise an existing review draft when the
  parent prompt asks for draft feedback, preserving that review-draft format.

In orchestrated planning/apply mode, do not run the infinite loop below, do not
ask for terminal approval, do not commit, do not push, do not reply to review
comments, do not resolve threads, and do not update `.opencode/state`.

## Prerequisites

- `gh` CLI installed and authenticated (`gh auth status` must pass)
- Git repo with GitHub remote
- `gh-cli`, `code-writer`, and `git-commit` skills available
- Working directory on the PR's branch

## State File

`.opencode/state/pr-revise.json` — prevents re-processing reviews:

```json
{
  "repo": "owner/repo",
  "branch": "feature/auth-fix",
  "last_check": "2026-04-30T10:00:00Z",
  "known_review_ids": ["review-id-abc"],
  "last_pr_state": "draft",
  "draft_cycle_count": 0,
  "next_sleep_seconds": 1800
}
```

Create if missing. Read at start of every cycle.

## Workflow — Infinite Loop

No stop command. Runs until the OpenCode process is killed (Esc / close terminal).

### 1. Detect repo & branch

```bash
git rev-parse --abbrev-ref HEAD
git remote get-url origin   # extract owner/repo
```

On failure: print error, sleep anyway.

### 2. Poll GitHub (via `gh` CLI)

Load the `gh-cli` skill and use its branch-matching fetch pattern.

- Find the open PR matching the current branch with `gh pr list --state open --head "$BRANCH" ...`
- Detect whether the PR is **draft** or **ready for review / open** from `isDraft`
- Fetch reviews with `gh pr view <number> --json ...`
- Fetch line-level review comments with `gh api repos/{owner}/{repo}/pulls/<number>/comments --jq ...`

Prefer compact `--json` + `--jq` output to reduce token usage.

### 3. Diff reviews

Compare fetched review IDs against `known_review_ids`.

**No new reviews** → print confirmation, go to Step 7.

**New reviews** → continue.

### 4. Analyze (delegate to `pr-analyzer` subagent)

**You MUST use the `task` tool** to invoke the pr-analyzer subagent. Do NOT attempt to analyze reviews yourself.

```
task(
  subagent_type: "pr-analyzer",
  description: "Analyze PR review comments",
  prompt: "Analyze the following PR review and draft an implementation plan.

PR #<number>: <title>
Branch: <branch>
Repo: <owner/repo>

Review comments:
<grouped comments with file paths, line numbers, and comment bodies>

PR diff:
<the full diff or changed files>

You must:
1. Map each comment to specific code locations
2. Draft implementation plan with exact file paths & changes
3. Self-critique: edge cases? missing comments? regressions? misinterpretations?
4. Produce final revised plan + a specific reply per comment (what changed, where)
5. Return plan + replies"
)
```

The pr-analyzer will return an implementation plan and per-comment replies. Use these in Steps 5 and 6.

### 5. Present plan & ask approval

```
=== PR #42 — REVISED PLAN ===
1. src/auth.ts:45 — Add null check in `validate()`
2. tests/auth.spec.ts:12 — Update test case
===============================
Approve? (yes / revise / skip)
```

Wait for exact input. Options:
- **yes** — implement
- **revise** — send user feedback back to Step 4
- **skip** — mark reviews as known, sleep

### 6. Execute (if approved)

1. **Delegate plan to `code-writer` subagent** — Use the `task` tool:
   ```
   task(
     subagent_type: "code-writer",
     description: "Implement PR review fixes",
     prompt: "Implement the following changes for PR #<number>:\n\n<plan from pr-analyzer>"
   )
   ```
2. Load `git-commit` skill, auto-generate commit message
3. `git push`
4. Load the `gh-cli` skill and reply to each review comment with `gh api repos/{owner}/{repo}/pulls/<number>/comments/<comment_id>/replies --method POST -f body=...`. **Do NOT resolve threads.**
5. Append processed review IDs to `known_review_ids`
6. Write state file

### 7. Sleep

Use a **flexible polling interval** based on PR state:

- **Draft PR**
  - First draft cycle: sleep **1800s** (30 min)
  - Each new draft cycle: add **900s** (15 min)
  - Example: 30 min → 45 min → 60 min → 75 min
- **Ready for review / open PR**
  - Always sleep **300s** (5 min)

Rules:
- If the PR transitions from **open → draft**, reset draft backoff to the first draft cycle (`draft_cycle_count = 0`, `next_sleep_seconds = 1800`).
- If the PR transitions from **draft → open**, switch immediately to `next_sleep_seconds = 300` and stop increasing backoff.
- Increment `draft_cycle_count` only after a completed draft cycle.
- Persist `last_pr_state`, `draft_cycle_count`, and `next_sleep_seconds` in the state file before sleeping.

Then run:

```bash
sleep <next_sleep_seconds>
```

After waking up, return to Step 1.

## Error Handling

| Failure | Action |
|---|---|
| `gh` unavailable / auth failed | Print error, sleep |
| pr-analyzer fails | Ask user: retry or skip |
| code-writer fails | Ask user: retry or abort |
| git-commit skill fails | Ask user: commit manually or abort |

Always write state file before sleeping.

If no PR is found for the branch, print an error and use the conservative open-PR interval (`sleep 300`) unless the existing state file already indicates an active draft backoff you intentionally want to preserve.

## Design Rationale

- **Infinite loop, no stop check** — daemon stops only when process is killed
- **Cheap orchestrator** — only runs compact `gh` queries, diffs IDs, delegates; expensive reasoning lives in pr-analyzer subagent
- **Approval gate** — no edits/commits/push without explicit `yes`
- **Specific replies** — each comment gets a tailored response referencing exact changes
- **Adaptive polling** — draft PRs usually need less frequent checks, while open PRs should be watched closely
