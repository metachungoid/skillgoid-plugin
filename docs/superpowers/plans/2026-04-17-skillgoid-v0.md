# Skillgoid v0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Skillgoid v0 — a Claude Code plugin that drives a rough project goal through a criteria-gated build loop with a curated per-language lessons vault.

**Architecture:** 7 skills (`build`, `clarify`, `plan`, `loop`, `retrieve`, `retrospect`, `python-gates`) + 2 hooks (`SessionStart: detect-resume`, `Stop: gate-guard`) + 1 helper CLI (`measure_python.py`). Skills are prose instructions that orchestrate Claude Code's native tools. The gate adapter is a Python CLI that produces a structured JSON report. Hooks are small bash scripts bundled in the plugin manifest — no user `settings.json` edits required.

**Tech Stack:** Claude Code plugin system (`.claude-plugin/plugin.json`), Python 3.11+ with pytest for helper scripts, bash for hooks, PyYAML for schema parsing, `jsonschema` for validation.

**Naming note:** spec §14 used `skillgoid-*` skill names; this plan shortens them (`clarify`, `plan`, etc.) because the Claude Code plugin system namespaces skills as `/skillgoid:<name>` automatically. Semantics unchanged.

---

## Repo layout

```
skillgoid-plugin/
├── .claude-plugin/plugin.json              # manifest
├── README.md
├── LICENSE                                 # MIT
├── Makefile                                # test, lint, install-local
├── pyproject.toml                          # pytest + ruff config for helper scripts
├── .gitignore
├── skills/
│   ├── build/SKILL.md                      # top-level orchestrator
│   ├── clarify/SKILL.md                    # Stage -1 equivalent
│   ├── plan/SKILL.md                       # Stage 0+2 equivalent
│   ├── loop/SKILL.md                       # build-measure-reflect inner loop
│   ├── retrieve/SKILL.md                   # vault reader
│   ├── retrospect/SKILL.md                 # final summary + vault curator
│   └── python-gates/SKILL.md               # gate adapter skill, invokes measure_python.py
├── hooks/
│   ├── hooks.json                          # event → command mapping
│   ├── detect-resume.sh                    # SessionStart hook
│   └── gate-guard.sh                       # Stop hook
├── scripts/
│   ├── measure_python.py                   # Python gate measurement CLI
│   └── __init__.py
├── schemas/
│   ├── criteria.schema.json                # JSON Schema for .skillgoid/criteria.yaml
│   └── chunks.schema.json                  # JSON Schema for .skillgoid/chunks.yaml
├── examples/hello-cli/goal.md              # example starting goal for smoke test
├── tests/
│   ├── conftest.py
│   ├── test_schemas.py
│   ├── test_measure_python.py
│   ├── test_detect_resume.py
│   ├── test_gate_guard.py
│   └── fixtures/
│       ├── passing-project/                # pytest/ruff pass
│       └── failing-project/                # pytest/ruff fail
└── docs/superpowers/
    ├── specs/2026-04-17-skillgoid-design.md    # committed
    └── plans/2026-04-17-skillgoid-v0.md        # this file
```

---

## Task 1: Bootstrap the repo

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `LICENSE`
- Create: `Makefile`
- Modify: `README.md` (stub)

- [ ] **Step 1.1: Write `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "skillgoid-helpers"
version = "0.0.1"
description = "Helper scripts for the Skillgoid Claude Code plugin"
requires-python = ">=3.11"

[project.optional-dependencies]
dev = [
  "pytest>=8.0",
  "pytest-cov",
  "pyyaml>=6.0",
  "jsonschema>=4.0",
  "ruff>=0.5",
  "mypy>=1.10",
]

[tool.setuptools.packages.find]
include = ["scripts"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"

[tool.ruff]
line-length = 100
extend-select = ["T201"]
```

- [ ] **Step 1.2: Write `.gitignore`**

```
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
.mypy_cache/
.coverage
htmlcov/
dist/
build/
*.egg-info/
.venv/
.skillgoid/
```

- [ ] **Step 1.3: Write `LICENSE` (MIT)**

Standard MIT text, year 2026, author "Skillgoid contributors".

- [ ] **Step 1.4: Write `Makefile`**

```makefile
.PHONY: test lint install-local clean

test:
	pytest

lint:
	ruff check .

install-local:
	claude plugin install .

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache __pycache__ dist build *.egg-info
```

- [ ] **Step 1.5: Write `README.md` stub**

```markdown
# Skillgoid

A Claude Code plugin that turns a rough project goal into a shipped codebase through a criteria-gated build loop with compounding cross-project memory.

See `docs/superpowers/specs/2026-04-17-skillgoid-design.md` for the full design spec.

Quickstart coming in Task 16.
```

- [ ] **Step 1.6: Verify install works**

Run: `python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"`
Expected: installs cleanly, `pytest --version` and `ruff --version` both work.

- [ ] **Step 1.7: Commit**

```bash
git add pyproject.toml .gitignore LICENSE Makefile README.md
git commit -m "chore: bootstrap repo — pyproject, license, makefile"
```

---

## Task 2: JSON schemas for `criteria.yaml` and `chunks.yaml`

**Files:**
- Create: `schemas/criteria.schema.json`
- Create: `schemas/chunks.schema.json`
- Create: `tests/test_schemas.py`
- Create: `tests/fixtures/valid_criteria.yaml`
- Create: `tests/fixtures/valid_chunks.yaml`

- [ ] **Step 2.1: Write `schemas/criteria.schema.json`**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Skillgoid criteria.yaml",
  "type": "object",
  "required": ["gates"],
  "properties": {
    "language": {"type": "string", "description": "Primary language tag, e.g. python, node"},
    "loop": {
      "type": "object",
      "properties": {
        "max_attempts": {"type": "integer", "minimum": 1, "default": 5}
      }
    },
    "gates": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "type"],
        "properties": {
          "id": {"type": "string"},
          "type": {"type": "string", "enum": ["pytest", "ruff", "mypy", "import-clean", "cli-command-runs", "run-command"]},
          "args": {"type": "array", "items": {"type": "string"}},
          "command": {"type": "array", "items": {"type": "string"}},
          "expect_exit": {"type": "integer"},
          "expect_stdout_match": {"type": "string"},
          "module": {"type": "string"}
        },
        "additionalProperties": true
      }
    },
    "acceptance": {
      "type": "array",
      "items": {"type": "string"}
    }
  }
}
```

- [ ] **Step 2.2: Write `schemas/chunks.schema.json`**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Skillgoid chunks.yaml",
  "type": "object",
  "required": ["chunks"],
  "properties": {
    "chunks": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "description"],
        "properties": {
          "id": {"type": "string"},
          "description": {"type": "string"},
          "language": {"type": "string"},
          "gate_ids": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Subset of criteria.gates[].id this chunk must satisfy"
          },
          "depends_on": {
            "type": "array",
            "items": {"type": "string"}
          }
        }
      }
    }
  }
}
```

- [ ] **Step 2.3: Write valid fixture `tests/fixtures/valid_criteria.yaml`**

