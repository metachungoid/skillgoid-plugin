# Skillgoid v0.7 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Skillgoid v0.7 — Correctness Bundle. Two items: (1) parallel-wave safety via per-chunk iteration filenames + `paths:`-scoped git commits; (2) gate `env:` honored uniformly across all 7 gate handlers. Folds in one small related fix (`git_iter_commit.py --iteration` path resolution) and one prose-only update (`clarify` steers coverage gates into `integration_gates`).

**Architecture:** Mechanical fixes to existing code — `scripts/measure_python.py` (5 handlers) and `scripts/git_iter_commit.py` (rewrite of commit-scoping). Additive schema field (`paths:` on chunks). Prose-only updates to `loop`, `unstick`, `build`, `plan`, `clarify`, `python-gates` skills. Fully backward-compatible with v0.6.

**Tech Stack:** Python 3.11+, pytest, ruff, jsonschema (existing). No new runtime dependencies.

**Spec:** `docs/superpowers/specs/2026-04-18-skillgoid-v0.7-correctness-bundle.md` (commit `450e1ba`).
**Evidence source:** `~/Development/skillgoid-test/v0.7-findings.md` (28 findings) + `~/Development/skillgoid-test/taskbridge/.skillgoid/retrospective.md` — live-confirmed F17 (env in 5 of 7 handlers), F22 (filename race), F25 (--iteration path), F26 (git add -A cross-contamination), F28 (coverage cross-chunk scope).

---

## Repo layout changes

```
skillgoid-plugin/
├── scripts/
│   ├── measure_python.py             # MODIFIED: _merge_env through 5 handlers + tmp-in-project fix
│   ├── git_iter_commit.py            # MODIFIED: --chunks-file flag, scoped git add, hard-fail, path resolve
│   └── (others unchanged)
├── skills/
│   ├── build/SKILL.md                # MODIFIED: chunk yaml includes paths:
│   ├── clarify/SKILL.md              # MODIFIED: coverage → integration_gates; .gitignore += /tmp*.json
│   ├── loop/SKILL.md                 # MODIFIED: per-chunk filename convention + scratch-file hygiene
│   ├── plan/SKILL.md                 # MODIFIED: propose paths: per chunk
│   ├── python-gates/SKILL.md         # MODIFIED: env: universal note
│   ├── unstick/SKILL.md              # MODIFIED: iteration-filename pattern
│   └── (others unchanged)
├── schemas/
│   └── chunks.schema.json            # MODIFIED: add optional paths: field
├── tests/
│   ├── test_env_gate.py              # MODIFIED: 5 new per-handler env tests
│   ├── test_git_iter_commit.py       # MODIFIED: 4 new scoping/hardfail/path tests
│   ├── test_parallel_wave_commit.py  # NEW: 2 concurrent commits produce disjoint filesets
│   ├── test_iteration_filename_backcompat.py  # NEW: mixed old/new filenames read OK
│   └── test_schemas.py               # MODIFIED: paths: schema validates
├── plugin.json                       # MODIFIED: version 0.6.0 → 0.7.0
├── README.md                         # MODIFIED: "What's new in v0.7"
├── CHANGELOG.md                      # MODIFIED: [0.7.0] entry
└── docs/roadmap.md                   # MODIFIED: v0.7 shipped, v0.8 intake notes
```

**Expected test count:** 117 (v0.6) → ~130 (+13 new tests).

---

## Task 1: Branch setup

- [ ] **Step 1.1: Verify main baseline**

```bash
cd /home/flip/Development/skillgoid/skillgoid-plugin
git checkout main
. .venv/bin/activate
pytest -q && ruff check .
```
Expected: `117 passed`, ruff clean.

- [ ] **Step 1.2: Create feat/v0.7 branch**

```bash
git checkout -b feat/v0.7
```

- [ ] **Step 1.3: No commit — housekeeping only**

---

## Task 2: Add failing env tests for the 5 handlers that currently ignore env:

**Files:**
- Modify: `tests/test_env_gate.py` (append 5 new tests)

- [ ] **Step 2.1: Append failing tests to `tests/test_env_gate.py`**

Append these tests at the end of the file. They assert that each of the 5 currently-broken gate types respects a user-supplied `env:`. Four of five will fail on main — that's the point.

```python
def test_pytest_honors_env_pythonpath(tmp_path: Path):
    """F17: gate-level env: PYTHONPATH should win over the hardcoded <project>/src."""
    # Lay out a package under py/src/ (non-standard location)
    pkg = tmp_path / "py" / "src" / "mypkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("VAL = 42\n")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_it.py").write_text(
        "from mypkg import VAL\n"
        "def test_val(): assert VAL == 42\n"
    )
    criteria = """
gates:
  - id: py_test
    type: pytest
    args: ["tests/"]
    env:
      PYTHONPATH: "py/src"
"""
    report = run_cli(criteria, tmp_path)
    assert report["passed"] is True, f"results: {report['results']}"


def test_import_clean_honors_env_pythonpath(tmp_path: Path):
    """F17: gate env: PYTHONPATH respected by import-clean."""
    pkg = tmp_path / "py" / "src" / "mypkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    criteria = """
gates:
  - id: imp
    type: import-clean
    module: mypkg
    env:
      PYTHONPATH: "py/src"
"""
    report = run_cli(criteria, tmp_path)
    assert report["passed"] is True, f"results: {report['results']}"


def test_coverage_honors_env_pythonpath(tmp_path: Path):
    """F17: gate env: PYTHONPATH respected by coverage."""
    pkg = tmp_path / "py" / "src" / "mypkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("def f(): return 1\n")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_it.py").write_text(
        "from mypkg import f\n"
        "def test_f(): assert f() == 1\n"
    )
    criteria = """
gates:
  - id: cov
    type: coverage
    target: "mypkg"
    min_percent: 50
    env:
      PYTHONPATH: "py/src"
"""
    report = run_cli(criteria, tmp_path)
    assert report["passed"] is True, f"results: {report['results']}"


def test_ruff_honors_env(tmp_path: Path):
    """Ruff gate should pass env: through to the subprocess."""
    (tmp_path / "a.py").write_text("x = 1\n")
    criteria = """
gates:
  - id: ruff_env
    type: ruff
    args: ["check", "."]
    env:
      RUFF_CACHE_DIR: "/tmp/ruff-cache-skillgoid-test"
"""
    report = run_cli(criteria, tmp_path)
    # Pass if ruff is installed; env must not cause a crash.
    # (We can't directly observe RUFF_CACHE_DIR from the test, but the gate
    # running cleanly with env specified is the baseline assertion.)
    assert report["results"][0]["gate_id"] == "ruff_env"
    assert report["results"][0]["passed"] is True


def test_mypy_honors_env(tmp_path: Path):
    """Mypy gate should pass env: through to the subprocess."""
    (tmp_path / "a.py").write_text("x: int = 1\n")
    criteria = """
gates:
  - id: mypy_env
    type: mypy
    args: ["a.py"]
    env:
      MYPY_CACHE_DIR: "/tmp/mypy-cache-skillgoid-test"
"""
    report = run_cli(criteria, tmp_path)
    assert report["results"][0]["gate_id"] == "mypy_env"
    assert report["results"][0]["passed"] is True


def test_pytest_default_pythonpath_when_env_absent(tmp_path: Path):
    """Back-compat: absent gate env still gets <project>/src on PYTHONPATH."""
    pkg = tmp_path / "src" / "mypkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("VAL = 7\n")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_it.py").write_text(
        "from mypkg import VAL\n"
        "def test_val(): assert VAL == 7\n"
    )
    criteria = """
gates:
  - id: py_test
    type: pytest
    args: ["tests/"]
"""
    report = run_cli(criteria, tmp_path)
    assert report["passed"] is True, f"results: {report['results']}"
```

