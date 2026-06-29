"""Validate an auto-review draft before the agent finishes."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ASSESSMENTS = {"APPROVE", "REQUEST_CHANGES", "COMMENT"}
REQUIRED_HEADINGS = ("### Summary", "### Overall Assessment", "### Inline Comments")
_SEVERITY = r"CRITICAL|HIGH|MEDIUM|LOW|INFO"
INLINE_PATTERNS = (
    re.compile(
        rf"^[-*]\s*\[\s*(?P<classification>{_SEVERITY})\s*\]\s*"
        r"`(?P<path>[^`:\n]+):(?P<line>\d+)(?:-\d+)?`\s*(?::|—|–|-)\s*(?P<body>.+?)\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^[-*]\s*`(?P<path>[^`:\n]+):(?P<line>\d+)(?:-\d+)?`\s*"
        rf"\[\s*(?P<classification>{_SEVERITY})\s*\]\s*(?::|—|–|-)\s*(?P<body>.+?)\s*$",
        re.IGNORECASE,
    ),
)


def _missing_headings(content: str) -> list[str]:
    """Return required draft headings absent from the draft."""
    normalized = {line.strip().lower() for line in content.splitlines()}
    return [heading for heading in REQUIRED_HEADINGS if heading.lower() not in normalized]


def _parse_assessment(content: str) -> tuple[str, str | None]:
    """Return the overall assessment and a validation error, if any."""
    lines = content.splitlines()
    for index, line in enumerate(lines):
        if line.strip().lower() != "### overall assessment":
            continue
        for assessment_line in lines[index + 1 :]:
            value = assessment_line.strip()
            if not value:
                continue
            assessment = re.split(r"\s*(?:—|–|-)\s*", value, maxsplit=1)[0].strip().upper()
            if assessment in ASSESSMENTS:
                return assessment, None
            return "", f"unknown overall assessment: {assessment or value}"
    return "", "missing ### Overall Assessment"


def _parse_comment_errors(content: str) -> list[str]:
    """Return malformed inline comment errors from the Inline Comments section."""
    errors: list[str] = []
    in_section = False
    for line_number, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        if stripped.lower() in {"### inline comments", "### inline comment"}:
            in_section = True
            continue
        if in_section and stripped.startswith("### "):
            break
        if not in_section or not stripped or not stripped.startswith(("-", "*")):
            continue
        match = next((match for pattern in INLINE_PATTERNS if (match := pattern.match(stripped))), None)
        if not match or int(match.group("line")) <= 0:
            errors.append(f"draft line {line_number}: malformed inline comment")
    return errors


def validate_draft(draft_file: Path) -> list[str]:
    """Return validation errors for a review draft file."""
    if not draft_file.is_file():
        return [f"draft file not found: {draft_file}"]

    content = draft_file.read_text(encoding="utf-8")
    if not content.strip():
        return [f"draft file is empty: {draft_file}"]

    errors = [f"missing required heading: {heading}" for heading in _missing_headings(content)]
    assessment, assessment_error = _parse_assessment(content)
    if assessment_error:
        errors.append(assessment_error)
    errors.extend(_parse_comment_errors(content))
    if not assessment:
        errors.append("missing valid overall assessment")
    return errors


def main() -> int:
    """Validate a draft file path passed on the command line."""
    parser = argparse.ArgumentParser(description="Validate an auto-review draft markdown file.")
    parser.add_argument("draft_file", type=Path, help="Path to the draft markdown file.")
    args = parser.parse_args()

    errors = validate_draft(args.draft_file)
    if errors:
        print("Draft validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Draft validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
