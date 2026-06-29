---
name: pr-review
description: Use for code-reviewing GitHub PRs or branch diffs, drafting classified inline comments, and submitting approve/comment/request-changes reviews after explicit user approval. Trigger on review pr, pr review, code review, review current branch, request changes, approve pr after review, and inline review comments. For any GitHub PR operation, also load gh-cli. Do not use for PR creation, status lookup, fetching/replying to comments, or issue/repo tasks unless a code review is requested.
---

# PR Review

Review changes in either mode:

1. **GitHub PR mode**: review an existing PR with `gh`, draft classified inline comments, then submit review comments/threads only after user approval.
2. **Branch comparison mode**: compare current branch with a target branch (default repo branch from `origin/HEAD`, fallback `main`) and output a structured report. If user asks to submit, map findings to a PR and use GitHub PR mode.

Focus on real problems: bugs, security, data integrity, robustness, performance, missing tests, and maintainability. Avoid praise and nitpicks unless no issues are found.

## Draft Validation Script

Before finishing any generated draft for the auto-review tool, validate the draft file and fix issues until the command passes:

```bash
uv run python .agents/skills/pr-review/scripts/validate_draft.py <draft-file>
```

The script uses the production draft parser. It fails on missing required sections, missing/invalid assessment, and malformed inline comments such as bullets without a `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, or `INFO` classification.

## Non-Negotiable Review Submission Rule

Never submit a GitHub review, approval, request-changes event, or review comment without explicit user approval of the draft.

Workflow:
1. Analyze changes.
2. Present draft comments and intended review event.
3. Wait for clear approval of the exact draft and event shown: "yes", "proceed", "submit this REQUEST_CHANGES review", etc. Ambiguous replies are not approval—ask a clarifying question. If the user requests a different event than drafted, redraft and ask again.
4. **Immediately before submission only**: Add a `START REVIEW` timeline marker comment. This may be posted even if subsequent submission fails; if failure occurs, report that the marker was posted.
5. Submit with `gh` only after approval and after posting the required marker.
6. Include a review summary comment/body in addition to per-location comments.

## Safety Rules

- Do not edit project files during review.
- Do not commit, stash, merge, rebase, checkout, or reset.
- `git fetch origin --prune` is allowed.
- Do NOT mutate local branches (no `git pull`, no `git fetch origin <target>:<target>`). Compare against remote refs like `origin/<branch>` instead.
- If local branch mutation seems necessary, stop and explain; do not do it in the review workflow.
- Temporary review artifacts may be written inside the repo only under an ignored temp directory such as `.tmp/pr-review/`. Verify it is ignored first. If it is not ignored, ask before creating files there or use an already-approved temp location.
- If uncommitted changes exist, ask whether to include them or review committed `HEAD` only.

## Step 1: Choose Review Mode

Use the user's input/arguments first.

### GitHub PR mode triggers
- PR number or URL: `review PR 123`, `https://github.com/org/repo/pull/123`
- Current branch has an open PR.
- User asks to review and then submit, approve, request changes, comment, reply, resolve, or create threads.

Load/use the `gh-cli` skill for every PR operation. This skill adds review-analysis and approval-gating rules; `gh-cli` owns command details.

### Branch comparison mode triggers
- `review current branch`, `compare with develop`, `vs main`, `branch review`
- No PR exists or user asks for local branch comparison.

Target branch parsing:
- none → repo default branch from `origin/HEAD` → fallback `main`
- `compare with develop` → `origin/develop` when available, otherwise ask before using a local-only ref
- `vs feature-xyz` → `origin/feature-xyz` when available, otherwise ask before using a local-only ref
- `against release/1.2` → `origin/release/1.2` when available, otherwise ask before using a local-only ref

If mode or target is ambiguous, ask one concise question.

## Step 2A: GitHub PR Mode Setup

Verify auth and identify PR:

```bash
gh auth status
BRANCH=$(git branch --show-current)
gh pr list --state open --head "$BRANCH" --json number,title,isDraft,headRefName,baseRefName,reviewDecision,url --jq '.[0]'
```

For explicit PR:

```bash
~/.agents/skills/gh-cli/scripts/gh-pr-fmt.sh <number>
gh pr view <number> --json number,title,url,headRefName,baseRefName,commits,files,reviewDecision
gh pr diff <number> --name-only
gh pr view <number> --json additions,deletions,changedFiles
# Load full diff only if small; otherwise inspect targeted file patches via the PR files API.
gh pr diff <number>
```

For large PRs, avoid loading the entire diff. Use the file list and inspect high-risk file patches first:

```bash
OWNER_REPO=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')
gh api repos/$OWNER_REPO/pulls/<number>/files --paginate \
  --jq '.[] | select(.filename == "path/to/high-risk-file") | .patch'
```

If outside repo, use `--repo owner/repo` with `gh` commands.

If the PR has no code changes, report that and stop. If docs-only, run a lighter accuracy/completeness/consistency pass.

## Step 2B: Branch Comparison Mode Setup

Inspect state (read-only):

```bash
git branch --show-current
git status --short
git fetch origin --prune
git symbolic-ref refs/remotes/origin/HEAD --short
```

Target resolution: use repo default branch if available; fallback to `main`.
For user-specified targets, prefer `origin/<target-branch>`. Use a local-only ref only after asking the user.

Compare against remote refs (no local mutation):

```bash
TARGET="$(git symbolic-ref refs/remotes/origin/HEAD --short 2>/dev/null || true)"  # fallback: origin/main
TARGET="${TARGET:-origin/main}"
# If the user specified a target branch, set TARGET="origin/<target-branch>" when that remote ref exists.
git diff --shortstat $TARGET...HEAD
# Inspect file list before full diff. For large diffs (>50 files or >1000 lines), use targeted diffs and state scope.
git diff $TARGET...HEAD --name-only
git diff $TARGET...HEAD -- path/to/high-risk-file
git diff $TARGET...HEAD
```

If reviewing uncommitted changes too:

```bash
git diff --name-only
git diff --shortstat
git diff
git diff --cached --name-only
git diff --cached
```

Handle empty diff, identical branches, missing target refs, and large diffs gracefully. For large diffs, prioritize high-risk files and state scope.

## Step 3: Analyze Changes

Filter non-code files unless they affect behavior, build, deployment, dependencies, security, or tests.

Review each relevant changed file across seven criteria:

1. **Compliance**
   - Project conventions, lint/formatter/test configs, import order, type hints, naming.
   - Test expectations and obvious coverage gaps.
   - Docstring requirements, including Google-style markdown docstrings when project requires them.

2. **Correctness**
   - Logic errors, wrong conditions, edge cases, off-by-one bugs, null/None/undefined handling.
   - Race conditions, concurrency issues, ordering/state bugs, type mismatches.
   - API contract and algorithm correctness.

3. **Robustness**
   - Error handling, exception management, input validation, sanitization.
   - Boundary conditions, malformed data, cleanup, resource leaks.
   - Timeout, retry, cancellation, fallback behavior.

4. **Maintainability**
   - Separation of concerns, modularity, coupling, cohesion, dependency direction.
   - Long methods/classes, duplication, hidden side effects, magic numbers, hardcoded values.
   - Avoid speculative abstraction; prefer project-consistent minimal changes.

5. **Readability**
   - Clear names, organization, nesting, comments, docstrings.
   - Avoid clever/dense code that increases future bug risk.

6. **Optimality**
   - Algorithm complexity, redundant work, repeated I/O, allocations, memory usage.
   - Data structures, DB query patterns, batching, caching, lazy loading.

7. **Security**
   - SQL/command/template/path/code/LDAP/NoSQL injection and prompt injection where relevant.
   - Authn/authz, session handling, output encoding, secure file handling.
   - Secrets exposure, sensitive logs/errors, unsafe debug behavior.
   - Crypto, randomness, key handling, dependency vulnerability risk.

Severity:
- **CRITICAL**: security vulnerability, data corruption/loss, auth bypass, breaking change, outage risk.
- **HIGH**: likely failure bug, major performance issue, serious rule violation, missing critical validation/test.
- **MEDIUM**: maintainability issue, unhandled edge case, moderate performance issue, confusing structure, incomplete tests.
- **LOW**: naming, style, documentation, minor simplification, low-risk consistency.