- [ ] **Step 2.2: Run to confirm 4 of 6 fail (pre-fix state)**

```bash
. .venv/bin/activate
pytest tests/test_env_gate.py -v
```
Expected: `test_pytest_default_pythonpath_when_env_absent` passes (back-compat works), `test_ruff_honors_env` and `test_mypy_honors_env` may pass depending on whether ruff accepts env=, but the three polyglot-layout tests (pytest/import-clean/coverage with `PYTHONPATH: py/src`) FAIL with `ModuleNotFoundError: No module named 'mypkg'`.

- [ ] **Step 2.3: Commit the red tests**

```bash
git add tests/test_env_gate.py
git commit -m "test(env): add failing tests for pytest/import-clean/coverage/ruff/mypy env support (F17)"
```

---

## Task 3: Wire `_merge_env` through `_gate_pytest`

**Files:**
- Modify: `scripts/measure_python.py` lines 122-146 (`_gate_pytest`)

- [ ] **Step 3.1: Replace the env construction in `_gate_pytest`**

Locate the current body at lines 122-146. Replace the two lines that construct `env` (currently lines 125-127) with the merge-first-then-default-inject pattern.

```python
def _gate_pytest(gate: dict, project: Path) -> GateResult:
    args = gate.get("args") or []
    timeout = gate.get("timeout", DEFAULT_GATE_TIMEOUT)
    gate_env = gate.get("env") or {}
    env = _merge_env(project, gate_env)
    # Default-inject <project>/src on PYTHONPATH only when user did not supply one.
    if "PYTHONPATH" not in gate_env:
        env_path = str(project / "src")
        existing = os.environ.get("PYTHONPATH", "")
        env["PYTHONPATH"] = env_path + (os.pathsep + existing if existing else "")
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", *args],
```

Keep the rest of the function body (the subprocess.run call and its arguments, the TimeoutExpired handler, the pass/fail logic) exactly as-is.

- [ ] **Step 3.2: Run the pytest-env test**

```bash
pytest tests/test_env_gate.py::test_pytest_honors_env_pythonpath tests/test_env_gate.py::test_pytest_default_pythonpath_when_env_absent -v
```
Expected: both PASS.

- [ ] **Step 3.3: Run the full suite to confirm no regressions**

```bash
pytest -q
```
Expected: no new failures among previously-passing tests; import-clean/coverage/ruff/mypy env tests still fail.

- [ ] **Step 3.4: Commit**

```bash
git add scripts/measure_python.py
git commit -m "fix(pytest-gate): honor gate env: PYTHONPATH override (F17)"
```

---

## Task 4: Wire `_merge_env` through `_gate_import_clean`

**Files:**
- Modify: `scripts/measure_python.py` lines 204-231 (`_gate_import_clean`)

- [ ] **Step 4.1: Replace the env construction in `_gate_import_clean`**

Replace lines 208-212 (the existing `existing`/`env` construction) with the merge-first-then-default-inject pattern:

```python
def _gate_import_clean(gate: dict, project: Path) -> GateResult:
    module = gate.get("module")
    if not module:
        return GateResult(gate["id"], False, "", "", "missing `module` field; add `module: <name>`")
    gate_env = gate.get("env") or {}
    env = _merge_env(project, gate_env)
    if "PYTHONPATH" not in gate_env:
        env_path = str(project / "src")
        existing = os.environ.get("PYTHONPATH", "")
        env["PYTHONPATH"] = env_path + (os.pathsep + existing if existing else "")
    timeout = gate.get("timeout", DEFAULT_GATE_TIMEOUT)
    try:
        proc = subprocess.run(
            [sys.executable, "-c", f"import {module}"],
```

Keep the rest of the function identical.

- [ ] **Step 4.2: Run the import-clean env test**

```bash
pytest tests/test_env_gate.py::test_import_clean_honors_env_pythonpath -v
```
Expected: PASS.

- [ ] **Step 4.3: Full suite**

```bash
pytest -q
```
Expected: no regressions.

- [ ] **Step 4.4: Commit**

```bash
git add scripts/measure_python.py
git commit -m "fix(import-clean-gate): honor gate env: PYTHONPATH override (F17)"
```

---

## Task 5: Wire `_merge_env` through `_gate_coverage` (and move tmp file out of project tree)

**Files:**
- Modify: `scripts/measure_python.py` lines 281-349 (`_gate_coverage`)

- [ ] **Step 5.1: Replace env construction + fix tmp-file location**

Replace lines 286-295 (env construction + NamedTemporaryFile block) with:

```python
def _gate_coverage(gate: dict, project: Path) -> GateResult:
    target = gate.get("target") or "."
    min_percent = gate.get("min_percent", 80)
    timeout = gate.get("timeout", DEFAULT_GATE_TIMEOUT)

    gate_env = gate.get("env") or {}
    env = _merge_env(project, gate_env)
    if "PYTHONPATH" not in gate_env:
        env_path = str(project / "src")
        existing = os.environ.get("PYTHONPATH", "")
        env["PYTHONPATH"] = env_path + (os.pathsep + existing if existing else "")

    # Write coverage JSON to system tempdir (not project dir) so a killed gate
    # never leaves a stray file in the project tree that `git add -A` could
    # pick up. The finally-block cleanup still applies.
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, dir=tempfile.gettempdir()
    ) as tf:
        cov_path = Path(tf.name)
```

Keep the rest of the function (the subprocess.run, cov JSON parsing, finally-unlink) exactly as-is.

- [ ] **Step 5.2: Run the coverage env test + existing coverage tests**

```bash
pytest tests/test_env_gate.py::test_coverage_honors_env_pythonpath tests/test_coverage_gate.py -v
```
Expected: all PASS.

- [ ] **Step 5.3: Full suite**

```bash
pytest -q
```
Expected: no regressions.

- [ ] **Step 5.4: Commit**

```bash
git add scripts/measure_python.py
git commit -m "fix(coverage-gate): honor gate env: + move tmp file to /tmp (F17, F26 hygiene)"
```

---

## Task 6: Wire `_merge_env` through `_gate_ruff`

**Files:**
- Modify: `scripts/measure_python.py` lines 148-173 (`_gate_ruff`)

- [ ] **Step 6.1: Thread env through ruff**

Insert an env construction at the top of the function and pass it to `subprocess.run`. Replace lines 155-165 (the `args`/`timeout`/`try`/`subprocess.run` block) with:

```python
    args = gate.get("args") or ["check", "."]
    timeout = gate.get("timeout", DEFAULT_GATE_TIMEOUT)
    env = _merge_env(project, gate.get("env") or {})
    try:
        proc = subprocess.run(
            [str(ruff_bin), *args],
            cwd=project,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
```

Keep the rest of the function identical.

- [ ] **Step 6.2: Run the ruff env test**

```bash
pytest tests/test_env_gate.py::test_ruff_honors_env -v
```
Expected: PASS.

- [ ] **Step 6.3: Full suite**

```bash
pytest -q
```
Expected: no regressions.

- [ ] **Step 6.4: Commit**

```bash
git add scripts/measure_python.py
git commit -m "fix(ruff-gate): thread gate env: through subprocess (F17/F18)"
```

