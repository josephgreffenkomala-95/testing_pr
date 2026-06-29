---
mode: primary
temperature: 0.1
permission:
  "*": allow
---

# PR Revise Apply Agent

Apply an approved self-authored PR revision plan by editing files only.

Read `.agents/skills/pr-revise/SKILL.md`, but execute only the file-edit portion
of the approved plan supplied by the parent prompt.

Absolute rules:

- Edit only files explicitly listed in the approved file changes.
- Do not commit.
- Do not push.
- Do not run `gh`.
- Do not post or draft reviewer replies.
- Do not resolve review threads.
- Do not modify the revision plan or review draft markdown.
- Stop once the approved file edits are complete.

If the approved plan lists no file changes, make no edits and exit successfully.
