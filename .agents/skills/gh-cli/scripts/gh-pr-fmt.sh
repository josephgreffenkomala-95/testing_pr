#!/usr/bin/env bash
set -euo pipefail

# gh-pr-fmt: Format gh CLI PR output into clean markdown for LLM ingestion
# Usage: gh-pr-fmt <pr-number> [--repo owner/repo]

usage() {
    cat << 'EOF'
Usage: gh-pr-fmt <pr-number> [--repo owner/repo]

Format GitHub PR data from gh CLI into structured markdown.
Output includes PR description, reviews, review threads, and timeline comments.

Examples:
    gh-pr-fmt 42
    gh-pr-fmt 42 --repo owner/repo
EOF
    exit 1
}

# Parse arguments
PR_NUMBER=""
REPO_FLAG=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            usage
            ;;
        --repo)
            REPO_FLAG="--repo $2"
            shift 2
            ;;
        -*)
            echo "Error: Unknown option $1" >&2
            exit 1
            ;;
        *)
            if [[ -z "$PR_NUMBER" ]]; then
                PR_NUMBER="$1"
                shift
            else
                echo "Error: Unexpected argument $1" >&2
                exit 1
            fi
            ;;
    esac
done

if [[ -z "$PR_NUMBER" ]]; then
    echo "Error: PR number is required" >&2
    usage
fi

# Build gh command prefix
GH_PREFIX=""
if [[ -n "$REPO_FLAG" ]]; then
    GH_PREFIX="$REPO_FLAG"
fi

# Resolve owner/repo for api calls
OWNER=""
REPO=""

