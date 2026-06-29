"""Validate a self-authored revision plan before the agent finishes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _repo_src() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "src"
        if (candidate / "pr_review").is_dir():
            return candidate
    return current.parents[4] / "src"


sys.path.insert(0, str(_repo_src()))

from pr_review.core.revision_parser import parse_revision_plan  # noqa: E402


def validate_plan(plan_file: Path) -> list[str]:
    """Return validation errors for a revision plan file."""
    if not plan_file.is_file():
        return [f"plan file not found: {plan_file}"]
    content = plan_file.read_text(encoding="utf-8")
    if not content.strip():
        return [f"plan file is empty: {plan_file}"]
    required = (
        "### Summary",
        "### File Changes",
        "### Comment Replies",
        "### Commit Message",
        "### Overall Assessment",
    )
    normalized = {line.strip().lower() for line in content.splitlines()}
    errors = [f"missing required heading: {heading}" for heading in required if heading.lower() not in normalized]
    try:
        parse_revision_plan(content)
    except ValueError as exc:
        errors.append(str(exc))
    return errors


def main() -> int:
    """Validate a plan file path passed on the command line."""
    parser = argparse.ArgumentParser(description="Validate a self-authored revision plan markdown file.")
    parser.add_argument("plan_file", type=Path, help="Path to the plan markdown file.")
    args = parser.parse_args()

    errors = validate_plan(args.plan_file)
    if errors:
        print("Plan validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Plan validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