```yaml
language: python
loop:
  max_attempts: 5
gates:
  - id: pytest
    type: pytest
    args: ["-q"]
  - id: lint
    type: ruff
  - id: cli_help
    type: cli-command-runs
    command: ["myapp", "--help"]
    expect_exit: 0
    expect_stdout_match: "Usage:"
acceptance:
  - "CLI runs end-to-end on a fresh clone with only pip install -e ."
```

- [ ] **Step 2.4: Write valid fixture `tests/fixtures/valid_chunks.yaml`**

```yaml
chunks:
  - id: scaffold
    description: "Create package layout and pyproject"
    language: python
    gate_ids: [lint]
  - id: core-api
    description: "Implement core CLI commands"
    language: python
    gate_ids: [pytest, lint, cli_help]
    depends_on: [scaffold]
```

- [ ] **Step 2.5: Write failing test `tests/test_schemas.py`**

```python
import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


def _validator(schema_name: str) -> Draft202012Validator:
    schema = json.loads((ROOT / "schemas" / schema_name).read_text())
    return Draft202012Validator(schema)


def _load_yaml(fixture: str) -> dict:
    return yaml.safe_load((ROOT / "tests" / "fixtures" / fixture).read_text())


def test_valid_criteria_passes_schema():
    data = _load_yaml("valid_criteria.yaml")
    errors = list(_validator("criteria.schema.json").iter_errors(data))
    assert errors == []


def test_valid_chunks_passes_schema():
    data = _load_yaml("valid_chunks.yaml")
    errors = list(_validator("chunks.schema.json").iter_errors(data))
    assert errors == []


def test_criteria_missing_gates_fails():
    errors = list(_validator("criteria.schema.json").iter_errors({}))
    assert any("gates" in str(e.message) for e in errors)


def test_chunk_missing_id_fails():
    bad = {"chunks": [{"description": "no id here"}]}
    errors = list(_validator("chunks.schema.json").iter_errors(bad))
    assert any("id" in str(e.message) for e in errors)


def test_unknown_gate_type_fails():
    bad = {"gates": [{"id": "x", "type": "unknown-gate"}]}
    errors = list(_validator("criteria.schema.json").iter_errors(bad))
    assert any("enum" in str(e.message).lower() for e in errors)
```

- [ ] **Step 2.6: Run tests to confirm they pass**

Run: `pytest tests/test_schemas.py -v`
Expected: all 5 tests pass.

- [ ] **Step 2.7: Commit**

```bash
git add schemas/ tests/test_schemas.py tests/fixtures/valid_criteria.yaml tests/fixtures/valid_chunks.yaml
git commit -m "feat: add JSON schemas for criteria and chunks YAML"
```

---

## Task 3: `measure_python.py` skeleton + `run-command` gate

The Python gate adapter is a CLI that takes a project path and a criteria YAML, runs the requested gates, and prints a JSON report. This task implements the skeleton and the simplest gate (`run-command`) first; later tasks add more gate types.

**Files:**
- Create: `scripts/measure_python.py`
- Create: `scripts/__init__.py` (empty)
- Create: `tests/test_measure_python.py`
- Create: `tests/fixtures/passing-project/README.md` (marker only)

- [ ] **Step 3.1: Create `scripts/__init__.py`**

Empty file so tests can import from `scripts`.

- [ ] **Step 3.2: Write the failing test `tests/test_measure_python.py`**

```python
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = [sys.executable, str(ROOT / "scripts" / "measure_python.py")]


def run_cli(criteria_yaml: str, project_path: Path) -> dict:
    result = subprocess.run(
        CLI + ["--project", str(project_path), "--criteria-stdin"],
        input=criteria_yaml,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode in (0, 1), f"stderr: {result.stderr}"
    return json.loads(result.stdout)


def test_run_command_gate_passing(tmp_path: Path):
    criteria = """
gates:
  - id: echo
    type: run-command
    command: ["echo", "hello"]
    expect_exit: 0
"""
    report = run_cli(criteria, tmp_path)
    assert report["passed"] is True
    assert len(report["results"]) == 1
    assert report["results"][0]["gate_id"] == "echo"
    assert report["results"][0]["passed"] is True


def test_run_command_gate_failing(tmp_path: Path):
    criteria = """
gates:
  - id: fail
    type: run-command
    command: ["false"]
    expect_exit: 0
"""
    report = run_cli(criteria, tmp_path)
    assert report["passed"] is False
    assert report["results"][0]["passed"] is False
```

- [ ] **Step 3.3: Run test to confirm it fails**

Run: `pytest tests/test_measure_python.py -v`
Expected: FAIL — `measure_python.py` not found.

- [ ] **Step 3.4: Write `scripts/measure_python.py`**

```python
#!/usr/bin/env python3
"""Skillgoid Python gate adapter.

Reads a subset of criteria.yaml (the gates to run) and a project path;
runs each gate; emits a structured JSON report on stdout.

Contract: stdout is always valid JSON. Stderr carries debug noise. Exit
code 0 if all gates passed, 1 if any failed, 2 on internal error.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import yaml


@dataclass
class GateResult:
    gate_id: str
    passed: bool
    stdout: str
    stderr: str
    hint: str


def _run(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    return proc.returncode, proc.stdout, proc.stderr


def _gate_run_command(gate: dict, project: Path) -> GateResult:
    cmd = gate.get("command") or []
    if not cmd:
        return GateResult(gate["id"], False, "", "no command specified", "add `command:` to gate")
    expect_exit = gate.get("expect_exit", 0)
    code, out, err = _run(cmd, project)
    passed = code == expect_exit
    hint = "" if passed else f"exit={code}, expected {expect_exit}"
    return GateResult(gate["id"], passed, out, err, hint)


GATE_DISPATCH = {
    "run-command": _gate_run_command,
}


def run_gates(criteria: dict, project: Path) -> dict[str, Any]:
    results: list[GateResult] = []
    for gate in criteria.get("gates", []):
        handler = GATE_DISPATCH.get(gate["type"])
        if handler is None:
            results.append(GateResult(gate["id"], False, "", f"unsupported gate type: {gate['type']}", "add adapter support"))
            continue
        results.append(handler(gate, project))
    return {
        "passed": all(r.passed for r in results),
        "results": [asdict(r) for r in results],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Skillgoid Python gate adapter")
    ap.add_argument("--project", required=True, type=Path)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--criteria-file", type=Path, help="Path to a criteria.yaml subset")
    src.add_argument("--criteria-stdin", action="store_true", help="Read criteria YAML from stdin")
    args = ap.parse_args(argv)

    if args.criteria_stdin:
        criteria = yaml.safe_load(sys.stdin.read())
    else:
        criteria = yaml.safe_load(args.criteria_file.read_text())

    report = run_gates(criteria or {}, args.project.resolve())
    json.dump(report, sys.stdout)
    sys.stdout.write("\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3.5: Run tests to confirm they pass**

Run: `pytest tests/test_measure_python.py -v`
Expected: both tests pass.

- [ ] **Step 3.6: Commit**

```bash
git add scripts/measure_python.py scripts/__init__.py tests/test_measure_python.py
git commit -m "feat(gates): measure_python.py skeleton + run-command gate"
```

---

## Task 4: Add `pytest` and `ruff` gate types

**Files:**
- Modify: `scripts/measure_python.py` (add two gate handlers + dispatch entries)
- Modify: `tests/test_measure_python.py` (add tests for both)
- Create: `tests/fixtures/passing-project/pyproject.toml`
- Create: `tests/fixtures/passing-project/src/mypkg/__init__.py`
- Create: `tests/fixtures/passing-project/tests/test_trivial.py`
- Create: `tests/fixtures/failing-project/pyproject.toml`
- Create: `tests/fixtures/failing-project/src/mypkg/__init__.py`
- Create: `tests/fixtures/failing-project/tests/test_fails.py`

- [ ] **Step 4.1: Create passing fixture project**

`tests/fixtures/passing-project/pyproject.toml`:
```toml
[project]
name = "mypkg"
version = "0.0.1"
requires-python = ">=3.11"

