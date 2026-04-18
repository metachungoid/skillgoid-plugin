---
name: python-gates
description: Use to measure Python-project gates declared in `.skillgoid/criteria.yaml`. Invoked by the `loop` skill when a chunk's language is `python`. Runs pytest, ruff, mypy, import-clean, cli-command-runs, or generic run-command gates and returns a structured JSON report.
---

# python-gates

## What this skill does

Given a project path and a list of gate IDs (a subset of `.skillgoid/criteria.yaml → gates[]`), run the gates via the `measure_python.py` CLI and return the parsed JSON report.

## When to use

- Invoked by `skillgoid:loop` each iteration to decide whether the current chunk's gates pass.
- Invokable directly by the user (`/skillgoid:python-gates`) to re-measure without building.

## Inputs

- `project_path` — absolute path to the target project (usually the current working directory).
- `criteria_path` — usually `<project_path>/.skillgoid/criteria.yaml`.
- `gate_ids` (optional) — list of gate IDs to run. If omitted, runs all gates in the criteria file.

## Procedure

1. Read `criteria_path`. If `gate_ids` was provided, filter `gates[]` to only those IDs.
2. Write the filtered criteria to a temp file (or pipe via stdin).
3. Invoke the adapter CLI:
   ```bash
   python <plugin-root>/scripts/measure_python.py --project <project_path> --criteria-stdin < <temp_criteria>
   ```

**Note:** gate entries may carry a `timeout` field (integer seconds, default 300). The adapter honors it — a gate that runs past its timeout fails cleanly with a hint, rather than hanging the loop.

**Note:** gates may also carry an `env:` dict (string → string). **As of v0.7, the adapter merges it into the subprocess environment for every gate type** (run-command, cli-command-runs, pytest, import-clean, coverage, ruff, mypy). Previously only run-command and cli-command-runs honored env — v0.6 and earlier silently ignored env for the other 5 handlers. Useful for passing `PYTHONPATH: src` on projects not yet installed via `pip install -e .`. Relative PATH/PYTHONPATH values are resolved against the project dir.

**Default behavior:** pytest / import-clean / coverage still inject `<project>/src` onto PYTHONPATH when the gate does not specify its own PYTHONPATH — back-compat with v0.6 projects that rely on the implicit default. To override, supply `env: {PYTHONPATH: <your-path>}` on the gate.

**Note:** the adapter always exports `SKILLGOID_PYTHON=sys.executable` into the gate subprocess. Inside shell command strings (e.g., `["bash", "-c", "..."]`), reference `$SKILLGOID_PYTHON` instead of bare `python` to get a guaranteed-working interpreter path. The bare-`python` auto-resolution (v0.4) applies only to `command[0]`, so it won't help when `python` appears inside a shell pipeline. `$SKILLGOID_PYTHON` does.

4. Parse stdout as JSON. The shape is:
   ```json
   {"passed": bool, "results": [{"gate_id": str, "passed": bool, "stdout": str, "stderr": str, "hint": str}]}
   ```
5. Return the parsed report to the caller. Do not interpret pass/fail policy — the caller (usually `loop`) decides what to do.

## Failure modes

- If `measure_python.py` exits with code 2 (internal error), surface stderr to the user and stop — the caller should not retry.
- If a gate type is unsupported, the report will contain a failed entry with `hint: "unsupported gate type: <type>"`. Report this plainly; do not invent a workaround.

## Output

Return the JSON report verbatim as a structured object. The caller does any formatting.
