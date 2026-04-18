---
name: loop
description: Use to execute one chunk from `.skillgoid/chunks.yaml` through the criteria-gated build loop — build, measure via the appropriate language-gates skill, reflect, retry on failure, write `.skillgoid/iterations/NNN.json` each pass. Exits on success, loop-budget exhaustion, no-progress stall, or user interrupt.
---

# loop

## What this skill does

For a single chunk, runs:

```
while gates fail AND attempts < max_attempts AND progress != stalled:
    build    — implement or fix code for this chunk
    measure  — invoke the language-gates skill (e.g., skillgoid:python-gates)
    reflect  — record what happened in iterations/NNN.json
```

## Inputs

- `chunk_id` — the ID from `chunks.yaml` to execute.

## Configuration notes

- `criteria.yaml → loop.max_attempts` — maximum iterations per chunk (default 5).
- `criteria.yaml → loop.skip_git` — set to `true` to disable git-per-iteration commits in this project (default `false`). Useful for projects that have strict commit-message conventions.

## Procedure

### Setup
1. **Read** `.skillgoid/chunks.yaml` and `.skillgoid/criteria.yaml`. Find the chunk by ID.
2. **Resolve language:** chunk `language:` field > criteria `language:` field. If neither, ask the user.
3. **Resolve gates:** the subset of criteria.gates whose IDs appear in `chunk.gate_ids`.
4. **Determine loop budget:** `criteria.loop.max_attempts` (default 5).
5. **Create** `.skillgoid/iterations/` if absent.

### Loop (iteration N = 1, 2, 3, ...)
6. **Build step.** Implement or fix code for this chunk. On iteration 1, build from scratch. On iteration N>1, inject the prior iteration's gate report and reflection as context and fix only what's failing.
7. **Measure step.** Invoke the language-adapter skill:
   - `language == "python"` → `skillgoid:python-gates` with `gate_ids=chunk.gate_ids`.
   - Other languages (v1+) → the matching adapter skill.
8. **Reflect step.** Before writing the iteration file, compute the stall signature by running `python <plugin-root>/scripts/stall_check.py` against the gate_report (write the gate_report to a temp file if needed, then pass the temp file path as the argument). Include the returned 16-char hex value directly in `failure_signature` on initial write — do not leave a placeholder. Then write `.skillgoid/iterations/NNN.json` with:
   ```json
   {
     "iteration": N,
     "chunk_id": "<id>",
     "started_at": "ISO-8601",
     "ended_at": "ISO-8601",
     "gates_run": ["pytest", "ruff"],
     "gate_report": { ... verbatim from adapter ... },
     "reflection": "<1–3 paragraphs: what was tried, what failed, hypothesis for next attempt>",
     "notable": false,
     "failure_signature": "<16-char hex from stall_check.py>",
     "exit_reason": "in_progress"
   }
   ```
   Mark `notable: true` when the reflection surfaces a non-obvious lesson (unexpected tool behavior, surprising library edge case, a design decision that changed the plan). Boring iterations stay `notable: false`. The final written file must have a real 16-char hex in `failure_signature` — the schema will reject a placeholder.

8.1. **Git commit step.** Run:
   ```bash
   python <plugin-root>/scripts/git_iter_commit.py --project <project_path> --iteration .skillgoid/iterations/NNN.json
   ```
   This commits the iteration's changes with a structured message. On non-git projects it silently noops. Skip this step entirely if `criteria.yaml → loop.skip_git == true`.
9. **Exit conditions — evaluate in order:**
   - **Success:** `gate_report.passed == true` for all structured gates. Write a final iteration record with `exit_reason: "success"` and return.
   - **Budget exhausted:** `N >= max_attempts`. Write `exit_reason: "budget_exhausted"` and return with failure.
   - **No-progress stall:** the current iteration's `failure_signature` exactly equals the previous iteration's `failure_signature`. (Use `scripts/stall_check.py` — never rely on judgment.) If the previous iteration's `failure_signature` is missing (legacy v0 record), skip the stall check for this iteration and continue. Write `exit_reason: "stalled"`, surface a summary to the user, and return with failure.
   - **Otherwise:** increment N and continue the loop.

## Acceptance scenarios (soft)

Acceptance scenarios from `criteria.yaml → acceptance[]` are not structured gates. During the build step, use them to inform test writing: if an acceptance scenario isn't covered by an existing gate, write a test for it.

## Output

Short summary:

```
loop complete: chunk=<id>
exit: success | budget_exhausted | stalled
iterations: N
gates final state: <list>
```