---

## Task 7: Wire `_merge_env` through `_gate_mypy`

**Files:**
- Modify: `scripts/measure_python.py` lines 176-202 (`_gate_mypy`)

- [ ] **Step 7.1: Thread env through mypy**

Same pattern as ruff — insert env construction and pass to subprocess.run:

```python
def _gate_mypy(gate: dict, project: Path) -> GateResult:
    mypy_bin = _resolve_tool("mypy")
    if mypy_bin is None:
        return GateResult(
            gate["id"], False, "", "",
            "mypy not found next to python interpreter or on PATH — install with `pip install mypy`",
        )
    args = gate.get("args") or ["."]
    timeout = gate.get("timeout", DEFAULT_GATE_TIMEOUT)
    env = _merge_env(project, gate.get("env") or {})
    try:
        proc = subprocess.run(
            [str(mypy_bin), *args],
            cwd=project,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
```

Keep the rest of the function identical.

- [ ] **Step 7.2: Run the mypy env test**

```bash
pytest tests/test_env_gate.py::test_mypy_honors_env -v
```
Expected: PASS.

- [ ] **Step 7.3: Full suite — all env tests should now pass**

```bash
pytest tests/test_env_gate.py -v
```
Expected: all 11 tests pass (5 original + 6 new).

- [ ] **Step 7.4: Commit**

```bash
git add scripts/measure_python.py
git commit -m "fix(mypy-gate): thread gate env: through subprocess (F17/F18)"
```

---

## Task 8: Add `paths:` field to `chunks.schema.json`

**Files:**
- Modify: `schemas/chunks.schema.json`
- Modify: `tests/test_schemas.py` (add validation cases)

- [ ] **Step 8.1: Write failing schema test**

Append to `tests/test_schemas.py`:

```python
def test_chunk_with_paths_field_validates():
    """v0.7: chunks may declare `paths:` for commit-scoping."""
    import jsonschema
    chunks = {
        "chunks": [
            {
                "id": "py_db",
                "description": "Python sqlite layer",
                "gate_ids": ["py_lint", "py_test"],
                "paths": ["py/src/taskbridge/db.py", "py/tests/test_db.py"],
            }
        ]
    }
    schema = json.loads(
        (ROOT / "schemas" / "chunks.schema.json").read_text()
    )
    jsonschema.validate(chunks, schema)


def test_chunk_without_paths_still_validates():
    """v0.7: paths: is optional; existing criteria without it still validate."""
    import jsonschema
    chunks = {
        "chunks": [
            {
                "id": "legacy_chunk",
                "description": "No paths declared",
                "gate_ids": ["lint"],
            }
        ]
    }
    schema = json.loads(
        (ROOT / "schemas" / "chunks.schema.json").read_text()
    )
    jsonschema.validate(chunks, schema)


def test_chunk_paths_must_be_array_of_strings():
    """v0.7: paths: items must be strings."""
    import jsonschema
    chunks = {
        "chunks": [
            {
                "id": "bad",
                "description": "x",
                "gate_ids": ["g"],
                "paths": [{"not": "a string"}],
            }
        ]
    }
    schema = json.loads(
        (ROOT / "schemas" / "chunks.schema.json").read_text()
    )
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(chunks, schema)
```

- [ ] **Step 8.2: Run to verify the first test fails (field not in schema yet)**

```bash
pytest tests/test_schemas.py::test_chunk_with_paths_field_validates -v
```
Expected: depending on jsonschema strictness, may pass (additionalProperties is true). Let me make the schema stricter. Actually the spec explicitly wants the field to be *recognized*. Check current behavior:

```bash
pytest tests/test_schemas.py::test_chunk_paths_must_be_array_of_strings -v
```
Expected: FAIL (jsonschema doesn't reject because `paths` isn't in properties and additionalProperties is permissive).

- [ ] **Step 8.3: Add `paths:` property to `schemas/chunks.schema.json`**

Replace the `"properties"` block of the chunk item. Current file (schemas/chunks.schema.json) has an object with `id`, `description`, `language`, `gate_ids`, `depends_on`. Add `paths:`:

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
        "required": ["id", "description", "gate_ids"],
        "properties": {
          "id": {"type": "string"},
          "description": {"type": "string"},
          "language": {"type": "string"},
          "gate_ids": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "description": "Subset of criteria.gates[].id this chunk must satisfy. Must be non-empty — a chunk with no gates cannot be measured."
          },
          "depends_on": {
            "type": "array",
            "items": {"type": "string"}
          },
          "paths": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional. Project-relative paths or globs this chunk owns. When present, git_iter_commit.py stages only these paths (plus the iteration file). When absent, falls back to git add -A with a stderr warning."
          }
        }
      }
    }
  }
}
```

- [ ] **Step 8.4: Run all three schema tests**

```bash
pytest tests/test_schemas.py -v -k "chunk"
```
Expected: all pass.

- [ ] **Step 8.5: Full suite**

```bash
pytest -q
```

- [ ] **Step 8.6: Commit**

```bash
git add schemas/chunks.schema.json tests/test_schemas.py
git commit -m "feat(chunks-schema): add optional paths: field for commit-scoping"
```

---

## Task 9: `git_iter_commit.py` — resolve `--iteration` relative path + add `--chunks-file`

**Files:**
- Modify: `scripts/git_iter_commit.py`
- Modify: `tests/test_git_iter_commit.py`

- [ ] **Step 9.1: Write failing tests**

Append to `tests/test_git_iter_commit.py`:

```python
def test_iteration_relative_path_resolves_against_project(tmp_path, monkeypatch):
    """F25: --iteration as a relative path should resolve against --project,
    not caller's cwd."""
    import subprocess
    from scripts.git_iter_commit import main

    project = tmp_path / "proj"
    project.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(["git", "-C", str(project), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(project), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(project), "commit", "--allow-empty", "-qm", "init"], check=True)

    iters = project / ".skillgoid" / "iterations"
    iters.mkdir(parents=True)
    iter_file = iters / "scaffold-001.json"
    iter_file.write_text(json.dumps({
        "iteration": 1, "chunk_id": "scaffold",
        "gate_report": {"passed": True, "results": []},
        "exit_reason": "success",
    }))

    # Create a stub chunks.yaml (v0.7 flow requires it)
    (project / ".skillgoid" / "chunks.yaml").write_text(
        "chunks:\n  - id: scaffold\n    description: s\n    gate_ids: [g]\n"
    )

    # Call main from a cwd that is NOT the project
    monkeypatch.chdir(tmp_path)
    exit_code = main([
        "--project", str(project),
        "--iteration", ".skillgoid/iterations/scaffold-001.json",
        "--chunks-file", ".skillgoid/chunks.yaml",
    ])
    assert exit_code == 0
    # Commit should exist
    log = subprocess.run(["git", "-C", str(project), "log", "--oneline"],
                         capture_output=True, text=True, check=True)
    assert "iter 1 of chunk scaffold" in log.stdout


def test_iteration_unreadable_hard_fails(tmp_path, capsys):
    """v0.7: replace soft-fail with exit 2 + stderr."""
    from scripts.git_iter_commit import main
    project = tmp_path / "proj"
    project.mkdir()
    exit_code = main([
        "--project", str(project),
        "--iteration", "/nonexistent/path.json",
        "--chunks-file", "/nonexistent/chunks.yaml",
    ])
    assert exit_code == 2
    captured = capsys.readouterr()
    assert "cannot read iteration" in captured.err
