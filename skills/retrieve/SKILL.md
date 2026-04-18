---
name: retrieve
description: Use at project start (invoked by `build` before `clarify`) or when the user asks to recall past lessons. Detects project language, reads the corresponding `<language>-lessons.md` and `meta-lessons.md` from the user-global vault, and surfaces the subset relevant to the current goal.
---

# retrieve

## What this skill does

Reads curated lessons from the user-global vault and injects relevant context for the current project. No filtering, no ranking, no index — just read-one-file-per-language.

## Vault location

`~/.claude/skillgoid/vault/`:
- `<language>-lessons.md` — one per language (e.g., `python-lessons.md`)
- `meta-lessons.md` — language-agnostic lessons

If the directory doesn't exist, create it (empty).

## Inputs

- `rough_goal` (string) — the user's one-line goal (or a summary of it).
- Optional: `explicit_language` — skip detection if provided.

## Procedure

1. **Detect language** using this fallback chain (stop at first match):
   a. Explicit `language:` field in `.skillgoid/criteria.yaml` if it exists.
   b. Obvious toolchain files in the project root: `pyproject.toml` → python; `package.json` → node; `go.mod` → go; `Cargo.toml` → rust.
   c. Language keywords in `rough_goal` ("python", "fastapi", "react", "rust CLI", etc.).
   d. Fall back to: ask the user.
2. **Read** `~/.claude/skillgoid/vault/<language>-lessons.md` if it exists. If not, note "no prior lessons for <language>".
3. **Read** `~/.claude/skillgoid/vault/meta-lessons.md` if it exists.
4. **Summarize relevance:** reason over both files and surface the 2–5 lessons most relevant to `rough_goal`. Quote the lesson headings verbatim so the user can recognize them.
5. **Return a short briefing:**

   ```
   past lessons for <language>:
   - <relevant lesson heading> — <one-line why it applies>
   - ...

   meta-lessons:
   - <relevant lesson heading> — <one-line why it applies>
   ```

## When no vault file exists

Return: `"no prior lessons; this is a fresh start for <language>"`. Continue cleanly — do not fail.

## What this skill does not do

- It does not modify the vault (that's `retrospect`).
- It does not decide what's relevant to build — that's for `clarify` and `plan`.
