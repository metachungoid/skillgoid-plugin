# Skillgoid v0.3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Skillgoid v0.3 — the Polish & Observe bundle. Six additive improvements that sharpen what v0.2 does, with zero architectural change.

**Architecture:** All six changes ride inside v0.2's existing structures. Two new helper scripts (`scripts/diff_summary.py`, `scripts/metrics_append.py`), extensions to `scripts/measure_python.py` (timeout + coverage gate), schema additions to `criteria.schema.json` (timeout field, coverage enum, models block) and `iterations.schema.json` (changes object), and small prose updates to `loop`, `build`, `clarify`, `retrospect` skills plus `hooks/gate-guard.sh`. No new skills, no new hooks, no new user-facing commands.

**Tech Stack:** Python 3.11+ (pytest, pyyaml, jsonschema, pytest-cov — all already in dev deps), bash (hooks), Claude Code skills (markdown + YAML). No new runtime dependencies.

**Backward compatibility:** Fully additive. All v0.2 `criteria.yaml` / iteration records parse unchanged. Missing `timeout` → default 300s. Missing `models` → v0.2 hardcoded defaults. Missing `coverage` gate → no behavior change. Missing `changes` field → tolerated. `metrics.jsonl` is write-only on retrospect.

**Spec:** `docs/superpowers/specs/2026-04-17-skillgoid-v0.3-polish-observe.md` (commit `03fef53`).
**Roadmap:** `docs/roadmap.md`.

---

## Repo layout changes

```
skillgoid-plugin/
├── scripts/
│   ├── measure_python.py              # MODIFIED: timeout support + _gate_coverage
│   ├── diff_summary.py                # NEW
│   ├── metrics_append.py              # NEW
│   ├── stall_check.py                 # unchanged
│   └── git_iter_commit.py             # unchanged
├── schemas/
│   ├── criteria.schema.json           # MODIFIED: timeout, coverage in enum, models block
│   ├── iterations.schema.json         # MODIFIED: changes object
│   └── chunks.schema.json             # unchanged
├── skills/
│   ├── loop/SKILL.md                  # MODIFIED: diff-summary step after git commit
│   ├── build/SKILL.md                 # MODIFIED: read criteria.models for Agent calls
│   ├── clarify/SKILL.md               # MODIFIED: propose default coverage gate
│   ├── retrospect/SKILL.md            # MODIFIED: append metrics.jsonl line
│   ├── python-gates/SKILL.md          # MODIFIED (minor): timeout field is honored
│   └── (plan, retrieve — unchanged)
├── hooks/
│   ├── gate-guard.sh                  # MODIFIED: surface failing gate hints
│   ├── detect-resume.sh               # unchanged
│   └── hooks.json                     # unchanged
├── tests/
│   ├── test_timeout.py                # NEW
│   ├── test_coverage_gate.py          # NEW
│   ├── test_diff_summary.py           # NEW
│   ├── test_metrics_append.py         # NEW
│   ├── test_gate_guard.py             # MODIFIED: add hint-surfacing test
│   ├── test_schemas.py                # MODIFIED: timeout, coverage, models, changes tests
│   └── (all v0.2 tests unchanged)
├── README.md                          # MODIFIED: v0.3 section
├── CHANGELOG.md                       # MODIFIED: [0.3.0] entry
└── docs/
    └── roadmap.md                     # MODIFIED: mark v0.3 shipped, refine v0.4
```

---

## Task 1: Adapter timeouts

Add optional `timeout` field to gate schema. All gate handlers in `measure_python.py` honor it; `subprocess.TimeoutExpired` converts to a clean failing `GateResult`.

**Files:**
- Modify: `schemas/criteria.schema.json`
- Modify: `scripts/measure_python.py`
- Create: `tests/test_timeout.py`
- Modify: `tests/test_schemas.py`

- [ ] **Step 1.1: Write failing tests — `tests/test_timeout.py`**

```python
"""Adapter timeout handling — gates that exceed their timeout fail with a
clean GateResult instead of hanging the adapter forever.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "scripts" / "measure_python.py"


def run_cli(criteria_yaml: str, project_path: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(ADAPTER), "--project", str(project_path), "--criteria-stdin"],
        input=criteria_yaml,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,  # test harness: kill if adapter itself hangs
    )
    return json.loads(result.stdout)


def test_gate_under_timeout_passes(tmp_path: Path):
    criteria = """
gates:
  - id: fast
    type: run-command
    command: ["echo", "ok"]
    expect_exit: 0
    timeout: 5
"""
    report = run_cli(criteria, tmp_path)
    assert report["passed"] is True
    assert report["results"][0]["passed"] is True


def test_gate_over_timeout_fails_cleanly(tmp_path: Path):
    # `sleep 10` vs. `timeout: 1` — must fail fast with a clear hint.
    criteria = """
gates:
  - id: slow
    type: run-command
    command: ["sleep", "10"]
    timeout: 1
"""
    report = run_cli(criteria, tmp_path)
    assert report["passed"] is False
    result = report["results"][0]
    assert result["passed"] is False
    assert "timed out" in result["hint"].lower()
    assert "1s" in result["hint"] or "1 s" in result["hint"].replace(" ", " ")
```

- [ ] **Step 1.2: Run — confirm failure**

