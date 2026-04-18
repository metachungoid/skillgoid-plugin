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
   - `loop:` block with `max_attempts: 5` (default) and optionally `skip_git: false`
   - `gates:` — propose a starting set based on the language and goal. For Python CLIs, default to `pytest`, `ruff`, `cli-command-runs` (help flag), and `import-clean`. For libraries, drop the CLI gate and add `mypy`.
   - `integration_gates:` (new) — propose ONE default integration gate based on the project type (see step 5.1).
   - `integration_retries: 2` (default; include only if you've proposed integration_gates).
   - `acceptance:` — 2–5 free-form scenarios derived from clarifying answers.

5.1. **Default integration gate per project type.** Pick one:
   - **CLI project:** `cli-command-runs` invoking the CLI's main help flag or a trivial subcommand. Example:
     ```yaml
     integration_gates:
       - id: cli_smoke
         type: cli-command-runs
         command: ["myapp", "--help"]
         expect_exit: 0
         expect_stdout_match: "Usage:"
     ```
   - **Library (Python):** `import-clean` of the top-level package. Example:
     ```yaml
     integration_gates:
       - id: import_smoke
         type: import-clean
         module: mylib
     ```
   - **Service:** if the user can describe a start/health-check/shutdown sequence, generate a `run-command` that does all three. Otherwise leave `integration_gates` empty and note that one should be added by hand. When the service needs a shell pipeline, use `$SKILLGOID_PYTHON` instead of bare `python`:
     ```yaml
     integration_gates:
       - id: service_smoke
         type: run-command
         command: ["bash", "-c", "$SKILLGOID_PYTHON -m myservice --port 8999 & sleep 1 && curl -sf http://localhost:8999/health && kill %1"]
         env:
           PYTHONPATH: "src"
     ```
     (`$SKILLGOID_PYTHON` is set by the adapter to `sys.executable` — guaranteed-working interpreter path inside shell strings.)
   - **Unknown or ambiguous:** leave `integration_gates` empty; the user can add one later.

5.2. **Default coverage gate for Python projects — place in `integration_gates`, not per-chunk `gate_ids`.** Propose a `coverage` entry under `integration_gates:`, NOT inside `gates:`. Rationale: coverage is a whole-package metric. If coverage lives inside `gates:` and chunks reference it via `gate_ids`, it will fail false-positive on every chunk until the last chunk touching the package lands — producing iteration-budget churn for no fault of the chunk being evaluated. Moving it to `integration_gates` runs it once after all chunks pass, which matches the metric's semantic scope.

   ```yaml
   integration_gates:
     - id: cov
       type: coverage
       target: "<package-name>"   # e.g., mypkg; default "." if unclear
       min_percent: 80
       compare_to_baseline: false  # opt in later if desired
   ```

   Omit for non-Python projects or when the user explicitly opts out. `compare_to_baseline: false` by default — users who want regression detection flip it to `true` once a solid baseline exists.

   **Important caveat when combining coverage + CLI gates.** If the project also has a `cli-command-runs` gate (typical CLI project), include this note in the proposed `criteria.yaml` right above the `coverage` gate:

   ```yaml
   # NOTE: pytest-cov does not instrument subprocess calls.
   # Combine this coverage gate with in-process CLI tests that call
   # your main(argv) directly with monkeypatched sys.stdin/stdout,
   # not just subprocess-based tests. Otherwise CLI code will
   # register as uncovered and this gate will fail.
   ```

   This prevents the "pytest passes, ruff passes, coverage drops on the CLI chunk" failure mode observed on real runs. (Note: with v0.7 putting coverage into integration_gates, this failure mode now applies to the integration phase, not any individual chunk.)

5.3. **Default `.gitignore` for Python projects.** If the project directory has no `.gitignore`, propose adding one. Without it, the per-iteration `git_iter_commit.py` commits bytecode and cache artifacts (`__pycache__/`, `.pytest_cache/`, etc.) that pollute iteration `changes` fields and make retrospect noisy. Use this minimal template:

   ```gitignore
   __pycache__/
   *.pyc
   .pytest_cache/
   .ruff_cache/
   .mypy_cache/
   .coverage
   .venv/
   *.egg-info/
   build/
   dist/
   /tmp*.json
   ```

   `/tmp*.json` (v0.7) guards against scratch files that slip the loop skill's `/tmp` discipline. If a subagent accidentally writes a stall-check temp file in the project root, git-add-A would sweep it into the iteration commit. Belt-and-suspenders.

   If `.gitignore` already exists, propose additions of any missing lines — **do not overwrite the user's existing file.** Skip this step entirely for non-Python projects (a future task will add language-appropriate templates).

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