[tool.setuptools.packages.find]
where = ["src"]

[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"
```

`tests/fixtures/passing-project/src/mypkg/__init__.py`:
```python
"""mypkg — passing fixture."""


def add(a: int, b: int) -> int:
    return a + b
```

`tests/fixtures/passing-project/tests/test_trivial.py`:
```python
from mypkg import add


def test_add_one_plus_one():
    assert add(1, 1) == 2
```

- [ ] **Step 4.2: Create failing fixture project**

`tests/fixtures/failing-project/pyproject.toml`: same as passing.

`tests/fixtures/failing-project/src/mypkg/__init__.py`:
```python
import os  # unused import — ruff will flag
def add(a, b):
    return a - b  # wrong on purpose
```

`tests/fixtures/failing-project/tests/test_fails.py`:
```python
from mypkg import add
def test_add_fails():
    assert add(1, 1) == 2
```

- [ ] **Step 4.3: Write failing tests in `tests/test_measure_python.py`**

Append:

```python
PASSING = ROOT / "tests" / "fixtures" / "passing-project"
FAILING = ROOT / "tests" / "fixtures" / "failing-project"


def test_pytest_gate_passing():
    criteria = """
gates:
  - id: pytest
    type: pytest
    args: ["-q"]
"""
    report = run_cli(criteria, PASSING)
    assert report["passed"] is True
    assert report["results"][0]["gate_id"] == "pytest"


def test_pytest_gate_failing():
    criteria = """
gates:
  - id: pytest
    type: pytest
    args: ["-q"]
"""
    report = run_cli(criteria, FAILING)
    assert report["passed"] is False
    assert "FAIL" in report["results"][0]["stdout"] or "failed" in report["results"][0]["stdout"].lower()


def test_ruff_gate_passing():
    criteria = """
gates:
  - id: lint
    type: ruff
"""
    report = run_cli(criteria, PASSING)
    assert report["passed"] is True


def test_ruff_gate_failing():
    criteria = """
gates:
  - id: lint
    type: ruff
"""
    report = run_cli(criteria, FAILING)
    assert report["passed"] is False
    # ruff should flag the unused os import
    stdout_lower = report["results"][0]["stdout"].lower()
    assert "os" in stdout_lower or "unused" in stdout_lower or "f401" in stdout_lower
```

- [ ] **Step 4.4: Run tests — confirm 4 new tests fail**

Run: `pytest tests/test_measure_python.py -v`
Expected: 4 new tests fail (gate types not yet handled).

- [ ] **Step 4.5: Extend `scripts/measure_python.py`**

Add handlers and register them:

```python
def _gate_pytest(gate: dict, project: Path) -> GateResult:
    args = gate.get("args") or []
    # Install the fixture package in-tree so imports resolve; fall back to PYTHONPATH src
    env_path = str(project / "src")
    import os
    env = {**os.environ, "PYTHONPATH": env_path + ":" + os.environ.get("PYTHONPATH", "")}
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *args],
        cwd=project,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    passed = proc.returncode == 0
    hint = "" if passed else "pytest exited nonzero — read stdout for failing test names"
    return GateResult(gate["id"], passed, proc.stdout, proc.stderr, hint)