```bash
cd /home/flip/Development/skillgoid/skillgoid-plugin
. .venv/bin/activate
pytest tests/test_timeout.py -v
```
Expected: both tests fail (adapter doesn't honor `timeout` yet).

- [ ] **Step 1.3: Update `schemas/criteria.schema.json`**

In the gate item properties (both inside `gates[]` and `integration_gates[]`), add:

```json
"timeout": {"type": "integer", "minimum": 1, "default": 300, "description": "Seconds before the gate is killed and fails. Default 300."}
```

Add this property to both `gates[].items.properties` and `integration_gates[].items.properties`. Don't add to `required` — it's optional.

- [ ] **Step 1.4: Update `scripts/measure_python.py` — timeout param everywhere**

Add a module constant:
```python
DEFAULT_GATE_TIMEOUT = 300
```

Modify `_run` to accept timeout:
```python
def _run(cmd: list[str], cwd: Path, timeout: int | None = None) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, check=False, timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return 124, out, err  # 124 is a conventional timeout exit code
    return proc.returncode, proc.stdout, proc.stderr
```

In each gate handler that calls `subprocess.run` directly (`_gate_pytest`, `_gate_ruff`, `_gate_mypy`, `_gate_import_clean`, `_gate_cli_command_runs`) AND the `_gate_run_command` path, replace the raw `subprocess.run(...)` with the `_run(...)` helper and pass `timeout=gate.get("timeout", DEFAULT_GATE_TIMEOUT)`.

Then catch the `124` return in each handler:
```python
if code == 124:
    return GateResult(
        gate["id"], False, out, err,
        f"gate timed out after {timeout}s — check for infinite loops or hung I/O",
    )
```

Place this check right before the normal pass/fail computation.

For `_gate_pytest` which currently uses `subprocess.run` with custom env:
```python
def _gate_pytest(gate: dict, project: Path) -> GateResult:
    args = gate.get("args") or []
    timeout = gate.get("timeout", DEFAULT_GATE_TIMEOUT)
    env_path = str(project / "src")
    existing = os.environ.get("PYTHONPATH", "")
    env = {**os.environ, "PYTHONPATH": env_path + (os.pathsep + existing if existing else "")}
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", *args],
            cwd=project,
            capture_output=True,
            text=True,
            env=env,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or b"").decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err = (exc.stderr or b"").decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return GateResult(gate["id"], False, out, err, f"gate timed out after {timeout}s — check for infinite loops or hung I/O")
    passed = proc.returncode == 0
    hint = "" if passed else "pytest exited nonzero — read stdout for failing test names"
    return GateResult(gate["id"], passed, proc.stdout, proc.stderr, hint)
```

Apply the same pattern to `_gate_ruff`, `_gate_mypy`, `_gate_import_clean`. For `_gate_cli_command_runs` and `_gate_run_command`, use the updated `_run()` helper.

- [ ] **Step 1.5: Add schema test to `tests/test_schemas.py`**

Append:
```python
def test_criteria_gate_timeout_is_integer():
    data = {"gates": [{"id": "p", "type": "pytest", "timeout": 60}]}
    errors = list(_validator("criteria.schema.json").iter_errors(data))
    assert errors == []


def test_criteria_gate_timeout_must_be_positive():
    data = {"gates": [{"id": "p", "type": "pytest", "timeout": 0}]}
    errors = list(_validator("criteria.schema.json").iter_errors(data))
    assert any(e.validator == "minimum" for e in errors)
```

- [ ] **Step 1.6: Run tests**

```bash
pytest -v && ruff check .
```
Expected: 58 tests (54 + 2 timeout + 2 schema), ruff clean.

- [ ] **Step 1.7: Commit**

```bash
git add scripts/measure_python.py schemas/criteria.schema.json tests/test_timeout.py tests/test_schemas.py
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "feat(gates): per-gate timeout support (default 300s)

All gate handlers honor an optional `timeout` field; TimeoutExpired
converts to a failed GateResult with a clear hint instead of hanging
the adapter. Default 300s when unspecified. Applies to run-command,
pytest, ruff, mypy, import-clean, cli-command-runs."
```

---

## Task 2: Coverage gate (floor check)

Adds `coverage` to the gate-type enum, implements the min-percent check via pytest-cov. Baseline regression check comes in Task 3.

**Files:**
- Modify: `schemas/criteria.schema.json` (enum + optional properties)
- Modify: `scripts/measure_python.py` (add `_gate_coverage`, register in GATE_DISPATCH)
- Create: `tests/test_coverage_gate.py`
- Create: `tests/fixtures/low-coverage-project/` (pyproject, src/mypkg with uncovered code, 1 trivial test)

- [ ] **Step 2.1: Write failing tests — `tests/test_coverage_gate.py`**

```python
"""Coverage gate — pytest-cov-based floor check and (in Task 3) baseline
regression check.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "scripts" / "measure_python.py"
PASSING = ROOT / "tests" / "fixtures" / "passing-project"
LOW_COV = ROOT / "tests" / "fixtures" / "low-coverage-project"


def run_cli(criteria_yaml: str, project_path: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(ADAPTER), "--project", str(project_path), "--criteria-stdin"],
        input=criteria_yaml,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    return json.loads(result.stdout)


def test_coverage_gate_passes_when_above_floor():
    # passing-project has one function (add), one test (test_add) → 100% cov.
    criteria = """
gates:
  - id: cov
    type: coverage
    target: mypkg
    min_percent: 80
"""
    report = run_cli(criteria, PASSING)
    assert report["passed"] is True
    assert report["results"][0]["gate_id"] == "cov"
    # Current percent stored in stdout for later iterations to read as baseline
    assert "coverage:" in report["results"][0]["stdout"].lower()
    assert "100" in report["results"][0]["stdout"]


def test_coverage_gate_fails_below_floor():
    # low-coverage-project has mostly-untested code.
    criteria = """
gates:
  - id: cov
    type: coverage
    target: mypkg
    min_percent: 80
"""
    report = run_cli(criteria, LOW_COV)
    assert report["passed"] is False
    hint = report["results"][0]["hint"].lower()
    assert "below floor" in hint or "coverage" in hint
    assert "80" in report["results"][0]["hint"]


def test_coverage_gate_handles_missing_pytest_cov(tmp_path: Path):
    # In a completely empty project, pytest-cov will have no tests to run.
    # The handler should fail cleanly (no-data, not crash).
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="empty"\nversion="0.0.1"\nrequires-python=">=3.11"\n'
    )
    criteria = """
gates:
  - id: cov
    type: coverage
    target: empty
    min_percent: 80
"""
    report = run_cli(criteria, tmp_path)
    # Either we get a coverage=0% fail, or a clean "no coverage data" fail.
    assert report["passed"] is False
    assert report["results"][0]["gate_id"] == "cov"
```

- [ ] **Step 2.2: Create `tests/fixtures/low-coverage-project/`**

`tests/fixtures/low-coverage-project/pyproject.toml`:
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

`tests/fixtures/low-coverage-project/src/mypkg/__init__.py`:
```python
"""mypkg — low-coverage fixture."""


def add(a: int, b: int) -> int:
    return a + b


def subtract(a: int, b: int) -> int:
    return a - b


def multiply(a: int, b: int) -> int:
    return a * b


def divide(a: int, b: int) -> float:
    if b == 0:
        raise ValueError("cannot divide by zero")
    return a / b
```

`tests/fixtures/low-coverage-project/tests/test_trivial.py`:
```python
from mypkg import add


def test_add():
    assert add(1, 2) == 3
```

Only `add` is tested — `subtract`, `multiply`, `divide`, and the `ValueError` branch are uncovered. Coverage should land around 40%, well below the 80% floor.

- [ ] **Step 2.3: Run tests — confirm failure**

```bash
pytest tests/test_coverage_gate.py -v
```
Expected: all 3 tests fail — `coverage` is not yet in the gate enum.

- [ ] **Step 2.4: Update `schemas/criteria.schema.json`**

Add `"coverage"` to the gate-type enum (both inside `gates[]` and `integration_gates[]`). Add new optional properties:

```json
"target": {"type": "string", "description": "Package or path to measure coverage for. Default '.'"},
"min_percent": {"type": "integer", "minimum": 0, "maximum": 100, "default": 80},
"compare_to_baseline": {"type": "boolean", "default": false}
```

- [ ] **Step 2.5: Implement `_gate_coverage` in `scripts/measure_python.py`**

Add at the top of the file (new import):
```python
import tempfile
```

Add the handler:
```python
def _gate_coverage(gate: dict, project: Path) -> GateResult:
    target = gate.get("target") or "."
    min_percent = gate.get("min_percent", 80)
    timeout = gate.get("timeout", DEFAULT_GATE_TIMEOUT)

    # Env with src on PYTHONPATH (same pattern as _gate_pytest)
    env_path = str(project / "src")
    existing = os.environ.get("PYTHONPATH", "")
    env = {**os.environ, "PYTHONPATH": env_path + (os.pathsep + existing if existing else "")}

    # Write coverage JSON to a tmp file to avoid polluting project root
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, dir=str(project)
    ) as tf:
        cov_path = Path(tf.name)

    try:
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest",
                 f"--cov={target}",
                 f"--cov-report=json:{cov_path}",
                 "--cov-report=",  # suppress terminal report
                 "-q"],
                cwd=project,
                capture_output=True,
                text=True,
                env=env,
                check=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            out = (exc.stdout or b"").decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            err = (exc.stderr or b"").decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            return GateResult(gate["id"], False, out, err, f"gate timed out after {timeout}s — check for infinite loops or hung I/O")

        # pytest-cov may exit 0 or 1 depending on pytest result; coverage is
        # still generated. Fail fast if the file wasn't written.
        if not cov_path.exists() or cov_path.stat().st_size == 0:
            return GateResult(
                gate["id"], False, proc.stdout, proc.stderr,
                "coverage report not generated — is pytest-cov installed in the target project?",
            )

        try:
            cov_data = json.loads(cov_path.read_text())
            percent = float(cov_data["totals"]["percent_covered"])
        except Exception as exc:
            return GateResult(gate["id"], False, proc.stdout, proc.stderr,
                              f"failed to parse coverage.json: {exc}")

        stdout_summary = f"coverage: {percent:.1f}%"
        if percent < min_percent:
            return GateResult(
                gate["id"], False, stdout_summary, proc.stderr,
                f"coverage {percent:.1f}% below floor {min_percent}%",
            )
        return GateResult(gate["id"], True, stdout_summary, proc.stderr, "")
    finally:
        try:
            cov_path.unlink()
        except FileNotFoundError:
            pass
```

Register in `GATE_DISPATCH`:
```python
GATE_DISPATCH = {
    "run-command": _gate_run_command,
    "pytest": _gate_pytest,
    "ruff": _gate_ruff,
    "mypy": _gate_mypy,
    "import-clean": _gate_import_clean,
    "cli-command-runs": _gate_cli_command_runs,
    "coverage": _gate_coverage,
}
```

- [ ] **Step 2.6: Run tests**

```bash
pytest tests/test_coverage_gate.py -v
```
Expected: 3 tests pass.

- [ ] **Step 2.7: Full suite + ruff**

```bash
pytest -v && ruff check .
```
Expected: 61 total (58 + 3), ruff clean.

- [ ] **Step 2.8: Commit**

```bash
git add schemas/criteria.schema.json scripts/measure_python.py tests/test_coverage_gate.py tests/fixtures/low-coverage-project/
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "feat(gates): coverage gate — floor check via pytest-cov

New gate type 'coverage' honoring min_percent. Writes the current
coverage percent to stdout as 'coverage: X.Y%' so later iterations
can parse it as a baseline (regression check lands in Task 3).

Ships with a low-coverage-project fixture exercising the failure
path (add() tested, subtract/multiply/divide untested → ~40%)."
```

---

## Task 3: Coverage gate — baseline regression check

Extends `_gate_coverage` to optionally fail when coverage regresses vs. the previous iteration.

**Files:**
- Modify: `scripts/measure_python.py`
- Modify: `tests/test_coverage_gate.py`

- [ ] **Step 3.1: Write failing test — append to `tests/test_coverage_gate.py`**

```python
def test_coverage_gate_regression_detection(tmp_path: Path):
    """Given a prior iteration with higher coverage, a current run with lower
    coverage fails on compare_to_baseline=true."""
    # Arrange — simulate project with .skillgoid/iterations/001.json showing
    # a coverage gate that previously reported 90%.
    project = tmp_path / "proj"
    project.mkdir()
    # Reuse the low-coverage-project contents so current run yields ~40%.
    for path in (LOW_COV).rglob("*"):
        if path.is_file():
            target = project / path.relative_to(LOW_COV)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())

    sg = project / ".skillgoid"
    iters = sg / "iterations"
    iters.mkdir(parents=True)
    (iters / "001.json").write_text(json.dumps({
        "iteration": 1,
        "chunk_id": "demo",
        "gate_report": {
            "passed": True,
            "results": [
                {"gate_id": "cov", "passed": True, "stdout": "coverage: 90.0%",
                 "stderr": "", "hint": ""}
            ],
        },
    }))

    criteria = """
gates:
  - id: cov
    type: coverage
    target: mypkg
    min_percent: 10
    compare_to_baseline: true
"""
    report = run_cli(criteria, project)
    assert report["passed"] is False
    hint = report["results"][0]["hint"].lower()
    assert "regress" in hint or "dropped" in hint
```

- [ ] **Step 3.2: Run — confirm failure**

```bash
pytest tests/test_coverage_gate.py::test_coverage_gate_regression_detection -v
```
Expected: FAIL — regression check not yet implemented.

- [ ] **Step 3.3: Extend `_gate_coverage` with baseline comparison**

After the min_percent check in `_gate_coverage`, but before the final return, add:

```python
if gate.get("compare_to_baseline", False):
    baseline = _find_prior_coverage(project, gate["id"])
    if baseline is not None:
        # Allow 0.5pp tolerance for floating-point noise
        if percent < baseline - 0.5:
            return GateResult(
                gate["id"], False, stdout_summary, proc.stderr,
                f"coverage regressed from {baseline:.1f}% to {percent:.1f}%",
            )
```

Add the helper:
```python
import re as _re

_COVERAGE_RE = _re.compile(r"coverage:\s*([0-9.]+)%", _re.IGNORECASE)


def _find_prior_coverage(project: Path, gate_id: str) -> float | None:
    """Find the most recent prior iteration's coverage gate result.
    Returns the percent as float, or None if no prior record."""
    iters_dir = project / ".skillgoid" / "iterations"
    if not iters_dir.is_dir():
        return None
    iter_files = sorted(iters_dir.glob("*.json"), reverse=True)
    for path in iter_files:
        try:
            rec = json.loads(path.read_text())
        except Exception:
            continue
        for r in (rec.get("gate_report", {}).get("results") or []):
            if r.get("gate_id") == gate_id and r.get("passed"):
                match = _COVERAGE_RE.search(r.get("stdout") or "")
                if match:
                    return float(match.group(1))
    return None
```

(Note: `_re` alias avoids shadowing `re` which was imported in Task 1.) Actually `re` is already imported at module top — use it directly:

Replace `_re` with `re` in the regex and helper. Keep the `_COVERAGE_RE` constant name.

- [ ] **Step 3.4: Run tests**

```bash
pytest tests/test_coverage_gate.py -v
```
Expected: all 4 tests in test_coverage_gate.py pass.

- [ ] **Step 3.5: Full suite**

```bash
pytest -v && ruff check .
```
Expected: 62 total (61 + 1), ruff clean.

- [ ] **Step 3.6: Commit**

```bash
git add scripts/measure_python.py tests/test_coverage_gate.py
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "feat(gates): coverage regression check vs. prior iteration

With compare_to_baseline=true, the coverage gate reads the most recent
prior iteration's coverage stdout ('coverage: X.Y%'), and fails if the
current coverage dropped more than 0.5pp below it. Catches silent
regressions where new code lands without tests."
```

---

## Task 4: Diff summary helper — `scripts/diff_summary.py`

Small Python CLI that parses `git diff --numstat` output into a structured JSON. Consumed by the `loop` skill after each iteration's git commit.

**Files:**
- Create: `scripts/diff_summary.py`
- Create: `tests/test_diff_summary.py`

- [ ] **Step 4.1: Write failing tests — `tests/test_diff_summary.py`**

```python
"""Tests for scripts/diff_summary.py — parses `git diff --numstat` output
into a structured changes dict for iteration records.
"""
import json
import subprocess
import sys
from pathlib import Path

from scripts.diff_summary import parse_numstat, summarize_diff

ROOT = Path(__file__).resolve().parents[1]
CLI = [sys.executable, str(ROOT / "scripts" / "diff_summary.py")]


def test_parse_text_files():
    output = "12\t3\tsrc/auth.py\n25\t0\ttests/test_auth.py\n"
    result = parse_numstat(output)
    assert result["files_touched"] == ["src/auth.py", "tests/test_auth.py"]
    assert result["net_lines"] == (12 - 3) + (25 - 0)
    assert "src/auth.py: +12/-3" in result["diff_summary"]
    assert "tests/test_auth.py: +25/-0" in result["diff_summary"]


def test_parse_binary_file():
    output = "-\t-\tbin/image.png\n"
    result = parse_numstat(output)
    assert result["files_touched"] == ["bin/image.png"]
    # Binary files contribute 0 to net_lines
    assert result["net_lines"] == 0
    assert "bin/image.png: (binary)" in result["diff_summary"]


def test_parse_empty_diff():
    result = parse_numstat("")
    assert result == {"files_touched": [], "net_lines": 0, "diff_summary": ""}


def test_summarize_diff_in_real_repo(tmp_path: Path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "a.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "first"], cwd=tmp_path, check=True)
    (tmp_path / "a.py").write_text("x = 1\ny = 2\nz = 3\n")
    (tmp_path / "b.py").write_text("new = True\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "second"], cwd=tmp_path, check=True)

    result = summarize_diff(tmp_path, base="HEAD~1", head="HEAD")
    assert "a.py" in result["files_touched"]
    assert "b.py" in result["files_touched"]
    assert result["net_lines"] == 2 + 1  # a.py: +2, b.py: +1


def test_summarize_diff_on_first_commit(tmp_path: Path):
    """No HEAD~1 — summarize against empty tree so first iteration works."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "a.py").write_text("x = 1\ny = 2\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "first"], cwd=tmp_path, check=True)
    result = summarize_diff(tmp_path)
    assert "a.py" in result["files_touched"]
    assert result["net_lines"] == 2


def test_cli_outputs_json(tmp_path: Path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "a.py").write_text("hello\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "first"], cwd=tmp_path, check=True)
    result = subprocess.run(
        CLI + ["--project", str(tmp_path)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert "files_touched" in data
    assert "net_lines" in data
    assert "diff_summary" in data
```

- [ ] **Step 4.2: Run — confirm failure**

```bash
pytest tests/test_diff_summary.py -v
```
Expected: FAIL — `scripts.diff_summary` doesn't exist.

- [ ] **Step 4.3: Implement `scripts/diff_summary.py`**

```python
#!/usr/bin/env python3
"""Git diff summary helper.

Parses `git diff --numstat` output into a structured dict for inclusion
in iteration records. Used by the loop skill after each per-iteration
git commit.

Contract:
    summarize_diff(project: Path, base: str = "HEAD~1", head: str = "HEAD") -> dict
    parse_numstat(output: str) -> dict

Both return: {"files_touched": [...], "net_lines": int, "diff_summary": str}

On first commit (no HEAD~1), falls back to diffing against the empty tree.
Binary files appear in files_touched but contribute 0 to net_lines.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


# git's empty-tree hash — safe to diff against for the "no previous commit" case
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def parse_numstat(output: str) -> dict:
    files_touched: list[str] = []
    net_lines = 0
    summary_parts: list[str] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        added_raw, deleted_raw, path = parts[0], parts[1], "\t".join(parts[2:])
        files_touched.append(path)
        if added_raw == "-" or deleted_raw == "-":
            summary_parts.append(f"{path}: (binary)")
            continue
        try:
            added = int(added_raw)
            deleted = int(deleted_raw)
        except ValueError:
            continue
        net_lines += added - deleted
        summary_parts.append(f"{path}: +{added}/-{deleted}")
    return {
        "files_touched": files_touched,
        "net_lines": net_lines,
        "diff_summary": ", ".join(summary_parts),
    }


def _has_parent_commit(project: Path) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD~1"],
        cwd=project, capture_output=True, text=True, check=False,
    )
    return result.returncode == 0


def summarize_diff(project: Path, base: str | None = None, head: str = "HEAD") -> dict:
    """Return the parsed diff between base..head in the given project.
    If base is None, defaults to HEAD~1 (or empty tree on first commit)."""
    if base is None:
        base = "HEAD~1" if _has_parent_commit(project) else EMPTY_TREE
    try:
        proc = subprocess.run(
            ["git", "diff", "--numstat", f"{base}..{head}"],
            cwd=project,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return {"files_touched": [], "net_lines": 0, "diff_summary": "git not available"}
    if proc.returncode != 0:
        return {"files_touched": [], "net_lines": 0, "diff_summary": f"git diff failed: {proc.stderr.strip()[:200]}"}
    return parse_numstat(proc.stdout)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Skillgoid git-diff summary helper")
    ap.add_argument("--project", required=True, type=Path)
    ap.add_argument("--base", default=None)
    ap.add_argument("--head", default="HEAD")
    args = ap.parse_args(argv)
    result = summarize_diff(args.project.resolve(), base=args.base, head=args.head)
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4.4: Run tests**

```bash
pytest tests/test_diff_summary.py -v
```
Expected: 6 tests pass.

- [ ] **Step 4.5: Full suite + ruff**

```bash
pytest -v && ruff check .
```
Expected: 68 total (62 + 6), ruff clean.

- [ ] **Step 4.6: Commit**

```bash
git add scripts/diff_summary.py tests/test_diff_summary.py
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "feat(diff): git diff summary helper for iteration records

Parses `git diff --numstat` into {files_touched, net_lines, diff_summary}.
Handles first-commit (diffs against empty tree), binary files (net 0),
and missing-git environments. Consumed by the loop skill after each
iteration's git commit."
```

---

## Task 5: Iteration `changes` field + loop skill update

Adds `changes` to iterations.schema.json and updates loop skill prose to populate it from `diff_summary.py`.

**Files:**
- Modify: `schemas/iterations.schema.json`
- Modify: `skills/loop/SKILL.md`
- Modify: `tests/test_schemas.py`

- [ ] **Step 5.1: Update `schemas/iterations.schema.json`**

In the top-level `properties`, add:
```json
"changes": {
  "type": "object",
  "properties": {
    "files_touched": {"type": "array", "items": {"type": "string"}},
    "net_lines": {"type": "integer"},
    "diff_summary": {"type": "string"}
  }
}
```

Not in `required` — old records without it parse fine.

- [ ] **Step 5.2: Add schema test — append to `tests/test_schemas.py`**

```python
def test_iterations_schema_accepts_changes_field():
    record = {
        "iteration": 1,
        "chunk_id": "x",
        "gate_report": {"passed": True, "results": []},
        "changes": {
            "files_touched": ["a.py"],
            "net_lines": 5,
            "diff_summary": "a.py: +5/-0",
        },
    }
    errors = list(_validator("iterations.schema.json").iter_errors(record))
    assert errors == []


def test_iterations_schema_rejects_non_integer_net_lines():
    record = {
        "iteration": 1,
        "chunk_id": "x",
        "gate_report": {"passed": True, "results": []},
        "changes": {
            "files_touched": ["a.py"],
            "net_lines": "lots",
            "diff_summary": "",
        },
    }
    errors = list(_validator("iterations.schema.json").iter_errors(record))
    assert any(e.validator == "type" for e in errors)
```

- [ ] **Step 5.3: Update `skills/loop/SKILL.md` — add diff step after git commit**

Read the file to find Step 8.1 (git commit step). After that step, insert a new Step 8.2:

```markdown
8.2. **Record diff summary.** Immediately after the git commit lands, capture what changed:
   ```bash
   python <plugin-root>/scripts/diff_summary.py --project <project_path>
   ```
   The output JSON has shape `{files_touched: [...], net_lines: int, diff_summary: str}`. Inject this as the `changes` field when writing `iterations/NNN.json`. If `loop.skip_git == true` or the project isn't a git repo (`diff_summary.py` returns empty), omit the `changes` field.
```

Also update the iteration JSON example in step 8 (Reflect) to include the `changes` field:

```json
{
  "iteration": N,
  "chunk_id": "<id>",
  ...
  "changes": {"files_touched": [...], "net_lines": <int>, "diff_summary": "..."},
  "exit_reason": "in_progress"
}
```

Read the current step-8 example block and edit it to include the new field alongside `failure_signature`.

- [ ] **Step 5.4: Run tests**

```bash
pytest -v && ruff check .
```
Expected: 70 total (68 + 2 schema), ruff clean.

- [ ] **Step 5.5: Commit**

```bash
git add schemas/iterations.schema.json skills/loop/SKILL.md tests/test_schemas.py
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "feat(loop): record diff summary per iteration

After each iteration's git commit, loop skill invokes diff_summary.py
and includes the structured changes dict in iterations/NNN.json.
Schema allows the field but doesn't require it (backward-compat with
v0.2 records and non-git projects)."
```

---

## Task 6: Gate-guard message enhancement

Update `hooks/gate-guard.sh` to surface the top-2 failing gate hints in the Stop-hook block reason. Test via existing `tests/test_gate_guard.py`.

**Files:**
- Modify: `hooks/gate-guard.sh`
- Modify: `tests/test_gate_guard.py`

- [ ] **Step 6.1: Add failing test — append to `tests/test_gate_guard.py`**

```python
def test_gate_guard_block_reason_includes_top_hints(tmp_path: Path):
    """When blocking, the reason string includes the hints from up to 2
    failing gates so the user can make an informed decision."""
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    (sg / "criteria.yaml").write_text("loop:\n  max_attempts: 5\ngates: []\n")
    (sg / "chunks.yaml").write_text("chunks:\n  - id: a\n    description: x\n    gate_ids: [pytest, ruff]\n")
    iters = sg / "iterations"
    iters.mkdir()
    (iters / "001.json").write_text(json.dumps({
        "iteration": 1, "chunk_id": "a",
        "gate_report": {
            "passed": False,
            "results": [
                {"gate_id": "pytest", "passed": False,
                 "stdout": "", "stderr": "",
                 "hint": "2 tests failed in test_auth.py — likely missing session fixture"},
                {"gate_id": "ruff", "passed": False,
                 "stdout": "", "stderr": "",
                 "hint": "F401 unused import `os` in src/auth.py:1"},
            ],
        },
        "exit_reason": "in_progress",
    }))
    out = _run(tmp_path)
    assert out.get("decision") == "block"
    reason = out.get("reason", "")
    # Both top-2 hint strings should appear in the reason
    assert "session fixture" in reason
    assert "F401" in reason or "unused import" in reason
