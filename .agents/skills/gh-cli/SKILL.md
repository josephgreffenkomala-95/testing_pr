---
name: gh-cli
description: Use the GitHub CLI (`gh`) instead of GitHub MCP tools for all pull-request operations. Make sure to use this skill whenever the user needs to create a PR, open a pull request, fetch PR reviews/comments, check review feedback, reply to review thread comments, leave PR comments, approve a PR, request changes, or view a PR diff. Also trigger when the user mentions `gh` CLI, GitHub CLI, reducing token usage, avoiding MCP JSON schemas, or specifically asks to use command-line tools for GitHub pull request tasks. This skill is exclusively for PR workflows and should NOT be used for creating issues, managing repositories, searching code, or GitHub Actions workflows.
triggers:
  - gh cli
  - github cli
  - check pr
  - show pr
  - pr comments
  - pr reviews
  - review comments
  - fetch pr
  - get pr
  - pr feedback
  - token usage
  - reduce tokens
  - avoid mcp
  - gh-pr-fmt
---

# GitHub CLI PR Skill

## Overview

This skill replaces the built-in GitHub MCP tools (`Github_create_pull_request`, `Github_pull_request_read`, `Github_add_reply_to_pull_request_comment`, etc.) with native `gh` CLI commands via the `bash` tool.

**Why use this?** The `gh` CLI produces shorter, plain-text output compared to verbose MCP JSON schemas/responses. This reduces token consumption when the task is strictly about creating PRs, viewing comments, or replying to review threads.

**Prerequisites:**
- `gh` CLI installed and authenticated (`gh auth status` must pass).
- Current working directory inside a git repo with a GitHub remote, OR explicit `--repo owner/repo` flag used.

## Important Distinction: Two Types of Comments

GitHub PRs have two completely separate comment systems. Using the wrong command will create the wrong type of comment.

| Type | What it is | `gh` command |
|------|-----------|-------------|
| **Timeline / Issue comment** | General comment on the PR conversation tab | `gh pr comment <number> --body "..."` |
| **Review thread comment** | Comment tied to a specific line in the diff | `gh api repos/.../pulls/.../comments/.../replies` |

Do not use `gh pr comment` when the user asks you to reply to a review comment on a specific line. That command always creates a timeline comment.

---

## Workflow 1: Create a Pull Request

Use `gh pr create`.

### Basic creation
```bash
gh pr create --title "feat: add user authentication" --body "Implemented JWT-based auth flow."
```

### With explicit base branch and repo
```bash
gh pr create --repo owner/repo --base main --head feature-branch \
  --title "feat: add auth" --body "Details here..."
```

### Read body from file
```bash
gh pr create --title "feat: add auth" --body-file pr_description.md
```

### Auto-fill from commits
```bash
gh pr create --fill
```

### Draft PR
```bash
gh pr create --draft --title "WIP: refactor" --body "Still in progress"
```

### Useful flags
- `--base <branch>` — target branch (default: repo default branch)
- `--head <branch>` — source branch (default: current branch)
- `--reviewer <user>` — request reviewer
- `--label <name>` — add labels
- `--assignee <login>` — assign users (use `@me` for self)
- `--draft` — mark as draft
- `--no-maintainer-edit` — prevent maintainers from pushing to your branch
- `--dry-run` — preview without creating

**Output:** On success, `gh` prints the created PR URL. Capture it from the command output.

---

## Workflow 2: Fetch PR Reviews and Comments

### Default: Use gh-pr-fmt.sh (Recommended for all PR review/comment fetching)

**This is the primary method for fetching PR information.** The `gh-pr-fmt.sh` script produces a clean, structured markdown output that is optimized for LLM consumption with ~95% fewer tokens than raw JSON.

```bash
# From within a git repo
~/.agents/skills/gh-cli/scripts/gh-pr-fmt.sh <pr-number>

# Or specify repo explicitly
~/.agents/skills/gh-cli/scripts/gh-pr-fmt.sh 42 --repo owner/repo
```

**When to use this:**
- ✅ **Always use this first** when asked to check PR comments, reviews, or threads
- ✅ When you need the complete PR context (description + reviews + threads + timeline comments)
- ✅ For monitoring PRs, analyzing review feedback, or preparing responses
- ✅ Any time token efficiency matters (which is always)