def _gate_ruff(gate: dict, project: Path) -> GateResult:
    args = gate.get("args") or ["check", "."]
    proc = subprocess.run(
        ["ruff", *args],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    passed = proc.returncode == 0
    hint = "" if passed else "ruff flagged lint issues — fix or add to ignore config"
    return GateResult(gate["id"], passed, proc.stdout, proc.stderr, hint)


GATE_DISPATCH = {
    "run-command": _gate_run_command,
    "pytest": _gate_pytest,
    "ruff": _gate_ruff,
}
```

Replace the existing `GATE_DISPATCH` with the expanded version.

- [ ] **Step 4.6: Run tests**

Run: `pytest tests/test_measure_python.py -v`
Expected: all 6 tests pass.

- [ ] **Step 4.7: Commit**

```bash
git add scripts/measure_python.py tests/test_measure_python.py tests/fixtures/
git commit -m "feat(gates): pytest and ruff gate types"
```

---

## Task 5: Add `mypy`, `import-clean`, `cli-command-runs` gates

**Files:**
- Modify: `scripts/measure_python.py`
- Modify: `tests/test_measure_python.py`

- [ ] **Step 5.1: Write failing tests**

Append to `tests/test_measure_python.py`:

```python
def test_mypy_gate_on_passing_fixture():
    criteria = """
gates:
  - id: types
    type: mypy
    args: ["src"]
"""
    report = run_cli(criteria, PASSING)
    # mypy should pass on the trivial fixture
    assert report["passed"] is True


def test_import_clean_passes():
    criteria = """
gates:
  - id: imp
    type: import-clean
    module: mypkg
"""
    report = run_cli(criteria, PASSING)
    assert report["passed"] is True


def test_import_clean_fails_on_nonexistent_module(tmp_path: Path):
    criteria = """
gates:
  - id: imp
    type: import-clean
    module: does_not_exist_xyz
"""
    report = run_cli(criteria, tmp_path)
    assert report["passed"] is False


def test_cli_command_runs_passing(tmp_path: Path):
    criteria = """
gates:
  - id: cli
    type: cli-command-runs
    command: ["echo", "hello world"]
    expect_exit: 0
    expect_stdout_match: "hello"
"""
    report = run_cli(criteria, tmp_path)
    assert report["passed"] is True


def test_cli_command_runs_fails_on_stdout_mismatch(tmp_path: Path):
    criteria = """
gates:
  - id: cli
    type: cli-command-runs
    command: ["echo", "goodbye"]
    expect_exit: 0
    expect_stdout_match: "hello"
"""
    report = run_cli(criteria, tmp_path)
    assert report["passed"] is False
    assert "stdout" in report["results"][0]["hint"].lower()
```

- [ ] **Step 5.2: Run tests — confirm they fail**

Run: `pytest tests/test_measure_python.py -v`
Expected: 5 new tests fail.

- [ ] **Step 5.3: Implement handlers in `scripts/measure_python.py`**

Add these handlers and extend `GATE_DISPATCH`:

```python
import re


def _gate_mypy(gate: dict, project: Path) -> GateResult:
    args = gate.get("args") or ["."]
    proc = subprocess.run(
        ["mypy", *args],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    # mypy returns 0 on success; 1+ on type errors; 2 on internal errors.
    passed = proc.returncode == 0
    hint = "" if passed else "mypy reported type errors — read stdout"
    return GateResult(gate["id"], passed, proc.stdout, proc.stderr, hint)


def _gate_import_clean(gate: dict, project: Path) -> GateResult:
    module = gate.get("module")
    if not module:
        return GateResult(gate["id"], False, "", "missing `module` field", "add `module: <name>`")
    import os
    env = {**os.environ, "PYTHONPATH": str(project / "src") + ":" + os.environ.get("PYTHONPATH", "")}
    proc = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=project,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    passed = proc.returncode == 0
    hint = "" if passed else f"import failed: {proc.stderr.strip()[:200]}"
    return GateResult(gate["id"], passed, proc.stdout, proc.stderr, hint)


def _gate_cli_command_runs(gate: dict, project: Path) -> GateResult:
    cmd = gate.get("command") or []
    expect_exit = gate.get("expect_exit", 0)
    expect_match = gate.get("expect_stdout_match")
    if not cmd:
        return GateResult(gate["id"], False, "", "no command specified", "add `command:` to gate")
    code, out, err = _run(cmd, project)
    passed = code == expect_exit
    hint_parts = []
    if not passed:
        hint_parts.append(f"exit={code}, expected {expect_exit}")
    if expect_match and not re.search(expect_match, out):
        passed = False
        hint_parts.append(f"stdout did not match /{expect_match}/")
    return GateResult(gate["id"], passed, out, err, "; ".join(hint_parts))


GATE_DISPATCH = {
    "run-command": _gate_run_command,
    "pytest": _gate_pytest,
    "ruff": _gate_ruff,
    "mypy": _gate_mypy,
    "import-clean": _gate_import_clean,
    "cli-command-runs": _gate_cli_command_runs,
}
```

Replace the existing `GATE_DISPATCH` with the expanded version.

- [ ] **Step 5.4: Run tests**

Run: `pytest tests/test_measure_python.py -v`
Expected: all 11 tests pass.

- [ ] **Step 5.5: Commit**

```bash
git add scripts/measure_python.py tests/test_measure_python.py
git commit -m "feat(gates): mypy, import-clean, cli-command-runs gate types"
```

---

## Task 6: `python-gates` skill

The skill markdown that Claude invokes to run gates. It shells out to `measure_python.py`.

**Files:**
- Create: `skills/python-gates/SKILL.md`

- [ ] **Step 6.1: Write `skills/python-gates/SKILL.md`**

````markdown
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
````

- [ ] **Step 6.2: Lint-check the skill file**

Verify the YAML frontmatter parses and references exist:
```bash
python -c "import yaml; f=open('skills/python-gates/SKILL.md'); lines=f.read().split('---', 2); print(yaml.safe_load(lines[1]))"
```
Expected: prints `{'name': 'python-gates', 'description': '...'}`.

- [ ] **Step 6.3: Commit**

```bash
git add skills/python-gates/SKILL.md
git commit -m "feat(skill): python-gates skill wraps measure_python.py"
```

---

## Task 7: `clarify` skill

Interactive goal refinement + criteria drafting.

**Files:**
- Create: `skills/clarify/SKILL.md`

- [ ] **Step 7.1: Write `skills/clarify/SKILL.md`**

````markdown
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
````

- [ ] **Step 7.2: Commit**

```bash
git add skills/clarify/SKILL.md
git commit -m "feat(skill): clarify — goal refinement + criteria drafting"
```

---

## Task 8: `plan` skill

Blueprint + chunk breakdown.

**Files:**
- Create: `skills/plan/SKILL.md`

- [ ] **Step 8.1: Write `skills/plan/SKILL.md`**

````markdown
---
name: plan
description: Use after `clarify` completes (or when the user says "plan the implementation") to turn `.skillgoid/goal.md` + `.skillgoid/criteria.yaml` into a concrete `.skillgoid/blueprint.md` and an ordered `.skillgoid/chunks.yaml`. Each chunk names the gate IDs it must satisfy.
---

# plan

## What this skill does

Produces two files:
1. `.skillgoid/blueprint.md` — architecture, key modules and their responsibilities, interface signatures, data model.
2. `.skillgoid/chunks.yaml` — ordered list of build chunks. Each chunk declares a subset of criteria gates that must pass before the chunk is considered complete. Validated against `schemas/chunks.schema.json`.

## Inputs

- `.skillgoid/goal.md`
- `.skillgoid/criteria.yaml`

## Procedure

1. **Verify** both input files exist. If not, stop and tell the caller to run `skillgoid:clarify` first.
2. **Read** the goal, criteria, and any past-lesson summary still in context from `skillgoid:retrieve`.
3. **Write `blueprint.md`** covering:
   - Architecture overview (1–3 paragraphs)
   - Module layout and responsibilities (which files go where)
   - Public interfaces / function signatures for the main entry points
   - Data model (types, storage, or schema) if applicable
   - External dependencies
4. **Write `chunks.yaml`** decomposing implementation into 3–8 chunks. Each chunk:
   - Has a short `id` (kebab-case)
   - Has a concrete `description` (what code will land in this chunk)
   - Has a `gate_ids` list — the subset of criteria gates that must pass for this chunk to count as done. Early chunks typically need only lint / import-clean. Later chunks add pytest and cli gates.
   - Optional `depends_on` — IDs of chunks that must finish first.
   - Optional `language` override (for polyglot projects).
5. **Enforce sequencing:** gate_ids must be real IDs from `criteria.yaml`. If a chunk references a nonexistent gate, fix it.
6. **Validate** `chunks.yaml` against `schemas/chunks.schema.json` (same pattern as `clarify` step 7).
7. **Show both files to the user** and ask for sign-off before returning. Adjust ordering, split/merge chunks if requested.

## Principles

- **Small chunks.** A chunk should be 30–90 minutes of work for a focused engineer. If a chunk needs 3+ modules changed, split it.
- **Gate early, gate often.** Don't reserve all gates for the last chunk. The whole point of the loop is to fail fast.
- **Dependency-order the list.** `chunks[0]` has no dependencies; each later chunk can reference earlier ones in `depends_on`.

## Output

```
plan complete:
- blueprint.md (N modules)
- chunks.yaml (M chunks, first: <chunk_id>)
```
````

- [ ] **Step 8.2: Commit**

```bash
git add skills/plan/SKILL.md
git commit -m "feat(skill): plan — blueprint + chunks decomposition"
```

---

## Task 9: `loop` skill

The inner build-measure-reflect cycle. This is the heart of Skillgoid.

**Files:**
- Create: `skills/loop/SKILL.md`

- [ ] **Step 9.1: Write `skills/loop/SKILL.md`**

````markdown
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

## Procedure

Setup
1. **Read** `.skillgoid/chunks.yaml` and `.skillgoid/criteria.yaml`. Find the chunk by ID.
2. **Resolve language:** chunk `language:` field > criteria `language:` field. If neither, ask the user.
3. **Resolve gates:** the subset of criteria.gates whose IDs appear in `chunk.gate_ids`.
4. **Determine loop budget:** `criteria.loop.max_attempts` (default 5).
5. **Create** `.skillgoid/iterations/` if absent.

Loop (iteration N = 1, 2, 3, ...)
6. **Build step.** Implement or fix code for this chunk. On iteration 1, build from scratch. On iteration N>1, inject the prior iteration's gate report and reflection as context and fix only what's failing.
7. **Measure step.** Invoke the language-adapter skill:
   - `language == "python"` → `skillgoid:python-gates` with `gate_ids=chunk.gate_ids`.
   - Other languages (v1+) → the matching adapter skill.
8. **Reflect step.** Write `.skillgoid/iterations/NNN.json` with:
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
     "failure_signature": "<hash of (gate_ids_failing + first 200 chars of stderr)>"
   }
   ```
   Mark `notable: true` when the reflection surfaces a non-obvious lesson (unexpected tool behavior, surprising library edge case, a design decision that changed the plan). Boring iterations stay `notable: false`.
9. **Exit conditions — evaluate in order:**
   - **Success:** `gate_report.passed == true` for all structured gates. Write a final iteration record with `exit_reason: "success"` and return.
   - **Budget exhausted:** `N >= max_attempts`. Write `exit_reason: "budget_exhausted"` and return with failure.
   - **No-progress stall:** `failure_signature` on this iteration matches the previous iteration. Write `exit_reason: "stalled"`, surface a summary to the user, and return with failure.
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
````

- [ ] **Step 9.2: Commit**

```bash
git add skills/loop/SKILL.md
git commit -m "feat(skill): loop — criteria-gated build-measure-reflect cycle"
```

---

## Task 10: `retrieve` skill

Language-detection + vault reader.

**Files:**
- Create: `skills/retrieve/SKILL.md`

- [ ] **Step 10.1: Write `skills/retrieve/SKILL.md`**

````markdown
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
````

- [ ] **Step 10.2: Commit**

```bash
git add skills/retrieve/SKILL.md
git commit -m "feat(skill): retrieve — read per-language vault files"
```

---

## Task 11: `retrospect` skill

End-of-project summary + vault curator.

**Files:**
- Create: `skills/retrospect/SKILL.md`

- [ ] **Step 11.1: Write `skills/retrospect/SKILL.md`**

````markdown
---
name: retrospect
description: Use after all chunks have passed their gates (or on explicit user request). Writes `.skillgoid/retrospective.md` summarizing the project, then curates notable iteration reflections into the user-global `~/.claude/skillgoid/vault/<language>-lessons.md`. Dedupes against existing entries and compresses older entries when the file exceeds 8K tokens.
---

# retrospect

## What this skill does

Two outputs:
1. **Project-local:** `.skillgoid/retrospective.md` — what worked, what didn't, what the final state is.
2. **User-global:** an *updated* `<language>-lessons.md` (and/or `meta-lessons.md`) in the vault, with this project's notable reflections integrated, deduped, and compressed if over the 8K-token threshold.

## Procedure

Step A — write the retrospective
1. Read all `.skillgoid/iterations/*.json` in order.
2. Read `.skillgoid/goal.md`, `.skillgoid/blueprint.md`, `.skillgoid/chunks.yaml`.
3. Write `.skillgoid/retrospective.md`:
   ```markdown
   # Retrospective — <goal title>

   ## Outcome
   <success | partial | abandoned>, final chunk state.

   ## What worked
   - ...

   ## What didn't
   - ...

   ## Surprises
   - <unexpected library behavior, wrong assumptions, design pivots>

   ## Stats
   - Chunks: N (M passed gates, K stalled)
   - Total iterations: T
   - Languages: <list>
   ```

Step B — curate the vault
4. Collect iteration records where `notable: true`. Extract the `reflection` text and surrounding context.
5. Determine target vault file(s): primary is `<language>-lessons.md`. If a reflection is language-neutral (e.g., about goal-clarification or gate-design), also/instead write it to `meta-lessons.md`.
6. Read the existing target file (if present).
7. **Integrate** the new notable reflections:
   - For each new reflection, look for related existing entries. If related, merge (prefer clearer language; keep the most recent specific example).
   - Add genuinely new lessons as new entries with a clear heading: `## <topic>`.
   - Drop or rewrite existing entries that the new project contradicts.
8. **Compress** if file > 8K tokens (approx 30KB):
   - Identify the least-recently-referenced entries (oldest `last_touched:` frontmatter or earliest section).
   - Summarize them into a trailing `## Distilled prior art` bullet list (one line per compressed entry).
   - Remove the full-length originals once summarized.
9. Write the updated file back.
10. Append a short log entry (optional): `~/.claude/skillgoid/vault/.log` records which projects contributed which lessons. Append-only, one line per contribution.

## File format for `<language>-lessons.md`

```markdown
# <language> lessons

<!-- curated by Skillgoid retrospect — edit with care -->

## <topic heading>

<the lesson, 1–4 paragraphs, concrete, with a specific example>

Last touched: YYYY-MM-DD by project "<slug>"

## <next topic>
...

## Distilled prior art

- <one-line summary of a compressed lesson>
- ...
```

## "Notable" rubric

A reflection is notable if it surfaces any of:
- A failure mode that took more than one attempt to diagnose.
- Unexpected behavior from a library, tool, or platform.
- A design decision that changed in response to new information.
- A gate that failed repeatedly for a non-obvious reason.

Routine green iterations are not notable. Do not promote them.

## Output

```
retrospect complete:
- retrospective.md written
- promoted N notable reflections to vault
- <language>-lessons.md updated (compression: <yes/no>)
```
````

- [ ] **Step 11.2: Commit**

```bash
git add skills/retrospect/SKILL.md
git commit -m "feat(skill): retrospect — retrospective + vault curation"
```

---

## Task 12: `build` skill (top-level orchestrator)

**Files:**
- Create: `skills/build/SKILL.md`

- [ ] **Step 12.1: Write `skills/build/SKILL.md`**

````markdown
---
name: build
description: Top-level Skillgoid orchestrator. Use when the user says "skillgoid build <goal>", "start a new project with skillgoid", or invokes `/skillgoid:build`. Routes to the appropriate sub-skill based on project state — fresh start, mid-loop, or ready-to-retrospect.
---

# build

## What this skill does

Routes a user request through the Skillgoid pipeline:

1. **No `.skillgoid/` directory yet** → `retrieve` → `clarify` → `plan` → for each chunk: `loop` → `retrospect`.
2. **`.skillgoid/` exists, chunks remaining** → resume at the current chunk with `loop`.
3. **`.skillgoid/` exists, all chunks passed** → `retrospect`.

## Inputs

- `rough_goal` (optional, required only on fresh start).
- `subcommand` (optional): `status`, `resume`, `retrospect-only`.

## Procedure

1. **Detect state** by inspecting the current working directory:
   - `.skillgoid/` exists? Check `chunks.yaml` and `iterations/` to determine which chunks have exited successfully.
   - No `.skillgoid/`? Fresh start.
2. **Dispatch:**

   Fresh start (`rough_goal` required):
   - Invoke `skillgoid:retrieve` with `rough_goal`.
   - Invoke `skillgoid:clarify`.
   - Invoke `skillgoid:plan`.
   - For each chunk in `chunks.yaml` in order: invoke `skillgoid:loop` with `chunk_id`. If a chunk exits with `stalled` or `budget_exhausted`, surface to user and stop — do NOT continue to subsequent chunks.
   - When all chunks succeed, invoke `skillgoid:retrospect`.

   Mid-project resume (`subcommand == "resume"` or default when `.skillgoid/` exists):
   - Report current state: "On chunk X of N. Chunk X last exited: <success | stalled | budget_exhausted | in-progress>".
   - Continue loop on the next incomplete chunk.

   Status only (`subcommand == "status"`):
   - Print a summary of chunks (passed, pending, current) and recent iteration outcomes.
   - Do not modify any files.

   Retrospect-only (`subcommand == "retrospect-only"`):
   - Invoke `skillgoid:retrospect` even if not all chunks passed. Used for abandoned projects.

3. **Always** commit any files written in `.skillgoid/` to git if the project is a git repo.

## Output

Stream progress updates after each sub-skill invocation. End with a final summary of what was built and where artifacts live.
````

- [ ] **Step 12.2: Commit**

```bash
git add skills/build/SKILL.md
git commit -m "feat(skill): build — top-level orchestrator"
```

---

## Task 13: Hooks — `detect-resume.sh` and `gate-guard.sh` + `hooks.json`

Hooks fire via the plugin manifest. Each hook is a bash script that reads project state and emits hook-protocol JSON to stdout.

**Files:**
- Create: `hooks/hooks.json`
- Create: `hooks/detect-resume.sh`
- Create: `hooks/gate-guard.sh`
- Create: `tests/test_detect_resume.py`
- Create: `tests/test_gate_guard.py`

- [ ] **Step 13.1: Write `hooks/hooks.json`**

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/detect-resume.sh"}
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/gate-guard.sh"}
        ]
      }
    ]
  }
}
```

Note: if `${CLAUDE_PLUGIN_ROOT}` is not the actual env var Claude Code exposes to plugin hooks, the README will document how to adjust. Verify with a smoke test in Task 17.

- [ ] **Step 13.2: Write failing tests for both hooks**

`tests/test_detect_resume.py`:
```python
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "detect-resume.sh"