```

- [ ] **Step 6.2: Run — confirm failure**

```bash
pytest tests/test_gate_guard.py::test_gate_guard_block_reason_includes_top_hints -v
```
Expected: FAIL — current gate-guard.sh doesn't surface hints.

- [ ] **Step 6.3: Update `hooks/gate-guard.sh`**

Current script builds a reason string from just gate IDs. Modify the python heredoc inside gate-guard.sh (around the `failing_ids = ...` line) to additionally collect hints and include them.

Find the block in `hooks/gate-guard.sh` that starts with `failing_ids = [...]` inside the python heredoc. Replace that block through the `print(json.dumps(...))` call with:

```python
failing_results = [r for r in report.get("results", []) if not r.get("passed")]
failing_ids = [r.get("gate_id", "?") for r in failing_results]

# Pick top 2 hints by length (most informative)
def _truncate(s: str, n: int = 120) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"

hints_by_length = sorted(
    [(r.get("gate_id", "?"), (r.get("hint") or "")) for r in failing_results],
    key=lambda pair: len(pair[1]),
    reverse=True,
)
top_hints = [(gid, h) for gid, h in hints_by_length[:2] if h]

reason_parts = [
    f"Skillgoid: gates still failing ({', '.join(filter(None, failing_ids)) or 'unknown'}) and "
    f"loop budget remains ({iteration}/{max_attempts})."
]
for gid, hint in top_hints:
    reason_parts.append(f"→ {gid} hint: \"{_truncate(hint)}\"")