if [[ -n "$REPO_FLAG" ]]; then
    # Extract owner/repo from --repo flag
    # Handle formats: "owner/repo" or "HOST/owner/repo"
    REPO_SPEC="${REPO_FLAG#--repo }"
    if [[ "$REPO_SPEC" =~ / ]]; then
        # Check if it has HOST prefix
        PARTS=(${REPO_SPEC//\// })
        if [[ ${#PARTS[@]} -eq 3 ]]; then
            OWNER="${PARTS[1]}"
            REPO="${PARTS[2]}"
        else
            OWNER="${PARTS[0]}"
            REPO="${PARTS[1]}"
        fi
    fi
else
    # Get from current git repo
    REMOTE_URL=$(git remote get-url origin 2>/dev/null || echo "")
    if [[ -n "$REMOTE_URL" ]]; then
        # Extract owner/repo from git URL
        # Handle https://github.com/owner/repo.git or git@github.com:owner/repo.git
        if [[ "$REMOTE_URL" =~ github\.com[/:]([^/]+)/([^/]+)\.? ]]; then
            OWNER="${BASH_REMATCH[1]}"
            REPO="${BASH_REMATCH[2]%\.git}"
        fi
    fi
fi

if [[ -z "$OWNER" || -z "$REPO" ]]; then
    echo "Error: Could not determine owner/repo. Use --repo owner/repo flag." >&2
    exit 1
fi

# Create temp files for JSON data
TEMP_DIR=$(mktemp -d)
PR_JSON="$TEMP_DIR/pr.json"
REVIEWS_JSON="$TEMP_DIR/reviews.json"
COMMENTS_JSON="$TEMP_DIR/comments.json"
TIMELINE_JSON="$TEMP_DIR/timeline.json"

cleanup() {
    rm -rf "$TEMP_DIR"
}
trap cleanup EXIT

# Fetch PR metadata
gh pr view "$PR_NUMBER" $GH_PREFIX --json number,title,body,state,isDraft,reviewDecision,headRefName,baseRefName > "$PR_JSON" 2>&1 || {
    echo "Error: Failed to fetch PR metadata. Check PR number and authentication." >&2
    exit 1
}

# Fetch reviews via API (to get IDs)
gh api "repos/$OWNER/$REPO/pulls/$PR_NUMBER/reviews" > "$REVIEWS_JSON" 2>&1 || {
    echo "Error: Failed to fetch reviews." >&2
    exit 1
}

# Fetch line-level review comments
gh api "repos/$OWNER/$REPO/pulls/$PR_NUMBER/comments" > "$COMMENTS_JSON" 2>&1 || {
    echo "Error: Failed to fetch review comments." >&2
    exit 1
}

# Fetch timeline/issue comments
gh api "repos/$OWNER/$REPO/issues/$PR_NUMBER/comments" > "$TIMELINE_JSON" 2>&1 || {
    echo "Error: Failed to fetch timeline comments." >&2
    exit 1
}

# Process everything with jq to produce markdown
jq -s '
def truncate(text; max):
    if (text | length) > max then
        text[0:max] + "..."
    else
        text
    end;

def short_id(id):
    id | tostring | split("") | .[0:7] | add // id | tostring;

def format_pr(pr):
    "# PR #" + (pr.number | tostring) + ": " + pr.title,
    pr.state + (if pr.isDraft then " • Draft" else "" end) + " • " + pr.headRefName + " → " + pr.baseRefName + " • Review: " + (pr.reviewDecision // "N/A"),
    "",
    "## Description",
    if (pr.body | length) > 0 then
        pr.body
    else
        "*No description provided.*"
    end,
    "";

def format_review(review; threads):
    # Only show review if it has a body or associated threads
    if (review.body | length) > 0 or (threads | length) > 0 then
        "## Review rev_" + short_id(review.id) + " — @" + review.user.login + " (" + review.state + ")",
        if (review.body | length) > 0 then
            truncate(review.body; 500)
        else
            ""
        end,
        "" +
        # Add threads
        [
            threads[] |
            "### Thread on " + .path + ":" + (.line // "N/A" | tostring) + " by @" + .user.login,
            truncate(.body; 300),
            [
                .replies[] |
                "  ↳ **@" + .user.login + "**: " + truncate(.body; 200)
            ][],
            ""
        ][]
    else
        empty
    end;

def format_timeline(comments):
    if (comments | length) > 0 then
        "## Timeline Comments",
        "",
        [
            comments[] |
            "- **@" + .user.login + "**: " + truncate(.body; 200)
        ][]
    else
        empty
    end;

. as [$pr_data, $reviews, $review_comments, $timeline_comments] |

# Build threads from review comments
($review_comments | map(select(.in_reply_to_id == null) |
    .id as $parent_id |
    {
        id: $parent_id,
        path: .path,
        line: .line,
        body: .body,
        user: .user,
        created_at: .created_at,
        review_id: .pull_request_review_id,
        replies: [
            $review_comments[] | select(.in_reply_to_id == $parent_id) |
            {
                id: .id,
                body: .body,
                user: .user,
                created_at: .created_at
            }
        ]
    }
) | group_by(.review_id)) as $threads_by_review |

# Deduplicate reviews by ID (keep first occurrence)
($reviews | unique_by(.id)) as $unique_reviews |

# Build threads from review comments
($review_comments | map(select(.in_reply_to_id == null) |
    .id as $parent_id |
    {
        id: $parent_id,
        path: .path,
        line: .line,
        body: .body,
        user: .user,
        created_at: .created_at,
        review_id: .pull_request_review_id,
        replies: [
            $review_comments[] | select(.in_reply_to_id == $parent_id) |
            {
                id: .id,
                body: .body,
                user: .user,
                created_at: .created_at
            }
        ]
    }
) | group_by(.review_id)) as $threads_by_review |

# Build a lookup table: review_id -> threads for that review
def get_threads_for_review(review_id; threads_grouped):
    threads_grouped[] | select(.[0].review_id == review_id) // [];

# Output everything
format_pr($pr_data),
"",
[
    $unique_reviews[] |
    . as $review |
    get_threads_for_review($review.id; $threads_by_review) as $threads |
    format_review($review; $threads)
][],
"",
format_timeline($timeline_comments)
' "$PR_JSON" "$REVIEWS_JSON" "$COMMENTS_JSON" "$TIMELINE_JSON" 2>/dev/null || {
    echo "Error: Failed to process data. Check jq is installed." >&2
    exit 1
}
