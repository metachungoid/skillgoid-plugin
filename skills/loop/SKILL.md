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
3.1. **Apply per-chunk gate_overrides (v0.8).** If the chunk has `gate_overrides:` (optional field in chunks.yaml), merge into the resolved gates before measurement: for each gate in the resolved set, if its `id` appears in `chunk.gate_overrides`, replace the gate's `args` with `chunk.gate_overrides[gate_id].args`. Other gate fields (type, env, timeout, etc.) come from `criteria.yaml` unchanged.

   Example chunk:
   ```yaml
   - id: py_db
     gate_ids: [lint, pytest_chunk]
     gate_overrides:
       pytest_chunk: {args: ["tests/test_py_db.py"]}
       lint: {args: ["check", "src/taskbridge/db.py"]}
   ```

   This prevents cross-chunk gate interference in parallel waves (F3/F12 from v0.8 findings — every subagent was independently narrowing pytest args defensively; now the narrowing is declared upfront).
4. **Determine loop budget:** `criteria.loop.max_attempts` (default 5).
5. **Create** `.skillgoid/iterations/` if absent.

### Loop (iteration N = 1, 2, 3, ...)
6. **Build step.** Implement or fix code for this chunk. On iteration 1, build from scratch. On iteration N>1, inject the prior iteration's gate report and reflection as context and fix only what's failing.
7. **Measure step.** Invoke the language-adapter skill:
   - `language == "python"` → `skillgoid:python-gates` with `gate_ids=chunk.gate_ids`.
   - Other languages (v1+) → the matching adapter skill.
8. **Reflect step.** Compute `failure_signature` **before** writing the iteration file — never after, never empty, never `""`. Empty or missing signatures silently break stall detection. The schema rejects any value that is not a 16-char lowercase hex string (pattern `^[0-9a-f]{16}$`). One-liner:

   ```bash
   failure_signature=$(python <plugin-root>/scripts/stall_check.py <path-to-gate-report.json>)
   ```

   Write the gate_report to a temp file first (see canonical pattern below), pass that path as the argument, capture stdout as the signature. Then write `.skillgoid/iterations/<chunk_id>-NNN.json` with the captured signature embedded directly — do not leave a placeholder. `<chunk_id>` is this chunk's id from chunks.yaml; `NNN` is this chunk's own iteration count, zero-padded to 3 digits (first iteration is 001). Example: `scaffold-001.json`, `py_db-001.json`, `py_db-002.json`. (v0.7 convention — one filename namespace per chunk, so parallel chunks never contend.) Back-compat note: older projects (pre-v0.7) used unprefixed `NNN.json`. Both conventions coexist in the same iterations dir when a project is resumed across the upgrade; readers handle both.

   The iteration record JSON:
   ```json
   {
     "iteration": N,
     "chunk_id": "<id>",
     "started_at": "ISO-8601",
     "ended_at": "ISO-8601",
     "gates_run": ["pytest", "ruff"],
     "gate_report": {
       "passed": false,
       "results": [
         {
           "gate_id": "pytest_unit",
           "passed": false,
           "stdout": "",
           "stderr": "FAILED tests/test_foo.py::test_bar - AssertionError",
           "hint": "check the return value of parse_iso8601 for fixed offsets"
         },
         {
           "gate_id": "ruff_lint",
           "passed": true,
           "stdout": "All checks passed!",
           "stderr": "",
           "hint": ""
         }
       ]
     },
     "reflection": "<1–3 paragraphs: what was tried, what failed, hypothesis for next attempt>",
     "notable": false,
     "failure_signature": "<16-char hex from stall_check.py>",
     "changes": {"files_touched": [...], "net_lines": <int>, "diff_summary": "..."},
     "exit_reason": "in_progress"
   }
   ```

   This is the adapter-output shape. If you invoked `skillgoid:python-gates` (or any language-gates adapter), use its stdout object verbatim as `gate_report` — it already has this shape. If you are running gates manually without invoking an adapter, construct this exact object form. Do **not** use a flat list like `[{"gate_id": ..., "passed": ...}]`. The scripts accept flat-lists for backward compatibility with legacy iteration records, but this object form is the contract.

   **`exit_reason` values** — write exactly one per iteration record:

   | `exit_reason` value | When to write it |
   |---|---|
   | `"in_progress"` | Gates failed, budget remains, no stall detected. The loop will continue to iteration N+1. |
   | `"success"` | All gates passed (`gate_report.passed == true`). Terminal. |
   | `"budget_exhausted"` | This is iteration N and N ≥ `max_attempts`. Terminal with failure. |
   | `"stalled"` | `failure_signature` equals the previous iteration's `failure_signature`. Terminal with failure. |

   Write the field as `exit_reason`, not `status`. The schema, `scripts/stall_check.py`, `hooks/detect-resume.sh`, and `hooks/gate-guard.sh` all key off `exit_reason`. Using `status` will cause hooks to silently miss completed chunks and gate-guard to miss failing iterations. (The hooks do fall back to `status` for backward compatibility with pre-v0.10 records, but that fallback exists to rescue legacy data, not to license new drift.)

   Mark `notable: true` when the reflection surfaces a non-obvious lesson (unexpected tool behavior, surprising library edge case, a design decision that changed the plan). Boring iterations stay `notable: false`. The final written file must have a real 16-char hex in `failure_signature` — the schema will reject a placeholder.