reason_parts.append(
    "Continue iterating with `/skillgoid:build resume`, "
    "or break explicitly with `/skillgoid:build retrospect-only`."
)
reason = "\n".join(reason_parts)
print(json.dumps({"decision": "block", "reason": reason}))
```

Verify the existing script still parses after the edit by running `bash -n hooks/gate-guard.sh`.

- [ ] **Step 6.4: Run tests**

```bash
pytest tests/test_gate_guard.py -v
```
Expected: all gate_guard tests pass (previous 4 + new 1 = 5). The existing `test_failing_gates_with_budget_blocks_stop` assertion still matches because the first line of the reason still contains "gates still failing".

- [ ] **Step 6.5: Full suite**

```bash
pytest -v && ruff check .
```
Expected: 71 total, ruff clean.

- [ ] **Step 6.6: Commit**

```bash
git add hooks/gate-guard.sh tests/test_gate_guard.py
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "feat(hooks): surface top-2 failing gate hints in gate-guard block

When Stop fires mid-loop, include the hints from up to 2 failing gates
(sorted by hint length — most informative first) in the block reason
so the user can decide to continue or break without reading iteration
JSON. Hints truncated to 120 chars each."
```

---

## Task 7: Model tiering via `criteria.yaml`

Schema addition + `build` skill prose update so users can override chunk/integration subagent models per-project.

**Files:**
- Modify: `schemas/criteria.schema.json`
- Modify: `skills/build/SKILL.md`
- Modify: `tests/test_schemas.py`

- [ ] **Step 7.1: Add failing schema tests — append to `tests/test_schemas.py`**

```python
def test_criteria_models_block_validates():
    data = {
        "gates": [{"id": "p", "type": "pytest"}],
        "models": {
            "chunk_subagent": "opus",
            "integration_subagent": "haiku",
        },
    }
    errors = list(_validator("criteria.schema.json").iter_errors(data))
    assert errors == []


