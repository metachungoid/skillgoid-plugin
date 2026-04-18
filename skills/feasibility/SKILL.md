---
name: feasibility
description: Use after `clarify` completes (or invokable directly as `/skillgoid:feasibility`) to pre-flight-check every gate in `.skillgoid/criteria.yaml` against the current environment. Catches missing tools, unresolvable commands, and obvious env mismatches before iteration budget burns. Advisory only — user decides to proceed or fix first.
---

# feasibility

## What this skill does

Runs a shallow pre-flight check on every gate (and integration_gate) in `.skillgoid/criteria.yaml` — not a full gate run, just a "can this gate plausibly execute?" check. Surfaces mismatches as a readable report so the user can fix criteria before burning iteration budget on environment issues.

## When to use

- Invoked automatically by `skillgoid:build` on fresh start, between `clarify` and `plan`.
- Invokable directly: `/skillgoid:feasibility` — useful after editing `criteria.yaml` or moving the project to a new environment.

## Inputs

- `.skillgoid/criteria.yaml` — must exist.
- Current working environment (PATH, installed tools, env vars).

## Procedure

1. **Read** `.skillgoid/criteria.yaml`. Extract all gates from `gates[]` and `integration_gates[]`.
2. **For each gate, check by type:**
   - `pytest` → `shutil.which("pytest")` or `python -m pytest --version` succeeds.
   - `ruff` → `_resolve_tool("ruff")` succeeds (prefers venv-sibling, falls back to PATH).
   - `mypy` → same pattern as ruff.
   - `import-clean` → `module` field is non-empty and matches `^[a-zA-Z_][a-zA-Z0-9_.]*$`.
   - `coverage` → `pytest --cov --version` succeeds (verifies pytest-cov is installed).
   - `cli-command-runs`, `run-command` → `command[0]` is resolvable on PATH OR declared in `env:` OR is bare `python` (auto-resolved to sys.executable).
3. **For each gate with `env:`** — check PATH-like values (`PYTHONPATH`, `PATH`):
   - If the path value is **absolute**: must exist. Failure is hard.
   - If the path value is **relative** (e.g., `src`): resolve against project dir.
     - If it exists: ok.
     - If it doesn't exist AND the resolved path is within the project dir: downgrade to a WARNING with hint `"relative path '<path>' doesn't exist yet — if your scaffold chunk creates it, this is expected on a fresh project; otherwise fix the config"`. Warnings don't block feasibility on this check alone.
     - If it doesn't exist AND the resolved path is outside the project dir: hard failure.
   - Rationale: on fresh projects, scaffold chunks create `src/`, `tests/`, etc. Failing feasibility on paths the build loop will create is a false positive — observed in real runs on taskq and mdstats (both flagged `PYTHONPATH: src` before scaffold had a chance to create the directory).
4. **Emit a structured report** to stdout (JSON):
```json
{
  "all_ok": bool,
  "checks": [
    {"gate_id": "...", "ok": true|false, "hint": "..."},
    ...
  ]
}
```
5. **Human-readable summary:**
```
feasibility check — N gates, K ok, M failing:
✓ pytest: tool found at /path/to/pytest
✓ ruff: tool found at .venv/bin/ruff
✗ cli_smoke: command 'python' not on PATH (consider python3 or add env:)
```
6. **If `all_ok == false`**, ask the user: *"Proceed anyway / fix criteria now / abort?"*. If invoked from `build`, pass the user's choice back so build can either continue to `plan` or stop.
7. **Return** the structured report to the caller.

## What this skill does NOT do

- Run actual gates (no pytest execution, no code written).
- Install missing tools.
- Modify `criteria.yaml` without user consent.
- Check gate output shape (that's for the real loop).

## Failure modes

- Missing `.skillgoid/criteria.yaml`: exit with clear error, suggest `/skillgoid:clarify` first.
- Malformed criteria.yaml: emit `{"all_ok": false, "checks": [{"gate_id": "__parse__", "ok": false, "hint": "yaml parse failed: <msg>"}]}`.

## Output

Markdown report + JSON object. Human reads the markdown; the calling build skill parses the JSON.