def _run(cwd: Path) -> dict:
    env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(ROOT)}
    proc = subprocess.run(["bash", str(HOOK)], cwd=cwd, env=env, capture_output=True, text=True, check=False)
    if not proc.stdout.strip():
        return {}
    return json.loads(proc.stdout)


def test_no_skillgoid_dir_emits_nothing(tmp_path: Path):
    out = _run(tmp_path)
    # No-op outside a skillgoid project — empty or skip.
    assert out == {} or out.get("continue", True) is True


def test_active_project_emits_resume_context(tmp_path: Path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    (sg / "chunks.yaml").write_text("chunks:\n  - id: a\n    description: first\n    gate_ids: [pytest]\n")
    iters = sg / "iterations"
    iters.mkdir()
    (iters / "001.json").write_text(json.dumps({
        "iteration": 1, "chunk_id": "a", "exit_reason": "in_progress",
        "gate_report": {"passed": False, "results": [{"gate_id": "pytest", "passed": False}]}
    }))
    out = _run(tmp_path)
    assert "additionalContext" in out or "context" in out
    blob = json.dumps(out)
    assert "skillgoid" in blob.lower()
    assert "chunk" in blob.lower() or "iteration" in blob.lower()
```

`tests/test_gate_guard.py`:
```python
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "gate-guard.sh"


def _run(cwd: Path) -> dict:
    env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(ROOT)}
    proc = subprocess.run(["bash", str(HOOK)], cwd=cwd, env=env, capture_output=True, text=True, check=False)
    if not proc.stdout.strip():
        return {}
    return json.loads(proc.stdout)