def test_criteria_models_partial_block_validates():
    data = {
        "gates": [{"id": "p", "type": "pytest"}],
        "models": {"chunk_subagent": "sonnet"},
    }
    errors = list(_validator("criteria.schema.json").iter_errors(data))
    assert errors == []


def test_criteria_models_rejects_unknown_model():
    data = {
        "gates": [{"id": "p", "type": "pytest"}],
        "models": {"chunk_subagent": "gpt-7"},
    }
    errors = list(_validator("criteria.schema.json").iter_errors(data))
    assert any(e.validator == "enum" for e in errors)
```

- [ ] **Step 7.2: Run — confirm failure**

```bash
pytest tests/test_schemas.py -v -k models
```
Expected: 3 tests fail.

- [ ] **Step 7.3: Update `schemas/criteria.schema.json`**

Add to top-level `properties`:

```json
"models": {
  "type": "object",
  "properties": {
    "chunk_subagent": {
      "type": "string",
      "enum": ["haiku", "sonnet", "opus"],
      "default": "sonnet",
      "description": "Model for per-chunk subagents. v0.2 default is sonnet."
    },
    "integration_subagent": {
      "type": "string",
      "enum": ["haiku", "sonnet", "opus"],
      "default": "haiku",
      "description": "Model for the integration-gate subagent. v0.2 default is haiku (pure measurement)."
    }
  },
  "additionalProperties": false
}
```

- [ ] **Step 7.4: Run schema tests**

```bash
pytest tests/test_schemas.py -v -k models
```
Expected: 3 tests pass.

- [ ] **Step 7.5: Update `skills/build/SKILL.md` — read models block**

Find the chunk subagent dispatch (step 3c, the `Agent(...)` call block). Above the Agent call, add:

```markdown
   Before dispatching, read `models.chunk_subagent` from `criteria.yaml` (default `"sonnet"`) and use it as the `model=` arg. Valid values: `"haiku"`, `"sonnet"`, `"opus"`. If the field is absent or any other value, fall back to `"sonnet"` and log a stderr warning.
```

Update the Agent call block to show:

```
      Agent(
        subagent_type="general-purpose",
        model=<criteria.models.chunk_subagent or "sonnet">,
        description="Execute Skillgoid chunk <chunk_id>",
        prompt=<curated prompt — see template below>,
      )
```

Do the same in step 4d (integration subagent) with `models.integration_subagent` defaulting to `"haiku"`.

- [ ] **Step 7.6: Full suite + ruff**

```bash
pytest -v && ruff check .
```
Expected: 74 total (71 + 3), ruff clean.

- [ ] **Step 7.7: Commit**

```bash
git add schemas/criteria.schema.json skills/build/SKILL.md tests/test_schemas.py
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "feat(build): per-project subagent model selection via criteria.yaml