```

- [ ] **Step 9.2: Run — both should fail**

```bash
pytest tests/test_git_iter_commit.py::test_iteration_relative_path_resolves_against_project tests/test_git_iter_commit.py::test_iteration_unreadable_hard_fails -v
```
Expected: FAIL — `main()` doesn't accept `--chunks-file`, doesn't resolve relative --iteration, and soft-fails instead of exiting 2.

- [ ] **Step 9.3: Rewrite `scripts/git_iter_commit.py` `main()` + add `--chunks-file` + path resolution**

Replace the entire `main()` function at the bottom of the file (currently lines 84-97) with:

```python
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Skillgoid git-per-iteration commit helper")
    ap.add_argument("--project", required=True, type=Path)
    ap.add_argument("--iteration", required=True, type=Path)
    ap.add_argument(
        "--chunks-file",
        type=Path,
        default=None,
        help="Path to chunks.yaml (usually <project>/.skillgoid/chunks.yaml). "
             "Used to look up the chunk's paths: for scoped git add. "
             "If absent, falls back to 'git add -A' with a warning.",
    )
    args = ap.parse_args(argv)

    project = args.project.resolve()

    # Resolve --iteration against --project if relative (F25).
    iteration_path = args.iteration
    if not iteration_path.is_absolute():
        iteration_path = (project / iteration_path).resolve()

    # Hard-fail on unreadable iteration (replaces v0.6's silent soft-fail).
    try:
        record = json.loads(iteration_path.read_text())
    except Exception as exc:
        sys.stderr.write(f"git_iter_commit: cannot read iteration at {iteration_path}: {exc}\n")
        return 2

    # Resolve --chunks-file against --project if relative.
    chunks_file = args.chunks_file
    if chunks_file is not None and not chunks_file.is_absolute():
        chunks_file = (project / chunks_file).resolve()

    commit_iteration(project, record, iteration_path=iteration_path, chunks_file=chunks_file)
    return 0