## Step 4: Prefer Attached Code-Location Feedback

When reviewing a GitHub PR, prefer comments attached directly to changed code over a table-only summary.

For each issue, capture:
- file path
- line or line range on the new side of the diff
- severity
- issue
- why it matters
- concrete recommendation
- short snippet if useful

Only use summary tables for overview. The actionable feedback should be attached to the relevant file/line whenever possible.

If exact line attachment is risky or invalid, use file-level threaded comments with `subject_type=file` and include the line number in the body.

## Step 5: Draft Output Before Submission

### GitHub PR draft format

````markdown
## Draft PR Review for owner/repo#123

Recommended event: REQUEST_CHANGES | COMMENT | APPROVE
Severity summary: X Critical, Y High, Z Medium, W Low

### Inline/thread comments to create
1. path/to/file.py:45 [HIGH]
   Issue: ...
   Recommendation: ...
   Attachment: line-level | file-level fallback

2. path/to/other.ts:12-18 [MEDIUM]
   Issue: ...
   Recommendation: ...
   Attachment: line-level | file-level fallback

### Review body
[Concise overall summary comment to include with the submitted review]

### Submission sequence
1. Post required `START REVIEW` timeline marker.
2. Submit review with summary body, selected event, and attached comments in one create-review API call when possible.
3. If single-call submission is unavailable, use the documented fallback and note that standalone comments post immediately.

Should I submit this review to GitHub?
````

### Branch comparison report format

````markdown
### Code Review Report: [current-branch] vs [target-branch]

**Summary:**
- Files changed: [count]
- Lines added: [count] | Lines removed: [count]
- Review findings: [X] Critical, [Y] High, [Z] Medium, [W] Low
- Scope notes: [fetch/ref status, uncommitted changes inclusion/exclusion, docs-only, large diff limits]

**Findings by Location:**

#### [path/to/file]
- Line(s): [line/range]
- Severity: [CRITICAL/HIGH/MEDIUM/LOW]
- Category: [Compliance/Correctness/Robustness/Maintainability/Readability/Optimality/Security]
- Issue: [specific issue]
- Recommendation: [specific fix]

```[language]
[2-5 line snippet]
```

**Findings by Severity:**
- Critical: [IDs or none]
- High: [IDs or none]
- Medium: [IDs or none]
- Low: [IDs or none]

**Detailed Analysis by File:**
[Specific insights per changed file]

**Compliance Checklist (relevant/failed items only):**
- [ ] Code style compliance
- [ ] Docstring format compliance
- [ ] Import organization
- [ ] Type hint usage
- [ ] Test coverage requirements
- [ ] Naming conventions
- [ ] Security review completed

Omit passing items; include only items with findings or notable gaps.

**Recommended Next Steps:**
- [Actionable next step based on severity]
````

If no issues are found, say no blocking issues were identified.

## Step 6: Submit GitHub Review After Approval

Only after explicit user approval, submit via `gh`. First, post the `START REVIEW` timeline marker; if submission fails after, report the marker was posted.

Prepare temp files in a repo-local ignored temp directory to avoid external-directory permission prompts. Use these for review bodies, API payloads, and multiline comment bodies. First verify `.tmp/` is ignored; if it is not ignored, ask before creating it or use an already-approved temp location:

```bash
git check-ignore -q .tmp/ || git check-ignore -q .tmp/pr-review/
mkdir -p .tmp/pr-review
BODY_TMP=$(mktemp .tmp/pr-review/body.XXXXXX.md)
JSON_TMP=$(mktemp .tmp/pr-review/payload.XXXXXX.json)
COMMENT_BODY_TMP=$(mktemp .tmp/pr-review/comment.XXXXXX.md)
```

Clean up these artifacts after submission or when abandoning the review draft.

Get context:

```bash
HEAD_SHA=$(gh pr view <pr-number> --json commits --jq '.commits | last | .oid')
OWNER_REPO=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')
```

Post the marker comment (do this first, immediately before submission):

```bash
gh pr comment <number> --body "START REVIEW"
```