New optional models block lets projects override chunk_subagent
(default sonnet) and integration_subagent (default haiku) per-project.
Schema enforces enum ['haiku', 'sonnet', 'opus']. Missing field falls
back to v0.2 defaults."
```

---

## Task 8: Metrics append helper — `scripts/metrics_append.py`

New helper invoked by `retrospect` to append one cross-project stats line to `~/.claude/skillgoid/metrics.jsonl`.

**Files:**
- Create: `scripts/metrics_append.py`
- Create: `tests/test_metrics_append.py`

- [ ] **Step 8.1: Write failing tests — `tests/test_metrics_append.py`**

```python
"""Tests for scripts/metrics_append.py — appends cross-project run stats to
~/.claude/skillgoid/metrics.jsonl on retrospect.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.metrics_append import build_metrics_line, append_metrics

ROOT = Path(__file__).resolve().parents[1]
CLI = [sys.executable, str(ROOT / "scripts" / "metrics_append.py")]


def _write_iter(sg: Path, n: int, chunk_id: str, exit_reason: str,
                started: str = "2026-04-17T12:00:00Z",
                ended: str = "2026-04-17T12:05:00Z") -> None:
    iters = sg / "iterations"
    iters.mkdir(exist_ok=True)
    (iters / f"{n:03d}.json").write_text(json.dumps({
        "iteration": n,
        "chunk_id": chunk_id,
        "started_at": started,
        "ended_at": ended,
        "gate_report": {"passed": exit_reason == "success", "results": []},
        "exit_reason": exit_reason,
    }))


def _write_integ(sg: Path, attempt: int, passed: bool) -> None:
    integ = sg / "integration"
    integ.mkdir(exist_ok=True)
    (integ / f"{attempt:03d}.json").write_text(json.dumps({
        "iteration": attempt,
        "chunk_id": "__integration__",
        "gate_report": {"passed": passed, "results": []},
    }))


def test_build_metrics_line_from_iterations(tmp_path: Path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    (sg / "goal.md").write_text("# Goal\n\nBuild a CLI.\n")
    (sg / "criteria.yaml").write_text("language: python\ngates: []\n")
    (sg / "chunks.yaml").write_text(
        "chunks:\n"
        "  - id: scaffold\n    description: scaffold\n    gate_ids: [ruff]\n"
        "  - id: core\n    description: core\n    gate_ids: [pytest]\n"
    )
    _write_iter(sg, 1, "scaffold", "success")
    _write_iter(sg, 2, "core", "success",
                started="2026-04-17T12:05:00Z", ended="2026-04-17T12:30:00Z")
    line = build_metrics_line(sg, project_slug="demo")
    assert line["slug"] == "demo"
    assert line["language"] == "python"
    assert line["outcome"] == "success"
    assert line["chunks"] == 2
    assert line["total_iterations"] == 2
    assert line["stall_count"] == 0
    assert line["budget_exhausted_count"] == 0
    assert line["integration_retries_used"] == 0
    assert line["elapsed_seconds"] == 30 * 60


def test_build_metrics_line_counts_stalls_and_budget_exhaustion(tmp_path: Path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    (sg / "criteria.yaml").write_text("language: python\ngates: []\n")
    (sg / "chunks.yaml").write_text("chunks:\n  - id: a\n    description: x\n    gate_ids: [pytest]\n")
    _write_iter(sg, 1, "a", "stalled")
    _write_iter(sg, 2, "a", "budget_exhausted")
    line = build_metrics_line(sg, project_slug="rough")
    assert line["outcome"] == "partial"
    assert line["stall_count"] == 1
    assert line["budget_exhausted_count"] == 1


def test_build_metrics_line_counts_integration_retries(tmp_path: Path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    (sg / "criteria.yaml").write_text("language: python\ngates: []\n")
    (sg / "chunks.yaml").write_text("chunks:\n  - id: a\n    description: x\n    gate_ids: [pytest]\n")
    _write_iter(sg, 1, "a", "success")
    _write_integ(sg, 1, passed=False)
    _write_integ(sg, 2, passed=False)
    _write_integ(sg, 3, passed=True)
    line = build_metrics_line(sg, project_slug="integ")
    assert line["integration_retries_used"] == 2  # 3 attempts = 2 retries after the initial


def test_append_metrics_writes_to_jsonl(tmp_path: Path, monkeypatch):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    (sg / "criteria.yaml").write_text("language: python\ngates: []\n")
    (sg / "chunks.yaml").write_text("chunks:\n  - id: a\n    description: x\n    gate_ids: [pytest]\n")
    _write_iter(sg, 1, "a", "success")

    home = tmp_path / "fake-home"
    monkeypatch.setenv("HOME", str(home))
    result = append_metrics(sg, project_slug="demo")
    assert result is True

    metrics_path = home / ".claude" / "skillgoid" / "metrics.jsonl"
    assert metrics_path.exists()
    lines = metrics_path.read_text().strip().split("\n")
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["slug"] == "demo"
    assert parsed["outcome"] == "success"


def test_cli_works(tmp_path: Path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    (sg / "criteria.yaml").write_text("language: python\ngates: []\n")
    (sg / "chunks.yaml").write_text("chunks:\n  - id: a\n    description: x\n    gate_ids: [pytest]\n")
    _write_iter(sg, 1, "a", "success")

    home = tmp_path / "fake-home"
    env = {**os.environ, "HOME": str(home)}
    result = subprocess.run(
        CLI + ["--skillgoid-dir", str(sg), "--slug", "cli-demo"],
        env=env, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    metrics_path = home / ".claude" / "skillgoid" / "metrics.jsonl"
    assert metrics_path.exists()
```

- [ ] **Step 8.2: Run — confirm failure**

```bash
pytest tests/test_metrics_append.py -v
```
Expected: all 5 FAIL — `scripts.metrics_append` doesn't exist.

- [ ] **Step 8.3: Implement `scripts/metrics_append.py`**

```python
#!/usr/bin/env python3
"""Metrics append helper.

Invoked by the `retrospect` skill after writing a project's
retrospective.md. Appends one JSON line to
~/.claude/skillgoid/metrics.jsonl summarizing the project run.

Contract:
    build_metrics_line(sg: Path, project_slug: str) -> dict
    append_metrics(sg: Path, project_slug: str) -> bool

CLI:
    python scripts/metrics_append.py --skillgoid-dir <path> --slug <slug>

No data leaves the user's machine. No external transmission.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from pathlib import Path

import yaml


def _load_iterations(sg: Path) -> list[dict]:
    iters_dir = sg / "iterations"
    if not iters_dir.is_dir():
        return []
    records: list[dict] = []
    for path in sorted(iters_dir.glob("*.json")):
        try:
            records.append(json.loads(path.read_text()))
        except Exception:
            continue
    return records


def _load_integration(sg: Path) -> list[dict]:
    integ_dir = sg / "integration"
    if not integ_dir.is_dir():
        return []
    records: list[dict] = []
    for path in sorted(integ_dir.glob("*.json")):
        try:
            records.append(json.loads(path.read_text()))
        except Exception:
            continue
    return records


def _count_chunks(sg: Path) -> int:
    chunks_file = sg / "chunks.yaml"
    if not chunks_file.exists():
        return 0
    try:
        data = yaml.safe_load(chunks_file.read_text()) or {}
        chunks = data.get("chunks") or []
        return len(chunks) if isinstance(chunks, list) else 0
    except Exception:
        return 0


def _language(sg: Path) -> str | None:
    crit_file = sg / "criteria.yaml"
    if not crit_file.exists():
        return None
    try:
        data = yaml.safe_load(crit_file.read_text()) or {}
        return data.get("language")
    except Exception:
        return None


def _parse_ts(ts: str | None) -> _dt.datetime | None:
    if not ts:
        return None
    try:
        # Support both Z and +00:00 suffixes
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return _dt.datetime.fromisoformat(ts)
    except Exception:
        return None


def _elapsed_seconds(iters: list[dict]) -> int | None:
    starts = [_parse_ts(r.get("started_at")) for r in iters]
    ends = [_parse_ts(r.get("ended_at")) for r in iters]
    starts = [s for s in starts if s]
    ends = [e for e in ends if e]
    if not starts or not ends:
        return None
    return int((max(ends) - min(starts)).total_seconds())