def test_no_skillgoid_dir_does_not_block(tmp_path: Path):
    out = _run(tmp_path)
    # Outside skillgoid project, do not block.
    assert out == {} or out.get("decision") != "block"


def test_failing_gates_with_budget_blocks_stop(tmp_path: Path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    (sg / "criteria.yaml").write_text("loop:\n  max_attempts: 5\ngates: []\n")
    (sg / "chunks.yaml").write_text("chunks:\n  - id: a\n    description: x\n    gate_ids: [pytest]\n")
    iters = sg / "iterations"
    iters.mkdir()
    (iters / "001.json").write_text(json.dumps({
        "iteration": 1, "chunk_id": "a",
        "gate_report": {"passed": False, "results": [{"gate_id": "pytest", "passed": False}]},
        "exit_reason": "in_progress"
    }))
    out = _run(tmp_path)
    assert out.get("decision") == "block"
    assert "gates still failing" in out.get("reason", "").lower()


def test_all_gates_pass_allows_stop(tmp_path: Path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    (sg / "chunks.yaml").write_text("chunks:\n  - id: a\n    description: x\n    gate_ids: [pytest]\n")
    iters = sg / "iterations"
    iters.mkdir()
    (iters / "001.json").write_text(json.dumps({
        "iteration": 1, "chunk_id": "a",
        "gate_report": {"passed": True, "results": [{"gate_id": "pytest", "passed": True}]},
        "exit_reason": "success"
    }))
    out = _run(tmp_path)
    assert out.get("decision") != "block"
```

- [ ] **Step 13.3: Run tests — confirm they fail**

Run: `pytest tests/test_detect_resume.py tests/test_gate_guard.py -v`
Expected: fail — scripts missing.

- [ ] **Step 13.4: Write `hooks/detect-resume.sh`**

```bash
#!/usr/bin/env bash
# SessionStart hook: if CWD contains .skillgoid/, emit a one-paragraph resume summary.
set -euo pipefail

cwd="${CLAUDE_PROJECT_DIR:-$PWD}"
sg="$cwd/.skillgoid"

if [ ! -d "$sg" ]; then
  # Not a Skillgoid project — emit nothing.
  exit 0
fi

chunks_file="$sg/chunks.yaml"
iters_dir="$sg/iterations"

summary="Resuming Skillgoid project at $cwd."
if [ -f "$chunks_file" ]; then
  chunk_count=$(grep -c "^  - id:" "$chunks_file" || echo 0)
  summary="$summary chunks.yaml defines $chunk_count chunk(s)."
fi

if [ -d "$iters_dir" ]; then
  latest=$(ls -1 "$iters_dir"/*.json 2>/dev/null | sort | tail -n1 || true)
  if [ -n "$latest" ]; then
    chunk_id=$(python3 -c "import json,sys; print(json.load(open('$latest')).get('chunk_id', '?'))")
    exit_reason=$(python3 -c "import json,sys; print(json.load(open('$latest')).get('exit_reason', 'in_progress'))")
    gates_passed=$(python3 -c "import json; r=json.load(open('$latest')).get('gate_report',{}); print(r.get('passed','?'))")
    summary="$summary Latest iteration: chunk=$chunk_id, exit=$exit_reason, gates_passed=$gates_passed."
  fi
fi

# Emit context-injection JSON per Claude Code hook protocol.
python3 - <<PY
import json, sys
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": """$summary Use \`/skillgoid:build resume\` to continue, or \`/skillgoid:build status\` to inspect."""
    }
}))
PY
```

Make executable:
```bash
chmod +x hooks/detect-resume.sh
```

- [ ] **Step 13.5: Write `hooks/gate-guard.sh`**

```bash
#!/usr/bin/env bash
# Stop hook: if active Skillgoid session has failing gates and loop budget remains, block the stop.
set -euo pipefail

cwd="${CLAUDE_PROJECT_DIR:-$PWD}"
sg="$cwd/.skillgoid"

if [ ! -d "$sg" ]; then
  exit 0
fi

iters_dir="$sg/iterations"
if [ ! -d "$iters_dir" ]; then
  exit 0
fi

latest=$(ls -1 "$iters_dir"/*.json 2>/dev/null | sort | tail -n1 || true)
if [ -z "$latest" ]; then
  exit 0
fi

python3 - <<PY "$sg" "$latest"
import json, sys, yaml
sg, latest = sys.argv[1], sys.argv[2]
rec = json.load(open(latest))
exit_reason = rec.get("exit_reason", "in_progress")
report = rec.get("gate_report", {})
passed = report.get("passed", True)

if passed or exit_reason in ("success",):
    sys.exit(0)

# Check budget
max_attempts = 5
try:
    crit = yaml.safe_load(open(f"{sg}/criteria.yaml"))
    max_attempts = (crit or {}).get("loop", {}).get("max_attempts", 5)
except Exception:
    pass
iteration = rec.get("iteration", 0)

if iteration >= max_attempts or exit_reason in ("budget_exhausted", "stalled"):
    # Budget already exhausted — allow stop.
    sys.exit(0)

failing_ids = [r.get("gate_id") for r in report.get("results", []) if not r.get("passed")]
reason = (
    f"Skillgoid: gates still failing ({', '.join(failing_ids) or 'unknown'}) and "
    f"loop budget remains ({iteration}/{max_attempts}). Continue iterating with /skillgoid:build resume, "
    f"or break explicitly with /skillgoid:build retrospect-only."
)
print(json.dumps({"decision": "block", "reason": reason}))
PY
```

Make executable:
```bash
chmod +x hooks/gate-guard.sh
```

- [ ] **Step 13.6: Run hook tests**

Run: `pytest tests/test_detect_resume.py tests/test_gate_guard.py -v`
Expected: all tests pass.

- [ ] **Step 13.7: Commit**

```bash
git add hooks/ tests/test_detect_resume.py tests/test_gate_guard.py
git commit -m "feat(hooks): detect-resume (SessionStart) and gate-guard (Stop)"
```

---

## Task 14: Plugin manifest `.claude-plugin/plugin.json`

**Files:**
- Create: `.claude-plugin/plugin.json`

- [ ] **Step 14.1: Write the manifest**

```json
{
  "name": "skillgoid",
  "version": "0.1.0",
  "description": "Criteria-gated autonomous build loop with per-language compounding memory. Define success, build, measure, reflect, loop until gates pass.",
  "author": {"name": "flip"},
  "license": "MIT",
  "repository": "https://github.com/<your-handle>/skillgoid",
  "keywords": ["autonomous-builder", "criteria-loop", "skills", "plugin", "memory-vault"],
  "hooks": "./hooks/hooks.json"
}
```

`skills/` is auto-discovered; no need to list it explicitly in the manifest (per the plugin spec).

- [ ] **Step 14.2: Verify manifest JSON is valid**

Run: `python -c "import json; json.load(open('.claude-plugin/plugin.json'))"`
Expected: no output, exit 0.

- [ ] **Step 14.3: Commit**

```bash
git add .claude-plugin/plugin.json
git commit -m "feat(plugin): manifest registers skills and hooks"
```

---

## Task 15: README + quickstart + custom-adapter doc

**Files:**
- Modify: `README.md` (full rewrite from stub)
- Create: `docs/custom-adapter-template.md`

- [ ] **Step 15.1: Rewrite `README.md`**

````markdown
# Skillgoid

**A Claude Code plugin that turns a rough project goal into a shipped codebase through a criteria-gated build loop with compounding cross-project memory.**

- **Define success** — measurable gates, not "I think it's done".
- **Build → measure → reflect** — loop until the gates pass.
- **Learn across projects** — a curated per-language lessons file grows smarter with every project.

## Install

```bash
claude plugin install <git-url-or-local-path>
```

Or for local development:
```bash
git clone https://github.com/<your-handle>/skillgoid.git
cd skillgoid
claude plugin install .
```

## 60-second quickstart

1. Open a fresh, empty directory.
2. In Claude Code, run:
   ```
   /skillgoid:build "a Python CLI that syncs my Notion tasks to a local JSON file"
   ```
3. Answer a few clarifying questions when prompted.
4. Approve the draft `goal.md`, `criteria.yaml`, and `chunks.yaml`.
5. Skillgoid builds chunk-by-chunk, measuring gates each iteration. You watch (or step away). When the loop stalls or completes, you'll see a summary.
6. On success, a `retrospective.md` lands in `.skillgoid/` and notable lessons are curated into `~/.claude/skillgoid/vault/python-lessons.md`.

## Concepts

- **`.skillgoid/`** — project-local state: `goal.md`, `criteria.yaml`, `blueprint.md`, `chunks.yaml`, `iterations/NNN.json`, `retrospective.md`.
- **`~/.claude/skillgoid/vault/`** — user-global curated lessons: one `<language>-lessons.md` per language, plus optional `meta-lessons.md`.
- **Gates** — structured measurements (`pytest`, `ruff`, `mypy`, `import-clean`, `cli-command-runs`, `run-command`). Loop termination is defined in terms of these.
- **Acceptance scenarios** — free-form success stories. Inform test-writing but do not block the loop.
- **Hooks** — `SessionStart` injects resume context; `Stop` warns when you try to stop mid-loop with failing gates.

## Commands

- `/skillgoid:build "<goal>"` — start a new project.
- `/skillgoid:build resume` — continue the current project.
- `/skillgoid:build status` — print chunk + iteration summary.
- `/skillgoid:build retrospect-only` — finalize even if gates didn't all pass.
- `/skillgoid:clarify`, `/skillgoid:plan`, `/skillgoid:loop`, `/skillgoid:retrieve`, `/skillgoid:retrospect` — sub-skills, directly invokable.

## Custom language adapters

Skillgoid v0 ships with `python-gates`. See [docs/custom-adapter-template.md](docs/custom-adapter-template.md) to write your own for Node, Go, Rust, etc.

## Design

Full spec: [docs/superpowers/specs/2026-04-17-skillgoid-design.md](docs/superpowers/specs/2026-04-17-skillgoid-design.md).

## Licence

MIT.
````

- [ ] **Step 15.2: Write `docs/custom-adapter-template.md`**

````markdown
# Writing a custom Skillgoid gate adapter

A gate adapter is a single skill that, invoked with a project path + criteria, runs gates and returns a structured JSON report.

## Contract

**Input** (from the `loop` skill):
- `project_path`
- `criteria_path` (or criteria subset)
- optional `gate_ids` filter

**Output:**
```json
{
  "passed": true,
  "results": [
    {"gate_id": "string", "passed": true, "stdout": "...", "stderr": "...", "hint": "..."}
  ]
}
```

## Minimal skill skeleton

Create `skills/<language>-gates/SKILL.md`:

````markdown
---
name: <language>-gates
description: Use to measure gates for <language> projects. Invoked by the `loop` skill when chunk language is `<language>`.
---

# <language>-gates

## Procedure

1. Read criteria from the specified path, filter by gate_ids if provided.
2. For each gate, invoke the right tool (test runner, linter, etc.) and capture stdout/stderr/exit code.
3. Assemble the JSON report.
4. Return the report verbatim.
````

## Tips

- Prefer a small companion script in `scripts/measure_<language>.py` (or similar) and have the skill shell out to it. Skills are prose; scripts are code.
- Always return valid JSON on stdout even on partial failure. Never crash the adapter.
- If a gate type isn't supported, emit a failed result with `hint: "unsupported gate type: X"` — don't invent behavior.
````

- [ ] **Step 15.3: Commit**

```bash
git add README.md docs/custom-adapter-template.md
git commit -m "docs: README quickstart + custom adapter template"
```

---

## Task 16: Smoke test — example `hello-cli` project

A minimal fixture to eyeball that the full pipeline works end-to-end against a real plugin install.

**Files:**
- Create: `examples/hello-cli/goal.md`
- Create: `examples/hello-cli/README.md`

- [ ] **Step 16.1: Write `examples/hello-cli/goal.md`**

```markdown
# Example starting goal

Build a tiny Python CLI called `hello-cli` that:
- prints "hello, <name>!" when run with `hello-cli greet --name <name>`
- exits 0 on success
- has `--help` that documents the `greet` subcommand

Used to smoke-test Skillgoid end-to-end.
```

- [ ] **Step 16.2: Write `examples/hello-cli/README.md`**

````markdown
# Skillgoid end-to-end smoke test

To verify your install works:

```bash
mkdir -p /tmp/skillgoid-smoke && cd /tmp/skillgoid-smoke
cp <plugin-root>/examples/hello-cli/goal.md .
claude
```

Then in Claude Code:
```
/skillgoid:build "$(cat goal.md)"
```

You should see:
1. A clarifying Q&A pass.
2. Draft `goal.md` and `criteria.yaml` for your approval.
3. A `blueprint.md` and `chunks.yaml`.
4. One or more build iterations, each writing `.skillgoid/iterations/NNN.json`.
5. A `retrospective.md` when gates pass.
6. A new or updated `~/.claude/skillgoid/vault/python-lessons.md`.

If the `Stop` hook fires before completion with a message like "gates still failing", that's correct — it means the hook is wired up.
````

- [ ] **Step 16.3: Manually smoke-test once**

Install the plugin locally and run the flow on `hello-cli`. This is a manual QA step — no automated assertion. Verify:
- Plugin appears in `/plugin` UI.
- `/skillgoid:build` invokes `retrieve → clarify → plan → loop → retrospect`.
- `SessionStart` hook prints a resume summary when you reopen a `.skillgoid/` directory.
- `Stop` hook blocks when gates are red with budget remaining.

Record any issues in `docs/smoke-test-notes.md` and fix before shipping.

- [ ] **Step 16.4: Commit**

```bash
git add examples/
git commit -m "docs: hello-cli smoke-test example"
```

---

## Task 17: CI — GitHub Actions for pytest

**Files:**
- Create: `.github/workflows/test.yml`

- [ ] **Step 17.1: Write `.github/workflows/test.yml`**

```yaml
name: tests

on:
  pull_request:
  push:

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - name: Install
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]"
      - name: Lint
        run: ruff check .
      - name: Test
        run: pytest -v
```

- [ ] **Step 17.2: Verify the workflow YAML is valid**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/test.yml'))"`
Expected: no output, exit 0.

- [ ] **Step 17.3: Commit**

```bash
git add .github/workflows/test.yml
git commit -m "ci: pytest + ruff matrix"
```

---

## Self-review (author pass)

1. **Spec coverage:** every section of the spec is implemented.
   - §3 Core concept (criteria-first + loop + vault): ✓ Tasks 2, 7, 9, 10, 11.
   - §4 Architecture (6 skills + 1 adapter + 2 hooks): ✓ Tasks 6–13.
   - §5 Data layout (project-local + user-global): ✓ Task 10 (read), Task 11 (write).
   - §7 Gate adapter contract: ✓ Tasks 3–6.
   - §8 Hooks: ✓ Task 13.
   - §9 Loop-break conditions: ✓ Task 9 step 9 (exit conditions in order).
   - §10 Distribution: ✓ Tasks 14 (manifest), 15 (README), 17 (CI).
   - §11 Out-of-scope items (Chroma, MCP, etc.) — nothing in plan touches them. ✓
   - §12 Defaults baked in: max_attempts=5 (schema default + loop skill), 8K compression threshold (retrospect skill), Python-only adapter (Task 6 only), MIT license (Task 1.3).
   - §13 Open questions: flagged as TODOs to be resolved *during* the relevant task rather than postponed — (1) plugin hook format confirmed via claude-code-guide agent; (2) language detection fallback chain spelled out in Task 10; (3) multi-language projects: acknowledged but not implemented in v0 — single-language per chunk; (4) compression heuristic: least-recently-referenced, chosen in Task 11 step 8; (5) notable rubric: spelled out in Task 11; (6) subagent-per-chunk: not done in v0, `loop` runs in main session (flag for v1); (7) stall signature: hash of `(failing gate IDs + first 200 chars of stderr)` per Task 9 iteration record.

2. **Placeholder scan:** no "TBD", "TODO", "fill in later" in code or skill bodies. The repository URL in the manifest (`https://github.com/<your-handle>/skillgoid`) is the one exception — explicitly user-configurable at ship time.

3. **Type/name consistency:** `measure_python.py`, `python-gates`, `GATE_DISPATCH`, `GateResult`, gate IDs (`pytest`, `ruff`, `mypy`, `import-clean`, `cli-command-runs`, `run-command`) are consistent across Tasks 3–6 and referenced correctly in Tasks 2 (schema enum), 9 (loop-skill gates mention), 15 (README). The JSON report shape (`{passed, results[{gate_id, passed, stdout, stderr, hint}]}`) is consistent across scripts/measure_python.py, skills/python-gates/SKILL.md, and the hook tests.

4. **Gap check:** two v0 items I deliberately elided —
   - **No `subagent-per-chunk` isolation** (spec §13 Q6 flagged this as "probably subagent-per-chunk"). In v0 `loop` runs in the main Claude session. Revisit in v1 if context bloat bites. Acceptable for ship.
   - **Multi-language projects** are not supported in v0 (one language per chunk, one adapter per language). Spec §13 Q3 flagged this. README is honest — quickstart uses a single-language example. Acceptable for ship.

---

## Execution handoff

Plan complete and committed to `docs/superpowers/plans/2026-04-17-skillgoid-v0.md`. Two execution options:

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration.
**2. Inline Execution** — execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints.

Which approach?