### Scratch files — keep them out of the project tree

Any temp files you create during the iteration — including the one used to pass the gate_report to `stall_check.py` — must live under `tempfile.mkdtemp()` or `$TMPDIR`, never inside the project. If a scratch file lands in the project root, `git_iter_commit.py`'s staging will sweep it into the iteration commit (observed in real runs pre-v0.7).

Canonical pattern — write gate_report to a tempfile, call `stall_check.py`, capture the signature, insert it into the iteration record, then clean up:

```python
import json
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN_ROOT = Path("<plugin-root>")  # resolve from CLAUDE_PLUGIN_ROOT or similar

with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False,
                                  dir=tempfile.gettempdir()) as tf:
    tf.write(json.dumps({"gate_report": gate_report}))
    scratch = Path(tf.name)
try:
    proc = subprocess.run(
        [sys.executable, str(PLUGIN_ROOT / "scripts/stall_check.py"), str(scratch)],
        capture_output=True, text=True, check=True,
    )
    failure_signature = proc.stdout.strip()  # 16-char lowercase hex
    iteration_record["failure_signature"] = failure_signature
    # ... then write iteration_record to .skillgoid/iterations/<chunk_id>-NNN.json
finally:
    scratch.unlink(missing_ok=True)
```

8.1. **Git commit step.** Run:
   ```bash
   python <plugin-root>/scripts/git_iter_commit.py \
     --project <project_path> \
     --iteration .skillgoid/iterations/<chunk_id>-NNN.json \
     --chunks-file .skillgoid/chunks.yaml
   ```
   The `--chunks-file` flag (v0.7) lets the commit helper look up the chunk's `paths:` for scoped staging. If you omit `--chunks-file` OR the chunk has no `paths:` declared, git_iter_commit falls back to `git add -A` with a stderr warning — safe for sequential waves, unsafe for parallel ones. This commits the iteration's changes with a structured message. On non-git projects it silently noops. Skip this step entirely if `criteria.yaml → loop.skip_git == true`.

8.2. **Record diff summary.** Immediately after the git commit lands, capture what changed:
   ```bash
   python <plugin-root>/scripts/diff_summary.py --project <project_path>
   ```
   The output JSON has shape `{files_touched: [...], net_lines: int, diff_summary: str}`. Inject this as the `changes` field when writing `iterations/NNN.json`. If `loop.skip_git == true` or the project isn't a git repo (`diff_summary.py` returns `"git not available"`), omit the `changes` field.

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