def _outcome(iters: list[dict]) -> str:
    if not iters:
        return "abandoned"
    # Latest per chunk
    latest_per_chunk: dict[str, dict] = {}
    for r in iters:
        cid = r.get("chunk_id", "?")
        if cid == "?":
            continue
        n = r.get("iteration", 0)
        if cid not in latest_per_chunk or n > latest_per_chunk[cid].get("iteration", 0):
            latest_per_chunk[cid] = r
    exit_reasons = {r.get("exit_reason", "in_progress") for r in latest_per_chunk.values()}
    if exit_reasons == {"success"}:
        return "success"
    if "stalled" in exit_reasons or "budget_exhausted" in exit_reasons:
        return "partial"
    return "partial"


def build_metrics_line(sg: Path, project_slug: str) -> dict:
    iters = _load_iterations(sg)
    integ = _load_integration(sg)
    stall_count = sum(1 for r in iters if r.get("exit_reason") == "stalled")
    budget_count = sum(1 for r in iters if r.get("exit_reason") == "budget_exhausted")
    # integration_retries_used = attempts beyond the first
    integration_retries = max(len(integ) - 1, 0)
    return {
        "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "slug": project_slug,
        "language": _language(sg),
        "outcome": _outcome(iters),
        "chunks": _count_chunks(sg),
        "total_iterations": len(iters),
        "stall_count": stall_count,
        "budget_exhausted_count": budget_count,
        "integration_retries_used": integration_retries,
        "elapsed_seconds": _elapsed_seconds(iters),
    }


def _metrics_file() -> Path:
    home = Path(os.environ.get("HOME") or Path.home())
    return home / ".claude" / "skillgoid" / "metrics.jsonl"