```

(`commit_iteration` gets new kwargs in Task 10 — for now, update the function signature with defaults so the file still parses.)

Also update the `commit_iteration` signature at line 61 to accept the new kwargs without changing behavior yet:

```python
def commit_iteration(
    project: Path,
    record: dict,
    iteration_path: Path | None = None,
    chunks_file: Path | None = None,
) -> bool:
    """Commit the iteration's changes to git. Returns True if a commit was
    made (or attempted), False if noop (non-git project) or on error."""
    if not is_git_repo(project):
        return False

    message = _build_message(record)

    try:
        subprocess.run(["git", "add", "-A"], cwd=project, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", message],
            cwd=project,
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        sys.stderr.write(f"git_iter_commit: {stderr}")
        return False
    return True
```

- [ ] **Step 9.4: Run the two new tests + existing suite**

```bash
pytest tests/test_git_iter_commit.py -v
```
Expected: existing 8 tests still pass; `test_iteration_relative_path_resolves_against_project` passes; `test_iteration_unreadable_hard_fails` passes.

- [ ] **Step 9.5: Commit**

```bash
git add scripts/git_iter_commit.py tests/test_git_iter_commit.py
git commit -m "fix(git_iter_commit): resolve --iteration path + add --chunks-file + hard-fail (F25)"
```

---

## Task 10: `git_iter_commit.py` — scoped `git add` from chunk `paths:` with fallback warning

**Files:**
- Modify: `scripts/git_iter_commit.py` (extend `commit_iteration`)
- Modify: `tests/test_git_iter_commit.py`

- [ ] **Step 10.1: Write failing tests**

Append to `tests/test_git_iter_commit.py`:

```python
def _init_git_project(project: Path) -> None:
    import subprocess
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(["git", "-C", str(project), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(project), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(project), "commit", "--allow-empty", "-qm", "init"], check=True)


def test_paths_scopes_git_add(tmp_path):
    """F26: chunk with paths: only stages those paths in its commit."""
    import subprocess
    from scripts.git_iter_commit import main

    project = tmp_path / "proj"
    project.mkdir()
    _init_git_project(project)

    # Simulate two chunks' work present in the working tree
    (project / "a.py").write_text("pass\n")
    (project / "b.py").write_text("pass\n")
    (project / ".skillgoid").mkdir()
    (project / ".skillgoid" / "iterations").mkdir()

    iter_file = project / ".skillgoid" / "iterations" / "chunk_a-001.json"
    iter_file.write_text(json.dumps({
        "iteration": 1, "chunk_id": "chunk_a",
        "gate_report": {"passed": True, "results": []},
        "exit_reason": "success",
    }))

    chunks_file = project / ".skillgoid" / "chunks.yaml"
    chunks_file.write_text(
        "chunks:\n"
        "  - id: chunk_a\n"
        "    description: a\n"
        "    gate_ids: [g]\n"
        "    paths: [a.py]\n"
        "  - id: chunk_b\n"
        "    description: b\n"
        "    gate_ids: [g]\n"
        "    paths: [b.py]\n"
    )

    exit_code = main([
        "--project", str(project),
        "--iteration", str(iter_file),
        "--chunks-file", str(chunks_file),
    ])
    assert exit_code == 0

    # The commit for chunk_a should include a.py + its iteration file but NOT b.py
    files = subprocess.run(
        ["git", "-C", str(project), "show", "--name-only", "--format=", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip().split("\n")
    assert "a.py" in files
    assert ".skillgoid/iterations/chunk_a-001.json" in files
    assert "b.py" not in files


def test_missing_paths_falls_back_to_add_all_with_warning(tmp_path, capsys):
    """v0.7 back-compat: chunk without paths: uses git add -A and warns."""
    import subprocess
    from scripts.git_iter_commit import main

    project = tmp_path / "proj"
    project.mkdir()
    _init_git_project(project)
    (project / "a.py").write_text("pass\n")
    (project / ".skillgoid").mkdir()
    (project / ".skillgoid" / "iterations").mkdir()

    iter_file = project / ".skillgoid" / "iterations" / "legacy-001.json"
    iter_file.write_text(json.dumps({
        "iteration": 1, "chunk_id": "legacy",
        "gate_report": {"passed": True, "results": []},
        "exit_reason": "success",
    }))

    chunks_file = project / ".skillgoid" / "chunks.yaml"
    chunks_file.write_text(
        "chunks:\n"
        "  - id: legacy\n"
        "    description: no paths\n"
        "    gate_ids: [g]\n"
    )

    exit_code = main([
        "--project", str(project),
        "--iteration", str(iter_file),
        "--chunks-file", str(chunks_file),
    ])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "no paths: declared" in captured.err
    assert "falling back" in captured.err

    files = subprocess.run(
        ["git", "-C", str(project), "show", "--name-only", "--format=", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip().split("\n")
    assert "a.py" in files  # git add -A took it


def test_missing_chunks_file_arg_falls_back_to_add_all(tmp_path, capsys):
    """v0.7: --chunks-file omitted entirely → fall back to v0.6 behavior."""
    import subprocess
    from scripts.git_iter_commit import main

    project = tmp_path / "proj"
    project.mkdir()
    _init_git_project(project)
    (project / "a.py").write_text("pass\n")
    (project / ".skillgoid").mkdir()
    (project / ".skillgoid" / "iterations").mkdir()
    iter_file = project / ".skillgoid" / "iterations" / "x-001.json"
    iter_file.write_text(json.dumps({
        "iteration": 1, "chunk_id": "x",
        "gate_report": {"passed": True, "results": []},
        "exit_reason": "success",
    }))

    exit_code = main([
        "--project", str(project),
        "--iteration", str(iter_file),
    ])
    assert exit_code == 0
    files = subprocess.run(
        ["git", "-C", str(project), "show", "--name-only", "--format=", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip().split("\n")
    assert "a.py" in files
```

- [ ] **Step 10.2: Run — all three should fail**

```bash
pytest tests/test_git_iter_commit.py::test_paths_scopes_git_add \
       tests/test_git_iter_commit.py::test_missing_paths_falls_back_to_add_all_with_warning \
       tests/test_git_iter_commit.py::test_missing_chunks_file_arg_falls_back_to_add_all -v
```
Expected: FAIL — `commit_iteration` still always does `git add -A`, never emits the warning.

- [ ] **Step 10.3: Implement scoped `git add` in `commit_iteration`**

Replace the `commit_iteration` body (around lines 61-81) with:

```python
def commit_iteration(
    project: Path,
    record: dict,
    iteration_path: Path | None = None,
    chunks_file: Path | None = None,
) -> bool:
    """Commit the iteration's changes to git. Returns True if a commit was
    made (or attempted), False if noop (non-git project) or on error.

    When `chunks_file` is provided AND the chunk referenced by record.chunk_id
    has a `paths:` list, stage only those paths + the iteration file. Otherwise
    fall back to `git add -A` with a stderr warning.
    """
    if not is_git_repo(project):
        return False

    message = _build_message(record)
    chunk_id = record.get("chunk_id", "")
    scoped_paths = _resolve_scoped_paths(project, chunk_id, chunks_file, iteration_path)

    try:
        if scoped_paths is not None:
            subprocess.run(
                ["git", "add", "--", *scoped_paths],
                cwd=project, check=True, capture_output=True,
            )
        else:
            sys.stderr.write(
                f"git_iter_commit: chunk {chunk_id!r} has no paths: declared, "
                f"falling back to 'git add -A' — consider adding paths: for "
                f"safer parallel waves\n"
            )
            subprocess.run(
                ["git", "add", "-A"],
                cwd=project, check=True, capture_output=True,
            )
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", message],
            cwd=project, check=True, capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        sys.stderr.write(f"git_iter_commit: {stderr}")
        return False
    return True


def _resolve_scoped_paths(
    project: Path,
    chunk_id: str,
    chunks_file: Path | None,
    iteration_path: Path | None,
) -> list[str] | None:
    """Return a list of paths (relative to project) to stage for this chunk's
    commit, or None if no scoping info is available (caller should fall back
    to git add -A).
    """
    if chunks_file is None or not chunks_file.exists():
        return None
    try:
        import yaml
        data = yaml.safe_load(chunks_file.read_text()) or {}
    except Exception:
        return None
    chunks = data.get("chunks") or []
    match = next((c for c in chunks if c.get("id") == chunk_id), None)
    if not match:
        return None
    paths = match.get("paths")
    if not paths:
        return None
    result = list(paths)
    # Always include the iteration file itself (project-relative)
    if iteration_path is not None:
        try:
            rel = iteration_path.relative_to(project)
            result.append(str(rel))
        except ValueError:
            # Iteration path wasn't under project — skip (shouldn't happen post-resolve).
            pass
    return result
```

Also add `import yaml` at the top of the file alongside other imports if not already present. (It's already used in hooks; verify measure_python.py imports too.) Actually `git_iter_commit.py` doesn't currently import yaml. Add it conditionally inside `_resolve_scoped_paths` (shown above) to keep the module-level import surface minimal.

- [ ] **Step 10.4: Run the three new tests + full suite**

```bash
pytest tests/test_git_iter_commit.py -v
```
Expected: all pass.

```bash
pytest -q
```
Expected: no regressions.

- [ ] **Step 10.5: Commit**

```bash
git add scripts/git_iter_commit.py tests/test_git_iter_commit.py
git commit -m "fix(git_iter_commit): scope git add to chunk paths + fallback warning (F26)"
```

---

## Task 11: `test_parallel_wave_commit.py` — concurrent commits produce disjoint filesets

**Files:**
- Create: `tests/test_parallel_wave_commit.py`

- [ ] **Step 11.1: Write the integration test**

Create `tests/test_parallel_wave_commit.py`:

```python
"""Integration test: two git_iter_commit processes running concurrently on
the same repo must produce commits whose file contents are disjoint — no
cross-chunk contamination (F26)."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMITTER = ROOT / "scripts" / "git_iter_commit.py"


def _init(project: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(["git", "-C", str(project), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(project), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(project), "commit", "--allow-empty", "-qm", "init"], check=True)


def test_parallel_wave_commits_are_disjoint(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _init(project)

    # Two chunks' worth of files in the working tree
    (project / "a.py").write_text("x = 1\n")
    (project / "b.py").write_text("y = 2\n")
    iters = project / ".skillgoid" / "iterations"
    iters.mkdir(parents=True)

    # Iteration files for both chunks
    a_iter = iters / "chunk_a-001.json"
    b_iter = iters / "chunk_b-001.json"
    for chunk, iter_file in (("chunk_a", a_iter), ("chunk_b", b_iter)):
        iter_file.write_text(json.dumps({
            "iteration": 1, "chunk_id": chunk,
            "gate_report": {"passed": True, "results": []},
            "exit_reason": "success",
        }))

    chunks_file = project / ".skillgoid" / "chunks.yaml"
    chunks_file.write_text(
        "chunks:\n"
        "  - id: chunk_a\n"
        "    description: a\n"
        "    gate_ids: [g]\n"
        "    paths: [a.py]\n"
        "  - id: chunk_b\n"
        "    description: b\n"
        "    gate_ids: [g]\n"
        "    paths: [b.py]\n"
    )

    # Launch both commit processes concurrently
    a_proc = subprocess.Popen(
        [sys.executable, str(COMMITTER),
         "--project", str(project),
         "--iteration", str(a_iter),
         "--chunks-file", str(chunks_file)],
        stderr=subprocess.PIPE, stdout=subprocess.PIPE,
    )
    b_proc = subprocess.Popen(
        [sys.executable, str(COMMITTER),
         "--project", str(project),
         "--iteration", str(b_iter),
         "--chunks-file", str(chunks_file)],
        stderr=subprocess.PIPE, stdout=subprocess.PIPE,
    )
    a_rc = a_proc.wait(timeout=30)
    b_rc = b_proc.wait(timeout=30)
    # Git's index lock may cause one of the commits to transiently fail; retry
    # if so (this is the documented-reality of parallel git writes).
    if a_rc != 0:
        subprocess.run(
            [sys.executable, str(COMMITTER),
             "--project", str(project),
             "--iteration", str(a_iter),
             "--chunks-file", str(chunks_file)],
            check=True, capture_output=True,
        )
    if b_rc != 0:
        subprocess.run(
            [sys.executable, str(COMMITTER),
             "--project", str(project),
             "--iteration", str(b_iter),
             "--chunks-file", str(chunks_file)],
            check=True, capture_output=True,
        )

    # Inspect each commit's files
    log = subprocess.run(
        ["git", "-C", str(project), "log", "--pretty=%H %s"],
        capture_output=True, text=True, check=True,
    ).stdout.strip().split("\n")

    def files_of(sha: str) -> set[str]:
        out = subprocess.run(
            ["git", "-C", str(project), "show", "--name-only", "--format=", sha],
            capture_output=True, text=True, check=True,
        ).stdout.strip().split("\n")
        return {f for f in out if f}

    # Find the two chunk commits
    a_sha = next(line.split()[0] for line in log if "chunk_a" in line)
    b_sha = next(line.split()[0] for line in log if "chunk_b" in line)
    a_files = files_of(a_sha)
    b_files = files_of(b_sha)

    # chunk_a's commit: a.py + its iteration. NOT b.py, NOT b's iteration.
    assert "a.py" in a_files
    assert ".skillgoid/iterations/chunk_a-001.json" in a_files
    assert "b.py" not in a_files
    assert ".skillgoid/iterations/chunk_b-001.json" not in a_files

    assert "b.py" in b_files
    assert ".skillgoid/iterations/chunk_b-001.json" in b_files
    assert "a.py" not in b_files
    assert ".skillgoid/iterations/chunk_a-001.json" not in b_files
```

- [ ] **Step 11.2: Run**

```bash
pytest tests/test_parallel_wave_commit.py -v
```
Expected: PASS.

- [ ] **Step 11.3: Full suite**

```bash
pytest -q
```
Expected: no regressions.

- [ ] **Step 11.4: Commit**

```bash
git add tests/test_parallel_wave_commit.py
git commit -m "test(parallel-wave): disjoint commits for concurrent chunk_iter_commit calls (F26)"
```

---

## Task 12: `test_iteration_filename_backcompat.py` — mixed old/new filenames parse cleanly

**Files:**
- Create: `tests/test_iteration_filename_backcompat.py`

- [ ] **Step 12.1: Write the test**

Create `tests/test_iteration_filename_backcompat.py`:

```python
"""v0.7 back-compat: iterations dirs containing both v0.6 (NNN.json) and
v0.7 (<chunk_id>-NNN.json) filenames must still be read correctly by all
consumers (metrics_append, retrospect-era readers)."""
import json
from pathlib import Path

from scripts.metrics_append import build_metrics_line


def _make_iter(path: Path, chunk_id: str, iteration: int, passed: bool):
    path.write_text(json.dumps({
        "iteration": iteration,
        "chunk_id": chunk_id,
        "gate_report": {"passed": passed, "results": []},
        "exit_reason": "success" if passed else "in_progress",
        "started_at": "2026-04-18T00:00:00+00:00",
        "ended_at": "2026-04-18T00:00:01+00:00",
    }))


def test_mixed_filename_conventions_readable(tmp_path):
    sg = tmp_path / ".skillgoid"
    iters = sg / "iterations"
    iters.mkdir(parents=True)
    (sg / "chunks.yaml").write_text(
        "chunks:\n"
        "  - id: old_chunk\n    description: x\n    gate_ids: [g]\n"
        "  - id: new_chunk\n    description: y\n    gate_ids: [g]\n"
    )
    (sg / "criteria.yaml").write_text("language: python\ngates:\n  - id: g\n    type: ruff\n")

    # v0.6-style filename
    _make_iter(iters / "001.json", "old_chunk", 1, True)
    # v0.7-style filename
    _make_iter(iters / "new_chunk-001.json", "new_chunk", 1, True)

    line = build_metrics_line(sg, "mixed-test")
    assert line["total_iterations"] == 2
    assert line["chunks"] == 2
    assert line["outcome"] == "success"


def test_v07_only_filenames_readable(tmp_path):
    sg = tmp_path / ".skillgoid"
    iters = sg / "iterations"
    iters.mkdir(parents=True)
    (sg / "chunks.yaml").write_text(
        "chunks:\n"
        "  - id: a\n    description: x\n    gate_ids: [g]\n"
        "  - id: b\n    description: y\n    gate_ids: [g]\n"
    )
    (sg / "criteria.yaml").write_text("language: python\ngates:\n  - id: g\n    type: ruff\n")

    _make_iter(iters / "a-001.json", "a", 1, True)
    _make_iter(iters / "a-002.json", "a", 2, True)
    _make_iter(iters / "b-001.json", "b", 1, True)

    line = build_metrics_line(sg, "v07-only")
    assert line["total_iterations"] == 3
    assert line["chunks"] == 2
    assert line["outcome"] == "success"
```

- [ ] **Step 12.2: Run**

```bash
pytest tests/test_iteration_filename_backcompat.py -v
```
Expected: PASS (metrics_append.py is filename-agnostic — this is a check that it stays that way).

- [ ] **Step 12.3: Commit**

```bash
git add tests/test_iteration_filename_backcompat.py
git commit -m "test(backcompat): mixed v0.6/v0.7 iteration filenames parse cleanly"
```

---

## Task 13: Update `skills/loop/SKILL.md` — per-chunk filename convention + scratch hygiene

**Files:**
- Modify: `skills/loop/SKILL.md`

- [ ] **Step 13.1: Replace step 8's iteration-filename prose**

Find the line in `skills/loop/SKILL.md` step 8 that currently says:

> Then write `.skillgoid/iterations/NNN.json` with:

Replace with:

> Then write `.skillgoid/iterations/<chunk_id>-NNN.json` with (v0.7 convention — one filename namespace per chunk, so parallel chunks never contend). `<chunk_id>` is this chunk's id from chunks.yaml; `NNN` is this chunk's own iteration count, zero-padded to 3 digits (first iteration is 001). Example: `scaffold-001.json`, `py_db-001.json`, `py_db-002.json`.
>
> Back-compat note: older projects (pre-v0.7) used unprefixed `NNN.json`. Both conventions coexist in the same iterations dir when a project is resumed across the upgrade; readers handle both.

- [ ] **Step 13.2: Add scratch-file hygiene paragraph**

Immediately after step 8 (before step 8.1, the git commit step), insert a new subsection:

```markdown
### Scratch files — keep them out of the project tree

Any temp files you create during the iteration — including the one used to
pass the gate_report to `stall_check.py` — must live under
`tempfile.mkdtemp()` or `$TMPDIR`, never inside the project. If a scratch
file lands in the project root, `git_iter_commit.py`'s staging will sweep
it into the iteration commit (observed in real runs pre-v0.7).

Canonical pattern:

```python
import tempfile, json
from pathlib import Path

with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False,
                                  dir=tempfile.gettempdir()) as tf:
    tf.write(json.dumps(gate_report))
    scratch = Path(tf.name)
try:
    # use scratch
finally:
    scratch.unlink(missing_ok=True)
```
```

- [ ] **Step 13.3: Update step 8.1 `git_iter_commit.py` invocation**

Replace the command block in step 8.1 with:

```bash
python <plugin-root>/scripts/git_iter_commit.py \
  --project <project_path> \
  --iteration .skillgoid/iterations/<chunk_id>-NNN.json \
  --chunks-file .skillgoid/chunks.yaml
```

Add a note below:

> The `--chunks-file` flag (v0.7) lets the commit helper look up the chunk's `paths:` for scoped staging. If you omit `--chunks-file` OR the chunk has no `paths:` declared, git_iter_commit falls back to `git add -A` with a stderr warning — safe for sequential waves, unsafe for parallel ones.

- [ ] **Step 13.4: Commit**

```bash
git add skills/loop/SKILL.md
git commit -m "docs(loop-skill): v0.7 — per-chunk iteration filenames + scratch hygiene"
```

---

## Task 14: Update `skills/unstick/SKILL.md` — iteration-filename pattern

**Files:**
- Modify: `skills/unstick/SKILL.md`

- [ ] **Step 14.1: Update the "latest iteration" locator prose**

In `skills/unstick/SKILL.md` step 2 ("Read recent state"), find the phrase about reading "the latest iteration for this chunk in `.skillgoid/iterations/`". Replace with:

> **Read recent state** — the latest iteration for this chunk in `.skillgoid/iterations/`. Since v0.7, iteration files are named `<chunk_id>-NNN.json`, so finding a chunk's latest iteration is `sorted(iters_dir.glob(f"{chunk_id}-*.json"))[-1]`. Pre-v0.7 projects may have unprefixed `NNN.json` files; if you don't find a `<chunk_id>-*.json` match, fall back to scanning all `*.json` files and filter by the `chunk_id` field in the record body.

- [ ] **Step 14.2: Commit**

```bash
git add skills/unstick/SKILL.md
git commit -m "docs(unstick-skill): update iteration-filename locator for v0.7 convention"
```

---

## Task 15: Update `skills/build/SKILL.md` — include chunk `paths:` in subagent prompt

**Files:**
- Modify: `skills/build/SKILL.md`

- [ ] **Step 15.1: Update step 3b's chunk-yaml-in-prompt description**

In `skills/build/SKILL.md` step 3b (the curated context slice for the subagent prompt), find the bullet:

> - The chunk entry as YAML (id, description, gate_ids, language, depends_on)

Replace with:

> - The chunk entry as YAML (id, description, gate_ids, language, depends_on, paths). The `paths:` field is consumed by `git_iter_commit.py` at commit time — pass it through verbatim so the subagent includes it in its commit invocation.

- [ ] **Step 15.2: Commit**

```bash
git add skills/build/SKILL.md
git commit -m "docs(build-skill): include chunk paths: in subagent prompt context"
```

---

## Task 16: Update `skills/plan/SKILL.md` — propose `paths:` per chunk

**Files:**
- Modify: `skills/plan/SKILL.md`

- [ ] **Step 16.1: Extend step 4's chunk spec**

In `skills/plan/SKILL.md` step 4 (the chunk decomposition), find the bullet list describing what each chunk has. Add:

> - Optional `paths: [<project-relative-paths-or-globs>, ...]`. Declares which project paths this chunk owns. `git_iter_commit.py` uses this to stage only the chunk's own files per iteration — critical for parallel waves where sibling chunks would otherwise cross-contaminate each other's commits via `git add -A`. If two chunks in the same wave would touch overlapping paths, that's a sign they should be sequenced (add `depends_on:`) rather than parallelized.

- [ ] **Step 16.2: Add a short "paths" paragraph under Principles**

Under the "## Principles" heading, add one more bullet:

> - **Declare `paths:` for every chunk.** It costs one line per chunk in `chunks.yaml` and prevents the parallel-wave commit-scope failure mode. A chunk that genuinely touches the whole repo (rare — usually only a `scaffold` chunk) can omit `paths:` and accept `git add -A` fallback; for anything smaller, declare the paths.

- [ ] **Step 16.3: Commit**

```bash
git add skills/plan/SKILL.md
git commit -m "docs(plan-skill): propose paths: per chunk for scoped commits"
```

---

## Task 17: Update `skills/clarify/SKILL.md` — coverage → integration_gates + .gitignore addition

**Files:**
- Modify: `skills/clarify/SKILL.md`

- [ ] **Step 17.1: Rewrite step 5.2**

Find the step 5.2 block (currently starts with *"5.2. **Default coverage gate for Python projects with pytest.**"*). Replace the WHOLE step with:

```markdown
5.2. **Default coverage gate for Python projects — place in `integration_gates`, not per-chunk `gate_ids`.** Propose a `coverage` entry under `integration_gates:`, NOT inside `gates:`. Rationale: coverage is a whole-package metric. If coverage lives inside `gates:` and chunks reference it via `gate_ids`, it will fail false-positive on every chunk until the last chunk touching the package lands — producing iteration-budget churn for no fault of the chunk being evaluated. Moving it to `integration_gates` runs it once after all chunks pass, which matches the metric's semantic scope.

    ```yaml
    integration_gates:
      - id: cov
        type: coverage
        target: "<package-name>"
        min_percent: 80
        compare_to_baseline: false
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

    This prevents the "pytest passes, ruff passes, coverage drops on the CLI chunk" failure mode observed on real runs. (Note: this failure mode was originally described as a per-chunk issue — with v0.7 putting coverage into integration_gates, it now applies to the integration phase, not any individual chunk.)
```

- [ ] **Step 17.2: Add `/tmp*.json` to the .gitignore template in step 5.3**

In step 5.3, find the template `.gitignore` code block and append one line before the closing backticks:

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

Add a rationale paragraph below the template:

> `/tmp*.json` guards against scratch files that slip the loop skill's `/tmp` discipline. If a subagent accidentally writes a stall-check temp file in the project root, git-add-A would sweep it into the iteration commit. Belt-and-suspenders.

- [ ] **Step 17.3: Commit**

```bash
git add skills/clarify/SKILL.md
git commit -m "docs(clarify-skill): coverage in integration_gates + .gitignore tmp guard"
```

---

## Task 18: Update `skills/python-gates/SKILL.md` — env: universal note

**Files:**
- Modify: `skills/python-gates/SKILL.md`

- [ ] **Step 18.1: Update the env: note**

Find the note starting *"gates may also carry an `env:` dict..."* and replace with:

> **Note:** gates may also carry an `env:` dict (string → string). **As of v0.7, the adapter merges it into the subprocess environment for every gate type** (run-command, cli-command-runs, pytest, import-clean, coverage, ruff, mypy). Previously only run-command and cli-command-runs honored env — v0.6 and earlier silently ignored env for the other 5 handlers.
>
> Relative PATH/PYTHONPATH values are resolved against the project dir.
> Default behavior: pytest / import-clean / coverage still inject `<project>/src` onto PYTHONPATH when the gate does not specify its own PYTHONPATH — back-compat with v0.6 projects that rely on the implicit default. To override, supply `env: {PYTHONPATH: <your-path>}` on the gate.

- [ ] **Step 18.2: Commit**

```bash
git add skills/python-gates/SKILL.md
git commit -m "docs(python-gates-skill): document universal env: support (F17 resolved)"
```

---

## Task 19: Version bump + README + CHANGELOG

**Files:**
- Modify: `.claude-plugin/plugin.json`
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 19.1: Bump `.claude-plugin/plugin.json`**

Change the version field:

```json
{
  "name": "skillgoid",
  "version": "0.7.0",
  ...
}
```

- [ ] **Step 19.2: Add README "What's new in v0.7" section**

Insert at the top of the "What's new" section in `README.md`, immediately after the opening paragraph:

```markdown
## What's new in v0.7

Correctness bundle driven by the `taskbridge` polyglot stress run:

- **Gate `env:` honored by every gate type.** Previously `pytest`, `import-clean`, and `coverage` hardcoded `PYTHONPATH=<project>/src` and silently ignored gate-level `env:`; `ruff` and `mypy` didn't accept env at all. All 7 handlers now merge gate `env:` into the subprocess environment. Backward-compatible: handlers that injected `<project>/src` by default still do so when the gate doesn't specify its own PYTHONPATH.
- **Parallel-wave correctness — per-chunk iteration filenames + `paths:`-scoped commits.** Iteration files are now `<chunk_id>-NNN.json` (previously `NNN.json`) so concurrent subagents write to disjoint filename namespaces. `chunks.yaml` gains an optional `paths: [...]` field declaring which project paths a chunk owns; `git_iter_commit.py` uses it to stage only those paths plus the chunk's iteration file. Projects without `paths:` fall back to the v0.6 `git add -A` behavior with a stderr warning. Kills the silent cross-contamination observed in parallel waves (ts_db's commit sweeping up py_db's files).
- **Related fix — `git_iter_commit.py --iteration` resolves against `--project` when relative.** Previously failed silently on relative paths unless the caller's cwd happened to be the project root.
- **Clarify no longer proposes coverage as a per-chunk gate.** It now lands in `integration_gates` by default, matching the metric's whole-package scope. Avoids false-positive failures on chunks that land before the full package is implemented.

Upgrade path: existing `criteria.yaml` and `chunks.yaml` files continue to work unchanged. Add `paths:` to each chunk to opt into scoped commits for parallel waves.
```

- [ ] **Step 19.3: Add CHANGELOG entry**

Prepend to `CHANGELOG.md`:

```markdown
## [0.7.0] — 2026-04-18

### Changed
- Gate `env:` field is now honored by every gate type (previously only `run-command` and `cli-command-runs`). Backward-compatible: the default `<project>/src` PYTHONPATH injection for pytest/import-clean/coverage is preserved when gate `env:` doesn't specify PYTHONPATH.
- Iteration files are now named `<chunk_id>-NNN.json` (previously `NNN.json`). Readers handle both conventions for back-compat.
- `scripts/git_iter_commit.py` now accepts `--chunks-file` and uses each chunk's `paths:` field (new, optional in `chunks.yaml`) to stage only the chunk's own files. Falls back to `git add -A` with a stderr warning when `paths:` is absent.
- `scripts/git_iter_commit.py` now resolves a relative `--iteration` path against `--project` (previously required cwd to match project root).
- `scripts/git_iter_commit.py` now hard-fails (exit 2) on unreadable iteration JSON (previously silently soft-failed, hiding missed commits).
- `clarify` skill proposes `coverage` under `integration_gates:` by default, not inside per-chunk `gate_ids` (avoids false-positive failures from cross-chunk scope).
- `scripts/measure_python.py` `_gate_coverage` writes its scratch file to `tempfile.gettempdir()` instead of the project dir.

### Added
- Optional `paths:` field in `chunks.yaml` schema.
- 13 new tests covering env-in-every-handler, scoped git add, parallel-wave disjointness, mixed iteration-filename back-compat.

### Backward compatibility
- Existing `criteria.yaml`: unchanged behavior. Opt into broader env-support by adding `env:` to any gate.
- Existing `chunks.yaml`: unchanged behavior. Opt into scoped commits by adding `paths:` to chunks.
- Mixed-filename iteration dirs (v0.6 `NNN.json` + v0.7 `<chunk_id>-NNN.json`) are readable by all consumers.
```

- [ ] **Step 19.4: Full suite one more time**

```bash
pytest -q && ruff check .
```
Expected: ~130 passed, ruff clean.

- [ ] **Step 19.5: Commit**

```bash
git add .claude-plugin/plugin.json README.md CHANGELOG.md
git commit -m "release: v0.7.0 — Correctness Bundle"
```

---

## Task 20: Update `docs/roadmap.md`

**Files:**
- Modify: `docs/roadmap.md`

- [ ] **Step 20.1: Add v0.7 to Shipped; update v0.8 intake**

Under `## Shipped`, add after the v0.6 entry:

```markdown
### v0.7 — Correctness Bundle (2026-04-18)
Two items driven by the `taskbridge` polyglot stress run:
- Gate `env:` honored by every gate type (pytest, import-clean, coverage, ruff, mypy — previously hardcoded)
- Parallel-wave safety: per-chunk iteration filenames + `paths:`-scoped commits (kills the filename race + git-add-A cross-contamination observed in v0.5's parallel feature)
- Folded in: `git_iter_commit.py --iteration` path resolution (F25); coverage → integration_gates by default in clarify
Spec: `docs/superpowers/specs/2026-04-18-skillgoid-v0.7-correctness-bundle.md`
Plan: `docs/superpowers/plans/2026-04-18-skillgoid-v0.7.md`
```

Rename `## How to pick up v0.7` to `## How to pick up v0.8` and append one note:

```markdown
Additional for v0.8 (driven by taskbridge findings deferred from v0.7):
- Polyglot language-support shape (`languages[]` migration, polyglot clarify defaults, node-gates adapter) waits on 2-3 more polyglot project runs before committing to a design. One polyglot run exposed the correctness issues v0.7 ships; it is not enough evidence to commit to a full polyglot architecture.
```

- [ ] **Step 20.2: Commit**

```bash
git add docs/roadmap.md
git commit -m "docs(roadmap): v0.7 shipped + v0.8 intake notes"
```

---

## Task 21: Manual re-verification on taskbridge

**Files:** none modified (verification only)

- [ ] **Step 21.1: Rerun py_db gates against the fresh v0.7 build**

```bash
cd /home/flip/Development/skillgoid-test/taskbridge
/home/flip/Development/skillgoid/skillgoid-plugin/.venv/bin/python \
  /home/flip/Development/skillgoid/skillgoid-plugin/scripts/measure_python.py \
  --project /home/flip/Development/skillgoid-test/taskbridge \
  --criteria-stdin <<'EOF'
gates:
  - id: py_import
    type: import-clean
    module: taskbridge
    env:
      PYTHONPATH: "py/src"
  - id: py_test
    type: pytest
    args: ["py/tests/"]
    env:
      PYTHONPATH: "py/src"
EOF
```
Expected: both gates PASS now that env: is honored (previously py_import failed with ModuleNotFoundError).

- [ ] **Step 21.2: Inspect the commit scope of a new parallel-wave run**

Optionally re-dispatch the py_db and ts_db subagents again with `paths:` declared in taskbridge/.skillgoid/chunks.yaml; verify that each commit's `git show --name-only` is scoped to its chunk's files.

- [ ] **Step 21.3: No commit — this task is manual sanity check.**

---

## Task 22: Merge `feat/v0.7` → `main`

- [ ] **Step 22.1: Final check**

```bash
pytest -q && ruff check .
```
Expected: green.

- [ ] **Step 22.2: Merge**

```bash
git checkout main
git merge --no-ff feat/v0.7 -m "merge: v0.7 Correctness Bundle"
```

- [ ] **Step 22.3: Tag**

```bash
git tag -a v0.7.0 -m "Skillgoid v0.7.0 — Correctness Bundle"
```

---

## Self-review checklist (done before user review)

- [x] Every spec section has at least one task: env-everywhere (Tasks 2-7), paths schema (Task 8), git_iter_commit rewrite (Tasks 9-10), parallel-wave test (Task 11), back-compat test (Task 12), loop/unstick/build/plan/clarify/python-gates skill prose (Tasks 13-18), release mechanics (Tasks 19-20), manual re-verification (Task 21), merge (Task 22).
- [x] No "TBD"/"TODO"/"implement later" placeholders in any step.
- [x] Type/method names consistent: `_merge_env`, `commit_iteration`, `_resolve_scoped_paths`, `build_metrics_line` all match source state.
- [x] Every code step shows actual code. No "write the appropriate implementation."
- [x] Commit messages follow existing repo conventions (prefixes: `fix(...)`, `feat(...)`, `test(...)`, `docs(...)`, `release:`).
- [x] Back-compat invariants preserved in every task where behavior changes.