### Preferred: Single create-review API call

Use the single PR review creation endpoint with body, event, commit_id, and comments payload. Write the JSON payload to `$JSON_TMP` with actual values substituted; do not leave shell variables inside JSON strings:

```json
{
  "commit_id": "<head-sha>",
  "body": "[review summary here]",
  "event": "REQUEST_CHANGES",
  "comments": [
    {
      "path": "src/file.py",
      "line": 45,
      "side": "RIGHT",
      "body": "[HIGH] Issue...\n\nRecommendation: ..."
    },
    {
      "path": "src/other.py",
      "start_line": 40,
      "start_side": "RIGHT",
      "line": 45,
      "side": "RIGHT",
      "body": "[MEDIUM] Issue...\n\nRecommendation: ..."
    }
  ]
}
```

Submit:

```bash
gh api repos/$OWNER_REPO/pulls/<pr-number>/reviews --method POST --input "$JSON_TMP"
```

Event values: `REQUEST_CHANGES` (blocking issues), `COMMENT` (non-blocking), `APPROVE` (no blocking issues).

### Fallback: gh pr review with standalone comments

If the single-call approach is unavailable, use `gh pr review` for the review body and standalone API calls for per-location comments. **Warning**: standalone line/file comments post immediately and publicly before the review is complete.

Choose exactly one fallback path:

1. Summary-only review with no per-location comments.
2. Standalone per-location comments, then one overall review event.

Summary-only review. Put the approved review summary in `$BODY_TMP` using the file-writing tool or a safe temp-file write under the ignored temp directory, not a tracked project file:

```bash
gh pr review <number> --request-changes --body-file "$BODY_TMP"
```

Standalone line-level comments (post immediately). For multiline bodies, use temp payload files or values containing real newlines; avoid examples that rely on literal `\n` escapes:

```bash
gh api repos/$OWNER_REPO/pulls/<pr-number>/comments \
  --method POST \
  -f commit_id="$HEAD_SHA" \
  -f path="src/file.py" \
  -F line=45 \
  -f side=RIGHT \
  -F body=@"$COMMENT_BODY_TMP"
```

Standalone multi-line comments:

```bash
gh api repos/$OWNER_REPO/pulls/<pr-number>/comments \
  --method POST \
  -f commit_id="$HEAD_SHA" \
  -f path="src/file.py" \
  -F start_line=40 \
  -f start_side=RIGHT \
  -F line=45 \
  -f side=RIGHT \
  -F body=@"$COMMENT_BODY_TMP"
```

Fallback to file-level threaded comments when exact line-level placement fails:

```bash
gh api repos/$OWNER_REPO/pulls/<pr-number>/comments \
  --method POST \
  -f commit_id="$HEAD_SHA" \
  -f path="src/file.py" \
  -f subject_type=file \
  -F body=@"$COMMENT_BODY_TMP"
```

After standalone per-location comments, submit overall review event:

```bash
gh pr review <pr-number> --request-changes --body-file "$BODY_TMP"
```

## Step 7: Re-Review Existing Feedback

If user asks for re-review, first verify previous feedback:

```bash
gh pr view <pr-number> --json reviews
gh api repos/{owner}/{repo}/pulls/{pr-number}/comments
```

For each prior blocking comment, mark: resolved, partially addressed, or still open. Re-run normal analysis for regressions/new issues. Draft conclusion before any approval/submission.

Reply to addressed threads only after confirming current PR state, drafting the reply, and receiving explicit user approval:

```bash
gh api repos/$OWNER_REPO/pulls/<pr-number>/comments/<comment-id>/replies \
  --method POST \
  -f body="Addressed in the current PR state. Marking this thread resolved."
```

Resolve threads only if supported by the available GitHub/GraphQL workflow and only after user approval.

## Reporting Standards

- Attach classified comments to code locations whenever possible.
- Include specific file paths, line numbers, snippets, impact, and recommendations.
- Do not invent findings; omit weak concerns or phrase as questions.
- Consolidate duplicates with the clearest location.
- For large PRs, prioritize blocking issues first.
- End branch reports by offering to help implement fixes if requested.
