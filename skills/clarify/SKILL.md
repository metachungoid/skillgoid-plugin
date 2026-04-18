---
name: clarify
description: Use at the start of a Skillgoid project (or when the user says "clarify my goal") to refine a rough user goal into a concrete `.skillgoid/goal.md` and draft an initial `.skillgoid/criteria.yaml` with measurable gates. Interactive — asks the user clarifying questions one at a time before writing files.
---

# clarify

## What this skill does

Turns a one-line user goal into:
1. `.skillgoid/goal.md` — the refined problem statement, scope, non-goals, and success criteria in prose.
2. `.skillgoid/criteria.yaml` — structured gates + free-form acceptance scenarios, validated against `schemas/criteria.schema.json`.

## When to use

- First action of every new Skillgoid project (invoked by `skillgoid:build`).
- Explicitly by the user mid-project to refine criteria.

## Procedure

1. **Ensure `.skillgoid/` exists** in the project root. If it already contains `goal.md` or `criteria.yaml`, ask the user whether to amend or rewrite before proceeding.
2. **Pull past lessons** by invoking `skillgoid:retrieve` with the user's rough goal. Surface the top-level summary briefly so the user knows past context is in play.
3. **Ask clarifying questions one at a time**, max 6 rounds unless the user asks for more. Cover:
   - Primary user / audience
   - Must-have vs nice-to-have features (scope boundary)
   - Explicit non-goals
   - Success signals the user personally cares about
   - Language/toolchain preference (if not obvious from the goal)
   - Any hard constraints (deadlines, dependencies, deployment target)
   Prefer multiple-choice questions when possible.
4. **Draft `goal.md`** summarizing the refined understanding:
   ```markdown
   # Goal

   <one-paragraph goal statement>

   ## Scope
   - <in-scope items>

   ## Non-goals
   - <explicit non-goals>

   ## Success signals
   - <measurable or observable outcomes>

   ## Constraints
   - <hard constraints>
   ```
5. **Draft `criteria.yaml`** with:
   - `language:` if known
   - `loop.max_attempts: 5` (default)
   - `gates:` — propose a starting set based on the language and goal. For Python CLIs, default to `pytest`, `ruff`, `cli-command-runs` (help flag), and `import-clean`. For libraries, drop the CLI gate and add `mypy`.
   - `acceptance:` — 2–5 free-form scenarios derived from clarifying answers.
6. **Show both files to the user for approval** before returning. Offer to add/remove gates.
7. **Validate** `criteria.yaml` against `schemas/criteria.schema.json` (run `python -c "import json,yaml,jsonschema; jsonschema.validate(yaml.safe_load(open('.skillgoid/criteria.yaml')), json.load(open('<plugin-root>/schemas/criteria.schema.json')))"`). If validation fails, fix and retry.

## Output

Return a short summary to the caller:

```
clarify complete:
- goal.md written
- criteria.yaml with N gates + M acceptance scenarios
- language: <lang>
```