def append_metrics(sg: Path, project_slug: str) -> bool:
    line = build_metrics_line(sg, project_slug)
    path = _metrics_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")
    except Exception as exc:
        sys.stderr.write(f"metrics_append: {exc}\n")
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Skillgoid metrics append helper")
    ap.add_argument("--skillgoid-dir", required=True, type=Path)
    ap.add_argument("--slug", required=True)
    args = ap.parse_args(argv)
    append_metrics(args.skillgoid_dir.resolve(), args.slug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 8.4: Run tests**

```bash
pytest tests/test_metrics_append.py -v
```
Expected: 5 tests pass.

- [ ] **Step 8.5: Full suite + ruff**

```bash
pytest -v && ruff check .
```
Expected: 79 total (74 + 5), ruff clean.

- [ ] **Step 8.6: Commit**

```bash
git add scripts/metrics_append.py tests/test_metrics_append.py
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "feat(metrics): append per-project stats to metrics.jsonl

scripts/metrics_append.py gathers chunks, iterations, stalls,
budget exhaustion, integration retries, and elapsed time from a
project's .skillgoid/ directory and appends one JSON line to
~/.claude/skillgoid/metrics.jsonl. Invoked by retrospect skill.
Private to the user's machine — no external transmission."
```

---

## Task 9: Retrospect + Clarify skill updates

**Files:**
- Modify: `skills/retrospect/SKILL.md`
- Modify: `skills/clarify/SKILL.md`
- Modify: `skills/python-gates/SKILL.md` (tiny note about timeout)

- [ ] **Step 9.1: Update `skills/retrospect/SKILL.md`**

In the Procedure section, after "Step B — curate the vault" (step 10 of the existing flow, the optional `.log` entry), add a new step:

```markdown
Step C — append metrics
11. Append a cross-project metrics line by running:
   ```bash
   python <plugin-root>/scripts/metrics_append.py --skillgoid-dir .skillgoid --slug <project-slug>
   ```
   The `<project-slug>` is a short kebab-case identifier derived from the project directory name or `goal.md` title. The helper appends one JSON line to `~/.claude/skillgoid/metrics.jsonl` capturing chunks, iterations, stalls, budget exhaustion, integration retries, and elapsed time.

   This data accumulates across projects for future cross-project analytics. It never leaves your machine.
```

- [ ] **Step 9.2: Update `skills/clarify/SKILL.md`**

In step 5.1 (default integration gate per project type), after the CLI/library/service/unknown bullets, add a new section for the coverage gate:

```markdown
5.2. **Default coverage gate for Python projects with pytest.** When the project is Python and `gates` includes a `pytest` gate, propose adding a `coverage` gate to `gates` as well:
   ```yaml
   - id: cov
     type: coverage
     target: "<package-name>"   # e.g., mypkg; default "." if unclear
     min_percent: 80
     compare_to_baseline: false  # opt in later if desired
   ```
   Omit for non-Python projects or when the user explicitly opts out. `compare_to_baseline: false` by default — users who want regression detection flip it to `true` once a solid baseline exists.
```

- [ ] **Step 9.3: Update `skills/python-gates/SKILL.md` — tiny note about timeout**

Find the Procedure section. After the CLI invocation block, add:

```markdown
**Note:** gate entries may carry a `timeout` field (integer seconds, default 300). The adapter honors it — a gate that runs past its timeout fails cleanly with a hint, rather than hanging the loop.
```

- [ ] **Step 9.4: Verify all skill files parse**

```bash
for f in skills/*/SKILL.md; do
  python -c "import yaml; lines=open('$f').read().split('---', 2); assert yaml.safe_load(lines[1])"
done
echo "all skill frontmatters OK"
```

- [ ] **Step 9.5: Full suite + ruff**

```bash
pytest -v && ruff check .
```
Expected: 79 total (no code changes, just skill prose), ruff clean.

- [ ] **Step 9.6: Commit**

```bash
git add skills/retrospect/SKILL.md skills/clarify/SKILL.md skills/python-gates/SKILL.md
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "feat(skills): wire v0.3 additions into skill prose

- retrospect: invoke metrics_append.py after writing retrospective.
- clarify: propose default coverage gate (min_percent 80, no baseline)
  for Python projects that already have a pytest gate.
- python-gates: document that timeout is honored per-gate."
```

---

## Task 10: Docs — README, CHANGELOG, roadmap

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/roadmap.md`

- [ ] **Step 10.1: Add "What's new in v0.3" to `README.md`**

Before the existing `## What's new in v0.2` section (so v0.3 is the first "what's new" a reader sees), insert:

```markdown
## What's new in v0.3

Six additive polish items, zero architectural change:

- **Adapter timeouts.** Every gate accepts an optional `timeout: <seconds>` (default 300). Runaway tests or hung CLIs fail fast with a clear hint.
- **Coverage gate.** New gate type `coverage` — honors `min_percent` and optional `compare_to_baseline` regression detection. Catches the "tests pass because the feature doesn't exist yet" trap.
- **Diff-based reflection.** Each iteration record now includes a `changes` field (files touched, net lines, summary) derived from the per-iteration git diff. Sharpens stall analysis and retrospect.
- **Better `gate-guard` messages.** When the Stop hook blocks mid-loop, it now surfaces the top-2 failing gate hints so you can decide whether to continue without reading iteration JSON.
- **Model tiering.** Optional `models:` block in `criteria.yaml` lets you override chunk/integration subagent models per-project (`haiku`/`sonnet`/`opus`).
- **Cross-project metrics scaffolding.** Retrospect now appends one JSON line per project to `~/.claude/skillgoid/metrics.jsonl`. Data accumulates locally; readers/dashboards come later.

All changes are fully backward-compatible with v0.2.

```

- [ ] **Step 10.2: Add `[0.3.0]` entry to `CHANGELOG.md`**

At the top of the changelog (right after the header, before `## [0.2.0]`), insert:

```markdown
## [0.3.0] — 2026-04-17

### Added
- `scripts/diff_summary.py` — parses `git diff --numstat` into `{files_touched, net_lines, diff_summary}`.
- `scripts/metrics_append.py` — appends per-project stats to `~/.claude/skillgoid/metrics.jsonl` (local only, never transmitted).
- `coverage` gate type in `measure_python.py` — supports `min_percent` (default 80) and `compare_to_baseline` regression detection.
- Optional `timeout` field on every gate (default 300s). Converts `TimeoutExpired` to a failing GateResult with a clear hint.
- Optional `models:` block in `criteria.yaml` — override chunk/integration subagent model per-project.
- `changes` field on every iteration record (from `diff_summary.py`).

### Changed
- `hooks/gate-guard.sh` block reason now includes top-2 failing gate hints.
- `loop` skill procedure writes the `changes` field to each iteration record after the git-commit step.
- `build` skill reads `criteria.yaml → models` for Agent tool dispatch (falls back to v0.2 defaults).
- `clarify` skill proposes a default `coverage` gate for Python projects with `pytest`.
- `retrospect` skill appends a line to `~/.claude/skillgoid/metrics.jsonl` after writing the retrospective.
- `python-gates` skill documentation notes the timeout field is honored.

### Backward compatibility
- v0.2 `criteria.yaml` / iteration records parse unchanged.
- Missing `timeout` → default 300s.
- Missing `models` → v0.2 defaults (sonnet for chunk, haiku for integration).
- Missing `coverage` gate → no behavior change.
- Non-git projects skip the `changes` field entirely.

```

Keep the existing `## [0.2.0]` and `## [0.1.0]` entries intact below.

- [ ] **Step 10.3: Update `docs/roadmap.md`**

Replace the "In flight" section and update the "Deferred — v0.3 goals" section:

Find:
```markdown
## In flight

### v0.2 — Production Hardening Bundle
```

Replace the "In flight" header+body (the v0.2 section) and the "Deferred — v0.3 goals" section with:

```markdown
## Shipped

### v0 (2026-04-17)
The concept: criteria-gated build loop + compounding per-language vault.
Spec: `docs/superpowers/specs/2026-04-17-skillgoid-design.md`
Plan: `docs/superpowers/plans/2026-04-17-skillgoid-v0.md`

### v0.2 — Production Hardening Bundle (2026-04-17)
Three structural upgrades so the criteria-gated loop survives multi-chunk projects:
- Subagent-per-chunk isolation
- Deterministic stall detection + git-per-iteration
- Integration gate after all chunks
Spec: `docs/superpowers/specs/2026-04-17-skillgoid-v0.2-production-hardening.md`
Plan: `docs/superpowers/plans/2026-04-17-skillgoid-v0.2.md`

### v0.3 — Polish & Observe (2026-04-17)
Six additive polish items, zero architectural change:
- Adapter timeouts per gate (default 300s)
- Coverage gate type (min_percent + compare_to_baseline)
- Diff-based reflection (`changes` field per iteration)
- Better `gate-guard` messages (surface top-2 failing gate hints)
- Model tiering via `criteria.yaml → models`
- Cross-project metrics jsonl scaffolding
Spec: `docs/superpowers/specs/2026-04-17-skillgoid-v0.3-polish-observe.md`
Plan: `docs/superpowers/plans/2026-04-17-skillgoid-v0.3.md`

## Deferred — v0.4 goals

After v0.2 and v0.3 have been used on at least one real project, re-rank these by observed ROI.

### Adaptive / judgment upgrades (highest expected value)

- **Plan refinement mid-build.** After chunk N passes, if its iterations surfaced evidence that downstream chunks are miscalibrated, `build` re-invokes `plan` with the new evidence. Currently v0.2/v0.3 surface to user.
- **Pre-plan feasibility gate.** After `clarify`, a quick adversarial pass before committing to the plan.
- **Unstick skill.** `/skillgoid:unstick <chunk> "<hint>"` re-dispatches a stalled chunk with the hint injected.
- **Rehearsal mode.** Dry-run each chunk's first iteration before committing chunks.yaml.

### Scale / throughput upgrades

- **Parallel chunks** (now safer with v0.2's integration gate catching interference).
- **Polyglot / multi-language projects** — per-chunk adapter + vault across languages.

### Observability readers (v0.3's scaffolding becomes useful)

- `/skillgoid:stats` — reads `~/.claude/skillgoid/metrics.jsonl` and summarizes.
- Optional markdown/HTML dashboards.

### Quality / safety upgrades

- **Tighter vault retrieval.** Instead of reading the whole `<language>-lessons.md`, extract only the 3–5 sections most relevant to `rough_goal`.

### Ecosystem upgrades

- **More language adapters** (`node-gates`, `go-gates`, `rust-gates`).
- **Gate type plugins** — third-party-contributable gate types without editing `measure_python.py`.

## How to pick up v0.4

After v0.3 has been used on at least one real project:
1. Read `~/.claude/skillgoid/metrics.jsonl` — which failure modes actually happened?
2. Read that project's `retrospective.md` and vault additions — which v0.4 items would have helped most?
3. Re-rank by observed ROI, not predicted ROI.
4. Spec the top 2–3 items using the same brainstorming → spec → plan → subagent-driven-development flow.
```

- [ ] **Step 10.4: Full suite + ruff**

```bash
pytest -v && ruff check .
```
Expected: 79 total, ruff clean.

- [ ] **Step 10.5: Commit**

```bash
git add README.md CHANGELOG.md docs/roadmap.md
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "docs: v0.3 release notes + roadmap refresh

README gains 'What's new in v0.3' summary. CHANGELOG adds [0.3.0]
entry. Roadmap moves v0.2 and v0.3 into 'Shipped', refines v0.4 list
with emphasis on adaptive/judgment upgrades as the highest expected
value, adds '/skillgoid:stats' now that metrics.jsonl scaffolding
exists to consume."
```

---

## Self-review

**1. Spec coverage.** Every spec §3 component has a task:
- §3.1 Diff-based reflection → Task 4 (helper) + Task 5 (schema + loop prose).
- §3.2 Adapter timeouts → Task 1.
- §3.3 Better gate-guard messages → Task 6.
- §3.4 Model tiering → Task 7.
- §3.5 Coverage gate → Tasks 2 + 3.
- §3.6 Telemetry jsonl → Task 8 (helper) + Task 9 (retrospect prose).
- §6 Skill changes (clarify coverage default, retrospect metrics call, python-gates timeout note) → Task 9.
- §7 Hook changes (gate-guard) → Task 6.
- §8 Testing strategy → covered across Tasks 1, 2, 3, 4, 5, 6, 7, 8, 9. Expected count ~76–79 (spec predicted 64; plan adds more for diff parsing edge cases and metrics stats). Higher is fine.
- §10 Backward-compat → maintained throughout; confirmed in Task 10 CHANGELOG.

**2. Placeholder scan.** Every task step contains actual code or exact commands. `<project-slug>` in Task 9's retrospect prose is the one remaining placeholder — it's resolved at runtime by the retrospect skill from the project directory name or goal title. Acceptable; skills are prose and this is a templated field.

**3. Type/name consistency.**
- `signature(record: dict) -> str` (v0.2's `stall_check.py`) — unchanged here.
- `commit_iteration(project: Path, record: dict) -> bool` (v0.2's `git_iter_commit.py`) — unchanged here.
- `parse_numstat(output: str) -> dict` and `summarize_diff(project: Path, base=None, head="HEAD") -> dict` (Task 4) — used by Task 5 loop skill prose (via CLI only, not import).
- `build_metrics_line(sg: Path, project_slug: str) -> dict` and `append_metrics(sg: Path, project_slug: str) -> bool` (Task 8) — consumed by Task 9 retrospect via CLI.
- Gate types: `run-command`, `pytest`, `ruff`, `mypy`, `import-clean`, `cli-command-runs`, `coverage` — enum in schema (Task 2), dispatch table in measure_python.py (Task 2). Consistent.
- Models enum: `haiku`, `sonnet`, `opus` — Task 7 schema, Task 7 build skill prose. Consistent.
- `changes` field shape: `{files_touched: str[], net_lines: int, diff_summary: str}` — Task 4 output, Task 5 schema, Task 5 loop prose. Consistent.

No gaps found.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-17-skillgoid-v0.3.md`. Two execution options:

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints.

Which approach?
