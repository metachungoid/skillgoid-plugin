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