**Output format:**
```markdown
# PR #42: feat: add authentication
OPEN • Draft • feat/auth → main • Review: CHANGES_REQUESTED

## Description
JWT-based authentication with refresh tokens...

## Review rev_abc123 — @reviewer1 (CHANGES_REQUESTED)
Please add better error handling.

### Thread on src/auth.ts:42 by @reviewer1
This should handle token expiration.
  ↳ **@author**: Fixed in commit abc123.

## Timeline Comments
- **@user3**: When is this going out?
```

**Token savings:** ~95% reduction vs raw JSON (e.g., 262KB → 13KB for PR #6 in cpi-anomaly-detection)

---

### Alternative: Direct gh commands (Use only for specific edge cases)

Use these only when you need:
- Specific fields not included in the formatted output
- Raw JSON for programmatic processing
- Quick checks without full context

### Find the PR for the current branch
Use this when a workflow needs to monitor or update the PR associated with the checked-out branch.

```bash
BRANCH=$(git rev-parse --abbrev-ref HEAD)
gh pr list --state open --head "$BRANCH" \
  --json number,title,isDraft,headRefName,baseRefName,reviewDecision,url \
  --jq '.[0]'
```

If you need repo-scoped lookup outside the current directory:

```bash
BRANCH=$(git rev-parse --abbrev-ref HEAD)
gh pr list --repo owner/repo --state open --head "$BRANCH" \
  --json number,title,isDraft,headRefName,baseRefName,reviewDecision,url \
  --jq '.[0]'
```

This returns the matching PR for the branch, including whether it is a **draft** (`isDraft: true`) or a regular open PR (`isDraft: false`).

### Minimal polling fetch for automation
For polling loops, prefer a compact fetch that includes PR state, reviews, and line comments with only the fields you need:

```bash
gh pr view 42 --json number,title,isDraft,reviews,comments,reviewDecision \
  --jq '{number, title, isDraft, reviewDecision, reviews: [.reviews[] | {id: .id, author: .author.login, state: .state, body: .body}], comments: [.comments[] | {id: .id, author: .author.login, body: .body}]}'

gh api repos/{owner}/{repo}/pulls/42/comments \
  --jq '[.[] | {id: .id, body: .body, path: .path, line: .line, user: .user.login, in_reply_to_id: .in_reply_to_id, pull_request_review_id: .pull_request_review_id}]'
```

Use the first command for PR metadata + review summaries, and the second command for line-level review thread comments.

### View PR metadata
```bash
gh pr view 42
```

### View with timeline comments
```bash
gh pr view 42 --comments
```

### Get structured JSON output (for programmatic parsing)
```bash
gh pr view 42 --json number,title,body,state,isDraft,reviews,comments,reviewDecision
```

### Filter specific fields with jq
```bash
gh pr view 42 --json reviews,isDraft --jq '{isDraft, reviews: [.reviews[] | {author: .author.login, state: .state, body: .body}]}'
```

### Get the PR diff
```bash
gh pr diff 42
```

### List review comments on a PR (line-level comments in review threads)
```bash
gh api repos/{owner}/{repo}/pulls/42/comments
```

To get only specific fields and reduce token usage:
```bash
gh api repos/{owner}/{repo}/pulls/42/comments --jq '.[] | {id: .id, body: .body, path: .path, line: .line, user: .user.login, in_reply_to_id: .in_reply_to_id}'
```

### List timeline/issue comments on a PR
```bash
gh api repos/{owner}/{repo}/issues/42/comments --jq '.[] | {id: .id, user: .user.login, body: .body}'
```

**Note:** `gh pr view --comments` shows a combined view. If you need to distinguish between timeline comments and review thread comments, use the `gh api` commands above.

---

## Workflow 3: Reply to Review Thread Comments

This is the most common point of confusion. `gh` has **no native command** for replying to a specific line-level review comment. You must use `gh api`.

### Reply to a review comment
```bash
gh api repos/{owner}/{repo}/pulls/42/comments/987654321/replies \
  --method POST \
  -f body="Fixed in commit abc123. Please re-check."
```

Where `987654321` is the `id` of the review comment you are replying to. This must be a top-level review comment, not a reply to a reply.

### Parameters
- `{owner}` and `{repo}` are auto-populated from the current directory's remote if not quoted.
- `42` — the PR number.
- `987654321` — the review comment `id` (numeric, found via `gh api repos/{owner}/{repo}/pulls/42/comments`).
- `--method POST` is required.
- `-f body='...'` sends the reply text.

### Important rules
1. You **must** know the `comment_id` of the review comment. Fetch it first via `gh api repos/{owner}/{repo}/pulls/<number>/comments`.
2. The `comment_id` must be a **top-level review comment** (where `in_reply_to_id` is `null`), not an existing reply.
3. When using `in_reply_to`, the API ignores all other parameters except `body`. You do not need to specify `commit_id`, `path`, `line`, etc.

---

## Workflow 4: Add a Timeline Comment (General PR Comment)

If the user wants to leave a general comment on the PR (not a reply to a line-level review), use:

```bash
gh pr comment 42 --body "All tests pass. Ready for merge."
```

Or from a file:
```bash
gh pr comment 42 --body-file comment.md
```

This appears in the main PR conversation tab.

---

## Workflow 5: Submit a PR Review

To approve, request changes, or leave a review-level comment (not a thread reply):

```bash
# Approve
gh pr review 42 --approve

# Request changes with body
gh pr review 42 --request-changes --body "Needs more tests"

# Leave a review comment
gh pr review 42 --comment --body "Looks good overall"
```

This creates a **review**, which is different from a review thread reply. Reviews are aggregate states (APPROVE, REQUEST_CHANGES, COMMENT). They do not target specific lines.

---

## Common Flags for All Commands

- `-R, --repo <[HOST/]OWNER/REPO>` — operate on a different repo without changing directory
- `--jq <expression>` — filter JSON responses using jq syntax (reduces token usage dramatically)
- `--silent` — suppress output (useful when you only care about exit status)
- `-i, --include` — include HTTP headers in `gh api` output

---

## Token-Saving Patterns

1. **Use `gh-pr-fmt.sh`** for fetching complete PR context (reviews, comments, threads) - produces ~60% fewer tokens than raw JSON.
2. **Always use `--jq`** when calling `gh api` or `gh pr view --json` to return only the fields you need.
3. **Prefer `gh pr view --comments`** over separate `gh api` calls for simple inspection.
4. **Use `--silent`** for destructive operations (merge, close) if you don't need the response body.

---

## Error Handling

| Error | Likely cause | Action |
|-------|-------------|--------|
| `gh: HTTP 404` | PR or comment does not exist | Verify PR number and comment ID |
| `gh: HTTP 403` | Insufficient permissions | Check `gh auth status` and token scopes |
| `gh: HTTP 422` | Validation failed (e.g., reply to a reply) | Ensure `comment_id` is a top-level review comment |
| `no git remote` | Not in a git repo | Use `--repo owner/repo` explicitly |

---

## Decision Cheat Sheet

| User says... | Default Command (Recommended) | Alternative (If needed) |
|-------------|------------------------------|--------------------------|
| "Create a PR" | `gh pr create --title ... --body ...` | — |
| "Show PR comments/reviews" | `~/.agents/skills/gh-cli/scripts/gh-pr-fmt.sh <n>` ✅ | `gh pr view <n> --comments` |
| "Check PR feedback" | `~/.agents/skills/gh-cli/scripts/gh-pr-fmt.sh <n>` ✅ | Raw API calls with `--jq` |
| "Find the PR for my current branch" | `gh pr list --state open --head "$BRANCH" --json number,title,isDraft,... --jq '.[0]'` | — |
| "Poll PR state/reviews/comments" | `gh pr view <n> --json ...,isDraft,reviews,comments --jq ...` | Raw API for specific fields |
| "Show the PR diff" | `gh pr diff <n>` | — |
| "Reply to a review comment on line 45" | `gh api repos/.../pulls/<n>/comments/<id>/replies --method POST -f body='...'` | — |
| "Leave a comment on the PR" | `gh pr comment <n> --body "..."` | — |
| "Approve this PR" | `gh pr review <n> --approve` | — |

**Note:** Always try `~/.agents/skills/gh-cli/scripts/gh-pr-fmt.sh <pr-number>` first when the user asks about PR comments, reviews, or feedback. It provides complete context with 95% fewer tokens than raw JSON.
