# Skillgoid v0.8 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Skillgoid v0.8 — Correctness + Subagent Discipline Bundle. Five items covering seven findings from the minischeme stress run: (1) iteration JSON schema validation before commit (F5+F9), (2) path-overlap auto-serialization in `chunk_topo` (F8), (3) per-chunk `gate_overrides:` in `chunks.yaml` (F3+F12), (4) blueprint slicing — deferred since v0.2 (F7), (5) `## Cross-chunk types` blueprint convention (F6). Plus formally closing plan-refinement-mid-build after 8 runs of zero evidence.

**Architecture:** Two new helper scripts (`validate_iteration.py`, `blueprint_slice.py`), one schema extension (`chunks.schema.json` + `gate_overrides`), modifications to two existing scripts (`chunk_topo.py`, `git_iter_commit.py`), prose-only updates to four skills (`build`, `loop`, `plan`, `python-gates`). Full backward compatibility with v0.7 — every v0.7 project continues to work unchanged.

**Tech Stack:** Python 3.11+, jsonschema, yaml (existing), pytest, ruff. No new runtime dependencies.

**Spec:** `docs/superpowers/specs/2026-04-18-skillgoid-v0.8-correctness-and-discipline.md` (commit `c49907f`).
**Evidence:** `~/Development/skillgoid-test/v0.8-findings.md` + `~/Development/skillgoid-test/minischeme/.skillgoid/retrospective.md`.

---

## Repo layout changes

```
skillgoid-plugin/
├── scripts/
│   ├── validate_iteration.py         # NEW: iteration JSON schema validator
│   ├── blueprint_slice.py            # NEW: chunk-aware blueprint slicer
│   ├── chunk_topo.py                 # MODIFIED: overlap auto-serialize in plan_waves
│   ├── git_iter_commit.py            # MODIFIED: call validate_iteration before commit
│   └── (others unchanged)
├── skills/
│   ├── build/SKILL.md                # MODIFIED: invoke blueprint_slice.py in subagent prompt
│   ├── loop/SKILL.md                 # MODIFIED: apply gate_overrides when filtering criteria
│   ├── plan/SKILL.md                 # MODIFIED: 3 additions (types section, overrides, overlap warning)
│   └── (others unchanged)
├── schemas/
│   └── chunks.schema.json            # MODIFIED: add optional gate_overrides field
├── tests/
│   ├── test_validate_iteration.py    # NEW
│   ├── test_blueprint_slice.py       # NEW
│   ├── test_gate_overrides.py        # NEW
│   ├── test_v08_bundle.py            # NEW: integration test
│   ├── test_chunk_topo.py            # MODIFIED: +4 overlap tests
│   ├── test_schemas.py               # MODIFIED: +3 gate_overrides tests
│   ├── test_git_iter_commit.py       # MODIFIED: +2 validation tests
│   └── (others unchanged)
├── docs/roadmap.md                   # MODIFIED: v0.8 shipped + plan-refinement closed
├── README.md                         # MODIFIED: "What's new in v0.8"
├── CHANGELOG.md                      # MODIFIED: [0.8.0] entry
└── .claude-plugin/plugin.json        # MODIFIED: 0.7.0 → 0.8.0
```

**Expected test count:** 134 (v0.7) → ~154 (+~20).

---

## Task 1: Branch setup

- [ ] **Step 1.1: Verify v0.7 baseline**

```bash
cd /home/flip/Development/skillgoid/skillgoid-plugin
git checkout main
. .venv/bin/activate
pytest -q && ruff check .
git log --oneline -1
```
Expected: 134 passed, ruff clean, latest commit is on v0.7 merge or later.

- [ ] **Step 1.2: Create feat/v0.8 branch**

```bash
git checkout -b feat/v0.8
```

- [ ] **Step 1.3: No commit — housekeeping only**

---

## Task 2: `scripts/validate_iteration.py` — iteration JSON validator

**Files:**
- Create: `scripts/validate_iteration.py`
- Create: `tests/test_validate_iteration.py`

- [ ] **Step 2.1: Write failing tests**

Create `tests/test_validate_iteration.py`:

```python
"""Tests for scripts/validate_iteration.py — iteration JSON schema validator."""
import json
from pathlib import Path

import pytest

from scripts.validate_iteration import validate_iteration


VALID_RECORD = {
    "iteration": 1,
    "chunk_id": "scaffold",
    "gate_report": {"passed": True, "results": []},
}


def test_valid_record_returns_empty_errors():
    assert validate_iteration(VALID_RECORD) == []


def test_missing_required_gate_report_fails():
    bad = {k: v for k, v in VALID_RECORD.items() if k != "gate_report"}
    errors = validate_iteration(bad)
    assert errors
    assert any("gate_report" in e for e in errors)


def test_iteration_as_string_fails():
    bad = {**VALID_RECORD, "iteration": "001"}
    errors = validate_iteration(bad)
    assert errors
    assert any("iteration" in e.lower() for e in errors)


def test_missing_chunk_id_fails():
    bad = {k: v for k, v in VALID_RECORD.items() if k != "chunk_id"}
    errors = validate_iteration(bad)
    assert any("chunk_id" in e for e in errors)


def test_additional_properties_allowed():
    """Schema uses additionalProperties: true — subagents adding extra keys should pass."""
    rec = {**VALID_RECORD, "some_extra_field": "whatever"}
    assert validate_iteration(rec) == []


def test_cli_valid_returns_zero(tmp_path: Path):
    """CLI integration — valid iteration exits 0."""
    import subprocess
    import sys
    rec_file = tmp_path / "iter.json"
    rec_file.write_text(json.dumps(VALID_RECORD))
    result = subprocess.run(
        [sys.executable, "scripts/validate_iteration.py", str(rec_file)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_cli_invalid_returns_two_with_stderr(tmp_path: Path):
    """CLI integration — invalid iteration exits 2 with error messages."""
    import subprocess
    import sys
    rec_file = tmp_path / "iter.json"
    rec_file.write_text(json.dumps({"iteration": "bad", "chunk_id": "x"}))
    result = subprocess.run(
        [sys.executable, "scripts/validate_iteration.py", str(rec_file)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2
    assert "failed validation" in result.stderr or "iteration" in result.stderr


def test_cli_unreadable_path_returns_two(tmp_path: Path):
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, "scripts/validate_iteration.py", str(tmp_path / "nonexistent.json")],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2
```

- [ ] **Step 2.2: Run to confirm tests fail (script doesn't exist)**

```bash
pytest tests/test_validate_iteration.py -v
```
Expected: ImportError or collection failure — `scripts.validate_iteration` doesn't exist yet.

- [ ] **Step 2.3: Create `scripts/validate_iteration.py`**

```python
#!/usr/bin/env python3
"""Iteration JSON schema validator.

Validates a `.skillgoid/iterations/<chunk_id>-NNN.json` record against
`schemas/iterations.schema.json`. Used as a preflight check and called
internally by `git_iter_commit.py` before staging a commit.

Contract:
    validate_iteration(record: dict, schema_path: Path | None = None) -> list[str]
        Returns list of error messages (empty list = valid).

CLI:
    python scripts/validate_iteration.py <iteration-json-path> [--schema <path>]
    Exit 0 if valid; exit 2 if invalid (errors to stderr).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import jsonschema


def _default_schema_path() -> Path:
    return Path(__file__).resolve().parent.parent / "schemas" / "iterations.schema.json"


def validate_iteration(record: dict, schema_path: Path | None = None) -> list[str]:
    """Validate an iteration record. Returns sorted list of error messages."""
    if schema_path is None:
        schema_path = _default_schema_path()
    try:
        schema = json.loads(schema_path.read_text())
    except Exception as exc:
        return [f"cannot load schema at {schema_path}: {exc}"]
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(record), key=lambda e: list(e.path))
    return [
        f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}"
        for e in errors
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Skillgoid iteration JSON validator")
    ap.add_argument("path", type=Path, help="Path to iteration JSON file")
    ap.add_argument("--schema", type=Path, default=None,
                    help="Override schema path (default: schemas/iterations.schema.json)")
    args = ap.parse_args(argv)

    try:
        record = json.loads(args.path.read_text())
    except Exception as exc:
        sys.stderr.write(f"validate_iteration: cannot read {args.path}: {exc}\n")
        return 2

    errors = validate_iteration(record, args.schema)
    if errors:
        sys.stderr.write(f"validate_iteration: {args.path} failed validation:\n")
        for err in errors:
            sys.stderr.write(f"  - {err}\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2.4: Run tests — all should pass**

```bash
pytest tests/test_validate_iteration.py -v
```
Expected: 8 passed.

- [ ] **Step 2.5: Full suite — no regressions**

```bash
pytest -q
```
Expected: ~142 passed (134 + 8 new).

- [ ] **Step 2.6: Commit**

```bash
git add scripts/validate_iteration.py tests/test_validate_iteration.py
git commit -m "feat(validate-iteration): schema validator helper for iteration JSON (F5, F9)"
```

---

## Task 3: Integrate `validate_iteration` into `git_iter_commit.py`

**Files:**
- Modify: `scripts/git_iter_commit.py`
- Modify: `tests/test_git_iter_commit.py`

- [ ] **Step 3.1: Write failing tests**

Append to `tests/test_git_iter_commit.py`:

```python
def test_invalid_iteration_hard_fails(tmp_path, capsys):
    """F9: malformed iteration JSON (missing gate_report) must fail commit."""
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
    bad_iter = iters / "x-001.json"
    bad_iter.write_text(json.dumps({"iteration": 1, "chunk_id": "x"}))  # missing gate_report
    (project / ".skillgoid" / "chunks.yaml").write_text(
        "chunks:\n  - id: x\n    description: x\n    gate_ids: [g]\n"
    )
    exit_code = main([
        "--project", str(project),
        "--iteration", str(bad_iter),
        "--chunks-file", str(project / ".skillgoid" / "chunks.yaml"),
    ])
    assert exit_code == 2
    captured = capsys.readouterr()
    assert "failed validation" in captured.err or "gate_report" in captured.err
    # Commit should NOT have happened
    log = subprocess.run(
        ["git", "-C", str(project), "log", "--oneline"],
        capture_output=True, text=True, check=True,
    )
    assert "iter 1 of chunk x" not in log.stdout


def test_valid_iteration_commits_normally(tmp_path):
    """Regression: valid iteration still commits as in v0.7."""
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
    good_iter = iters / "x-001.json"
    good_iter.write_text(json.dumps({
        "iteration": 1, "chunk_id": "x",
        "gate_report": {"passed": True, "results": []},
        "exit_reason": "success",
    }))
    (project / ".skillgoid" / "chunks.yaml").write_text(
        "chunks:\n  - id: x\n    description: x\n    gate_ids: [g]\n"
    )
    exit_code = main([
        "--project", str(project),
        "--iteration", str(good_iter),
        "--chunks-file", str(project / ".skillgoid" / "chunks.yaml"),
    ])
    assert exit_code == 0
```

- [ ] **Step 3.2: Run — both should fail**

```bash
pytest tests/test_git_iter_commit.py::test_invalid_iteration_hard_fails tests/test_git_iter_commit.py::test_valid_iteration_commits_normally -v
```
Expected: `test_invalid_iteration_hard_fails` FAILS (bad iteration still commits); `test_valid_iteration_commits_normally` PASSES.

- [ ] **Step 3.3: Integrate validation into `scripts/git_iter_commit.py` `main()`**

In `scripts/git_iter_commit.py`, find the block where `record = json.loads(iteration_path.read_text())` is called, and insert validation immediately AFTER it reads the record:

```python
    # Hard-fail on unreadable iteration (v0.7 behavior preserved).
    try:
        record = json.loads(iteration_path.read_text())
    except Exception as exc:
        sys.stderr.write(f"git_iter_commit: cannot read iteration at {iteration_path}: {exc}\n")
        return 2

    # v0.8: schema validation before commit (F5, F9).
    from scripts.validate_iteration import validate_iteration
    errors = validate_iteration(record)
    if errors:
        sys.stderr.write(
            f"git_iter_commit: iteration at {iteration_path} failed schema validation:\n"
        )
        for err in errors:
            sys.stderr.write(f"  - {err}\n")
        return 2
```

Also ensure `scripts/validate_iteration.py` is importable from `scripts.validate_iteration` — this works because `scripts/` already has `__init__.py` (verify with `ls scripts/__init__.py`).

- [ ] **Step 3.4: Run the new tests — both pass**

```bash
pytest tests/test_git_iter_commit.py -v
```
Expected: all pass (existing 13 + 2 new = 15).

- [ ] **Step 3.5: Full suite**

```bash
pytest -q
```
Expected: ~144 passed.

- [ ] **Step 3.6: Commit**

```bash
git add scripts/git_iter_commit.py tests/test_git_iter_commit.py
git commit -m "fix(git_iter_commit): validate iteration JSON before commit (F5, F9)"
```

---

## Task 4: Add path-overlap tests to `test_chunk_topo.py`

**Files:**
- Modify: `tests/test_chunk_topo.py`

- [ ] **Step 4.1: Append failing tests**

Append to `tests/test_chunk_topo.py`:

```python
def test_overlapping_paths_auto_serialize():
    """F8: chunks with overlapping paths in the same wave get split."""
    chunks = [
        {"id": "scaffold"},
        {"id": "a", "depends_on": ["scaffold"], "paths": ["src/shared.py"]},
        {"id": "b", "depends_on": ["scaffold"], "paths": ["src/shared.py", "src/b.py"]},
    ]
    waves = plan_waves(chunks)
    # a and b overlap on shared.py; must NOT be in same wave
    assert waves[0] == ["scaffold"]
    # Wave 2 should have either [a] and wave 3 [b], OR [b] and wave 3 [a]
    wave_sets = [set(w) for w in waves[1:]]
    assert {"a"} in wave_sets or {"b"} in wave_sets
    # Assert they're NOT both in the same wave
    assert not any("a" in w and "b" in w for w in waves)


def test_disjoint_paths_stay_parallel():
    """Regression: non-overlapping paths remain parallel (v0.5 behavior)."""
    chunks = [
        {"id": "scaffold"},
        {"id": "a", "depends_on": ["scaffold"], "paths": ["src/a.py"]},
        {"id": "b", "depends_on": ["scaffold"], "paths": ["src/b.py"]},
    ]
    waves = plan_waves(chunks)
    assert waves[0] == ["scaffold"]
    assert set(waves[1]) == {"a", "b"}
    assert len(waves) == 2


def test_three_way_overlap_produces_three_sub_waves():
    """All three chunks pairwise-overlap → three serial sub-waves."""
    chunks = [
        {"id": "scaffold"},
        {"id": "a", "depends_on": ["scaffold"], "paths": ["src/core.py"]},
        {"id": "b", "depends_on": ["scaffold"], "paths": ["src/core.py"]},
        {"id": "c", "depends_on": ["scaffold"], "paths": ["src/core.py"]},
    ]
    waves = plan_waves(chunks)
    assert waves[0] == ["scaffold"]
    assert waves[1:] == [["a"], ["b"], ["c"]]  # alphabetical order for determinism


def test_overlap_serialization_is_deterministic():
    """Alphabetical grouping produces identical waves across runs."""
    chunks = [
        {"id": "scaffold"},
        {"id": "z", "depends_on": ["scaffold"], "paths": ["src/shared.py"]},
        {"id": "a", "depends_on": ["scaffold"], "paths": ["src/shared.py"]},
        {"id": "m", "depends_on": ["scaffold"], "paths": ["src/shared.py"]},
    ]
    waves = plan_waves(chunks)
    assert waves[0] == ["scaffold"]
    assert waves[1:] == [["a"], ["m"], ["z"]]


def test_chunks_without_paths_dont_split():
    """Chunks that don't declare paths: remain parallel (v0.5 back-compat)."""
    chunks = [
        {"id": "scaffold"},
        {"id": "a", "depends_on": ["scaffold"]},  # no paths
        {"id": "b", "depends_on": ["scaffold"]},  # no paths
    ]
    waves = plan_waves(chunks)
    assert waves[0] == ["scaffold"]
    assert set(waves[1]) == {"a", "b"}
```

- [ ] **Step 4.2: Run — first 4 tests should fail (no overlap logic yet)**

```bash
pytest tests/test_chunk_topo.py -v
```
Expected: `test_disjoint_paths_stay_parallel` and `test_chunks_without_paths_dont_split` pass (existing behavior); `test_overlapping_paths_auto_serialize`, `test_three_way_overlap_produces_three_sub_waves`, `test_overlap_serialization_is_deterministic` FAIL because overlap split isn't implemented.

- [ ] **Step 4.3: No commit — tests only; implementation in Task 5**

---

## Task 5: Implement path-overlap auto-serialize in `chunk_topo.py`

**Files:**
- Modify: `scripts/chunk_topo.py`

- [ ] **Step 5.1: Read existing `chunk_topo.py` to understand the shape**

```bash
cat scripts/chunk_topo.py
```

Note the current `plan_waves(chunks)` function and its dependencies (internal helpers, imports). The post-pass integrates AFTER the existing wave computation.

- [ ] **Step 5.2: Add overlap helpers + extend plan_waves**

In `scripts/chunk_topo.py`, add these helpers before the existing `plan_waves` definition (or at the top of the module after imports):

```python
def _paths_overlap(a: list[str], b: list[str]) -> bool:
    """Exact-string match on any path element between two chunks' paths lists.
    v0.8 uses exact matching; glob-aware matching is deferred to v0.9 if
    evidence shows users want it."""
    if not a or not b:
        return False
    return bool(set(a) & set(b))


def _split_wave_on_overlap(wave: list[str], chunks_by_id: dict[str, dict]) -> list[list[str]]:
    """Split a wave into consecutive sub-waves when chunks' paths: overlap.
    Greedy, alphabetical-order placement for determinism.
    Returns [wave] unchanged when no overlap exists."""
    if len(wave) <= 1:
        return [wave]
    sorted_chunks = sorted(wave)
    sub_waves: list[list[str]] = []
    for chunk_id in sorted_chunks:
        paths = chunks_by_id[chunk_id].get("paths") or []
        placed = False
        for sw in sub_waves:
            if all(
                not _paths_overlap(paths, chunks_by_id[cid].get("paths") or [])
                for cid in sw
            ):
                sw.append(chunk_id)
                placed = True
                break
        if not placed:
            sub_waves.append([chunk_id])
    if len(sub_waves) > 1:
        import sys
        sys.stderr.write(
            f"chunk_topo: wave {sorted_chunks!r} split into {len(sub_waves)} "
            f"sub-waves due to overlapping paths: {sub_waves!r}\n"
        )
    return sub_waves
```

Then modify the existing `plan_waves` to apply the split. After the existing topo-sort produces its list of waves (let's call that `initial_waves` in the existing code), replace the final return with:

```python
    chunks_by_id = {c["id"]: c for c in chunks}
    result: list[list[str]] = []
    for wave in initial_waves:
        for sub in _split_wave_on_overlap(wave, chunks_by_id):
            result.append(sub)
    return result
```

(The exact integration depends on the existing code's variable names — the implementer reads the file and adapts.)

- [ ] **Step 5.3: Run overlap tests — all should pass**

```bash
pytest tests/test_chunk_topo.py -v
```
Expected: all pass (existing + 5 new).

- [ ] **Step 5.4: Full suite**

```bash
pytest -q
```
Expected: ~149 passed.

- [ ] **Step 5.5: Commit**

```bash
git add scripts/chunk_topo.py tests/test_chunk_topo.py
git commit -m "feat(chunk_topo): auto-serialize waves with overlapping chunk paths (F8)"
```

---

## Task 6: Add `gate_overrides` to `chunks.schema.json`

**Files:**
- Modify: `schemas/chunks.schema.json`
- Modify: `tests/test_schemas.py`

- [ ] **Step 6.1: Write failing schema tests**

Append to `tests/test_schemas.py`:

```python
def test_chunk_with_gate_overrides_validates():
    """v0.8: chunks may declare gate_overrides for per-chunk gate arg narrowing."""
    chunks = {
        "chunks": [
            {
                "id": "py_db",
                "description": "x",
                "gate_ids": ["lint", "pytest_chunk"],
                "gate_overrides": {
                    "pytest_chunk": {"args": ["tests/test_py_db.py"]},
                    "lint": {"args": ["check", "src/taskbridge/db.py"]},
                },
            }
        ]
    }
    errors = list(_validator("chunks.schema.json").iter_errors(chunks))
    assert errors == []


def test_chunk_gate_overrides_args_must_be_string_array():
    chunks = {
        "chunks": [
            {
                "id": "bad",
                "description": "x",
                "gate_ids": ["g"],
                "gate_overrides": {"g": {"args": [123]}},  # int instead of str
            }
        ]
    }
    errors = list(_validator("chunks.schema.json").iter_errors(chunks))
    assert any(e.validator == "type" for e in errors)


def test_chunk_without_gate_overrides_still_validates():
    """v0.7 back-compat: chunks without gate_overrides still validate."""
    chunks = {
        "chunks": [
            {
                "id": "legacy",
                "description": "x",
                "gate_ids": ["g"],
            }
        ]
    }
    errors = list(_validator("chunks.schema.json").iter_errors(chunks))
    assert errors == []
```

- [ ] **Step 6.2: Run — first test and second should fail (field not in schema)**

```bash
pytest tests/test_schemas.py -v -k "gate_overrides"
```
Expected: `test_chunk_with_gate_overrides_validates` may pass (additionalProperties is true on chunk items); `test_chunk_gate_overrides_args_must_be_string_array` FAILS (no type constraint since property isn't declared). `test_chunk_without_gate_overrides_still_validates` passes.

- [ ] **Step 6.3: Extend `schemas/chunks.schema.json`**

Replace the chunk item's `properties` block in `schemas/chunks.schema.json` — add `gate_overrides` after the existing `paths` entry:

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
            "description": "Subset of criteria.gates[].id this chunk must satisfy."
          },
          "depends_on": {
            "type": "array",
            "items": {"type": "string"}
          },
          "paths": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional. Project-relative paths this chunk owns."
          },
          "gate_overrides": {
            "type": "object",
            "additionalProperties": {
              "type": "object",
              "properties": {
                "args": {"type": "array", "items": {"type": "string"}}
              },
              "additionalProperties": false
            },
            "description": "Optional per-chunk gate argument overrides. Keys are gate ids; values override that gate's args when running this chunk. Other gate fields (type, env, timeout) come from criteria.yaml unchanged."
          }
        }
      }
    }
  }
}
```

- [ ] **Step 6.4: Run schema tests — all pass**

```bash
pytest tests/test_schemas.py -v
```
Expected: all pass.

- [ ] **Step 6.5: Full suite**

```bash
pytest -q
```
Expected: ~152 passed.

- [ ] **Step 6.6: Commit**

```bash
git add schemas/chunks.schema.json tests/test_schemas.py
git commit -m "feat(chunks-schema): add optional gate_overrides per chunk (F3, F12)"
```

---

## Task 7: `tests/test_gate_overrides.py` + loop SKILL.md prose

**Files:**
- Create: `tests/test_gate_overrides.py`
- Modify: `skills/loop/SKILL.md`
- Modify: `skills/plan/SKILL.md`

- [ ] **Step 7.1: Write the merging-logic test**

Create `tests/test_gate_overrides.py`:

```python
"""Tests for per-chunk gate_overrides merging logic.
This logic lives in the loop skill prose — the test asserts the EXPECTED shape
of the criteria subset after merging, so future code helpers can reference it
and stay compliant."""


def _apply_gate_overrides(chunk: dict, gates: list[dict]) -> list[dict]:
    """Simulate the loop skill's override-merging behavior.
    For each gate, if the chunk has gate_overrides[gate.id], replace the gate's
    `args` with the override's `args`. All other gate fields unchanged."""
    overrides = chunk.get("gate_overrides") or {}
    result = []
    for gate in gates:
        g = dict(gate)
        ov = overrides.get(g["id"])
        if ov and "args" in ov:
            g["args"] = list(ov["args"])
        result.append(g)
    return result


def test_override_replaces_args():
    chunk = {"id": "py_db", "gate_overrides": {"pytest_chunk": {"args": ["tests/test_py_db.py"]}}}
    gates = [{"id": "pytest_chunk", "type": "pytest", "args": ["tests/"], "env": {"PYTHONPATH": "src"}}]
    result = _apply_gate_overrides(chunk, gates)
    assert result[0]["args"] == ["tests/test_py_db.py"]
    assert result[0]["env"] == {"PYTHONPATH": "src"}  # preserved
    assert result[0]["type"] == "pytest"  # preserved


def test_override_absent_falls_through():
    chunk = {"id": "py_db"}  # no overrides
    gates = [{"id": "pytest_chunk", "type": "pytest", "args": ["tests/"]}]
    result = _apply_gate_overrides(chunk, gates)
    assert result[0]["args"] == ["tests/"]


def test_override_only_affects_matching_gate():
    chunk = {"id": "py_db", "gate_overrides": {"pytest_chunk": {"args": ["tests/test_py_db.py"]}}}
    gates = [
        {"id": "lint", "type": "ruff", "args": ["check", "."]},
        {"id": "pytest_chunk", "type": "pytest", "args": ["tests/"]},
    ]
    result = _apply_gate_overrides(chunk, gates)
    assert result[0]["args"] == ["check", "."]  # lint unchanged
    assert result[1]["args"] == ["tests/test_py_db.py"]  # pytest overridden


def test_multiple_overrides():
    chunk = {
        "id": "py_db",
        "gate_overrides": {
            "pytest_chunk": {"args": ["tests/test_py_db.py"]},
            "lint": {"args": ["check", "src/taskbridge/db.py"]},
        },
    }
    gates = [
        {"id": "lint", "type": "ruff", "args": ["check", "."]},
        {"id": "pytest_chunk", "type": "pytest", "args": ["tests/"]},
    ]
    result = _apply_gate_overrides(chunk, gates)
    assert result[0]["args"] == ["check", "src/taskbridge/db.py"]
    assert result[1]["args"] == ["tests/test_py_db.py"]
```

- [ ] **Step 7.2: Run tests — all should pass**

```bash
pytest tests/test_gate_overrides.py -v
```
Expected: 4 passed.

- [ ] **Step 7.3: Update `skills/loop/SKILL.md`**

In `skills/loop/SKILL.md`, find the Setup section (around step 3 "Resolve gates") and add a new sub-step 3.1 after it:

```markdown
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
```

- [ ] **Step 7.4: Update `skills/plan/SKILL.md`**

In `skills/plan/SKILL.md` step 4 (chunk decomposition bullet list), add:

```markdown
   - Optional `gate_overrides: {<gate_id>: {args: [...]}}`. Per-chunk gate argument narrowing. Propose this when a chunk owns a test file matching `tests/test_<chunk_id>.py` or a source subdirectory predictable from the chunk's `paths:`. Prevents sibling-in-flight test failures in parallel waves.
     Example: `gate_overrides: {pytest_chunk: {args: ["tests/test_<chunk_id>.py"]}, lint: {args: ["check", <chunk_paths>...]}}`.
```

- [ ] **Step 7.5: Full suite + ruff**

```bash
pytest -q && ruff check .
```
Expected: ~156 passed, ruff clean.

- [ ] **Step 7.6: Commit**

```bash
git add tests/test_gate_overrides.py skills/loop/SKILL.md skills/plan/SKILL.md
git commit -m "feat(gate-overrides): loop applies per-chunk args + plan proposes them (F3, F12)"
```

---

## Task 8: Blueprint slicer tests

**Files:**
- Create: `tests/test_blueprint_slice.py`

- [ ] **Step 8.1: Write failing tests**

Create `tests/test_blueprint_slice.py`:

```python
"""Tests for scripts/blueprint_slice.py — chunk-aware blueprint slicer."""
from pathlib import Path

import pytest

from scripts.blueprint_slice import slice_blueprint


BLUEPRINT_WITH_ALL_SECTIONS = """\
# Blueprint — test

## Architecture overview

Arch text here.

## Cross-chunk types

Nil — defined in values.py.

## scaffold

Scaffold section.

## parser

Parser section.

## evaluator-core

Evaluator section.
"""

BLUEPRINT_NO_CROSS_CHUNK_TYPES = """\
# Blueprint — test

## Architecture overview

Arch text.

## scaffold

Scaffold.

## parser

Parser.
"""

BLUEPRINT_NO_H2 = """\
# Blueprint — legacy

Just prose, no H2 headings.
"""


def test_slice_returns_chunk_section_plus_overview_plus_types():
    result = slice_blueprint(BLUEPRINT_WITH_ALL_SECTIONS, "parser")
    assert "## Architecture overview" in result
    assert "Arch text here." in result
    assert "## Cross-chunk types" in result
    assert "Nil — defined in values.py." in result
    assert "## parser" in result
    assert "Parser section." in result
    # Should NOT include other chunks' sections
    assert "## scaffold" not in result
    assert "Scaffold section." not in result
    assert "## evaluator-core" not in result
    assert "Evaluator section." not in result


def test_slice_works_for_first_chunk():
    result = slice_blueprint(BLUEPRINT_WITH_ALL_SECTIONS, "scaffold")
    assert "## scaffold" in result
    assert "Scaffold section." in result
    assert "## parser" not in result


def test_slice_without_cross_chunk_types_warns(capsys):
    result = slice_blueprint(BLUEPRINT_NO_CROSS_CHUNK_TYPES, "parser")
    captured = capsys.readouterr()
    assert "Cross-chunk types" in captured.err  # warning present
    # Still returns arch + chunk section
    assert "## Architecture overview" in result
    assert "## parser" in result
    assert "Parser." in result


def test_slice_unknown_chunk_id_raises():
    with pytest.raises(ValueError, match="does-not-exist"):
        slice_blueprint(BLUEPRINT_WITH_ALL_SECTIONS, "does-not-exist")


def test_slice_legacy_no_h2_returns_full_content(capsys):
    result = slice_blueprint(BLUEPRINT_NO_H2, "anything")
    captured = capsys.readouterr()
    assert "no H2 headings" in captured.err
    assert result == BLUEPRINT_NO_H2


def test_slice_chunk_id_with_hyphen():
    md = """\
# Blueprint

## Architecture overview
Arch.

## special-forms
Special forms section.

## tail-calls
Tail calls section.
"""
    result = slice_blueprint(md, "special-forms")
    assert "## special-forms" in result
    assert "Special forms section." in result
    assert "## tail-calls" not in result


def test_slice_cli_valid(tmp_path: Path):
    import subprocess
    import sys
    bp = tmp_path / "blueprint.md"
    bp.write_text(BLUEPRINT_WITH_ALL_SECTIONS)
    result = subprocess.run(
        [sys.executable, "scripts/blueprint_slice.py",
         "--blueprint", str(bp), "--chunk-id", "parser"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
    assert "## parser" in result.stdout
    assert "Parser section." in result.stdout


def test_slice_cli_unknown_chunk_returns_two(tmp_path: Path):
    import subprocess
    import sys
    bp = tmp_path / "blueprint.md"
    bp.write_text(BLUEPRINT_WITH_ALL_SECTIONS)
    result = subprocess.run(
        [sys.executable, "scripts/blueprint_slice.py",
         "--blueprint", str(bp), "--chunk-id", "nonexistent"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2
    assert "nonexistent" in result.stderr
```

- [ ] **Step 8.2: Run — all fail (script doesn't exist)**

```bash
pytest tests/test_blueprint_slice.py -v
```
Expected: collection fails with `ImportError: scripts.blueprint_slice`.

- [ ] **Step 8.3: No commit — tests only**

---

## Task 9: Implement `scripts/blueprint_slice.py`

**Files:**
- Create: `scripts/blueprint_slice.py`

- [ ] **Step 9.1: Create the slicer**

Create `scripts/blueprint_slice.py`:

```python
#!/usr/bin/env python3
"""Blueprint slicer: extract the relevant section(s) for a specific chunk.

Given a `blueprint.md` file with `## <chunk-id>` H2 headings (one per chunk),
produce a sliced view containing:
  1. `## Architecture overview` (always, when present)
  2. `## Cross-chunk types` (always, when present; warning logged if absent)
  3. `## <chunk_id>` (raised ValueError if not present)

Legacy behavior: if the blueprint has no H2 headings at all, returns the full
blueprint content with a warning. This supports projects that haven't adopted
the v0.2 heading discipline.

Public surface:
    slice_blueprint(md: str, chunk_id: str) -> str

CLI:
    python scripts/blueprint_slice.py --blueprint <path> --chunk-id <id>
    Prints sliced content to stdout; errors to stderr; exit 2 on failure.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


_H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def _parse_sections(md: str) -> dict[str, str]:
    """Return dict mapping H2 heading → section body (heading included).
    Body runs from the heading to (but not including) the next H2 or EOF."""
    sections: dict[str, str] = {}
    matches = list(_H2_RE.finditer(md))
    if not matches:
        return sections
    for i, m in enumerate(matches):
        heading = m.group(1).strip()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md)
        sections[heading] = md[start:end].rstrip() + "\n"
    return sections


def slice_blueprint(md: str, chunk_id: str) -> str:
    """Return the sliced blueprint for a given chunk_id.

    Raises ValueError if no `## <chunk_id>` section exists.
    Warns to stderr if `## Cross-chunk types` is absent (still proceeds).
    Returns full content if blueprint has no H2 headings at all.
    """
    sections = _parse_sections(md)
    if not sections:
        sys.stderr.write(
            "blueprint_slice: no H2 headings found in blueprint; "
            "returning full content\n"
        )
        return md

    parts: list[str] = []
    if "Architecture overview" in sections:
        parts.append(sections["Architecture overview"])
    if "Cross-chunk types" in sections:
        parts.append(sections["Cross-chunk types"])
    else:
        sys.stderr.write(
            "blueprint_slice: no `## Cross-chunk types` section declared "
            "— consider adding one for multi-chunk type contracts (F6)\n"
        )

    if chunk_id not in sections:
        raise ValueError(
            f"blueprint_slice: no `## {chunk_id}` section in blueprint. "
            f"Available H2 sections: {sorted(sections)}"
        )
    parts.append(sections[chunk_id])
    return "\n".join(parts).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Slice blueprint for a specific chunk")
    ap.add_argument("--blueprint", required=True, type=Path)
    ap.add_argument("--chunk-id", required=True)
    args = ap.parse_args(argv)
    try:
        md = args.blueprint.read_text()
    except Exception as exc:
        sys.stderr.write(f"blueprint_slice: cannot read {args.blueprint}: {exc}\n")
        return 2
    try:
        sys.stdout.write(slice_blueprint(md, args.chunk_id))
    except ValueError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 9.2: Run the slicer tests — all pass**

```bash
pytest tests/test_blueprint_slice.py -v
```
Expected: 8 passed.

- [ ] **Step 9.3: Full suite**

```bash
pytest -q && ruff check .
```
Expected: ~164 passed, ruff clean.

- [ ] **Step 9.4: Commit**

```bash
git add scripts/blueprint_slice.py tests/test_blueprint_slice.py
git commit -m "feat(blueprint-slice): chunk-aware blueprint slicer helper (F7)"
```

---

## Task 10: `build` SKILL.md uses the slicer

**Files:**
- Modify: `skills/build/SKILL.md`

- [ ] **Step 10.1: Update step 3b prose**

In `skills/build/SKILL.md`, find step 3b's context-slice description (currently the bullet list that includes "The chunk entry as YAML" and "blueprint.md in full"). Replace the `blueprint.md in full` bullet with:

```markdown
      - **Sliced blueprint for the chunk** (v0.8, replacing v0.2's punt on slicing). Invoke the slicer:
        ```
        python <plugin-root>/scripts/blueprint_slice.py \
          --blueprint .skillgoid/blueprint.md \
          --chunk-id <chunk_id>
        ```
        Use the output as the "Blueprint (relevant)" section of the subagent prompt. Subagents receive their chunk's section + `## Architecture overview` + `## Cross-chunk types` (when present) — not the full blueprint.

        If the slicer exits 2 (no `## <chunk_id>` section in blueprint), surface the error and do NOT dispatch — this is a blueprint authoring error that the plan step should have caught.
```

Also update the preceding bullet to include `gate_overrides`:

```markdown
      - The chunk entry as YAML (id, description, gate_ids, language, depends_on, paths, gate_overrides). Pass the chunk yaml verbatim so the subagent can build the correct criteria subset using the override-merging logic from `skills/loop/SKILL.md` step 3.1.
```

- [ ] **Step 10.2: Verify via grep**

```bash
grep -n "blueprint_slice\|gate_overrides" skills/build/SKILL.md
```
Expected: both terms appear.

- [ ] **Step 10.3: Commit**

```bash
git add skills/build/SKILL.md
git commit -m "docs(build-skill): subagent prompt uses sliced blueprint (F7)"
```

---

## Task 11: `plan` SKILL.md — Cross-chunk types convention + same-file overlap warning

**Files:**
- Modify: `skills/plan/SKILL.md`

- [ ] **Step 11.1: Add the Cross-chunk types mandate to step 3**

In `skills/plan/SKILL.md` step 3 ("Write `blueprint.md`"), add a new bullet after the architecture-overview line:

```markdown
   - **Cross-chunk types section** (v0.8, REQUIRED for multi-chunk type contracts). Immediately after the architecture overview, add a `## Cross-chunk types` section enumerating types that multiple chunks consume, with the canonical module each lives in. Example:

     ```markdown
     ## Cross-chunk types

     Types that multiple chunks consume. All chunks MUST import these from the listed module rather than re-define them locally.

     - `Nil` (sentinel) — defined in `src/mypkg/values.py`.
     - `SExpr` (ADT: Atom, Symbol, Pair, Nil) — defined in `src/mypkg/parser.py`.
     - `Environment` — defined in `src/mypkg/environment.py`.

     Do not re-define these types in any other module.
     ```

     Omitting this section is not a hard error but surfaces as a slicer warning at build time (F6 from v0.8 findings: parser subagent invented its own Nil singleton because the blueprint didn't declare the shared one). The blueprint slicer always includes this section in every subagent's prompt when present.
```

- [ ] **Step 11.2: Add the overlap warning under Principles**

Find the `## Principles` section (currently has bullets about "Small chunks", "Gate early", "Dependency-order the list", "Heading discipline", "Declare paths:"). Add a new bullet:

```markdown
- **Avoid same-file chunks in the same wave.** Two chunks that modify overlapping `paths:` cannot safely commit in parallel — one's changes get committed under the other's chunk message. `chunk_topo` now auto-serializes these (v0.8), but a clean blueprint avoids the overlap in the first place. Either split the work into disjoint files, or add explicit `depends_on` to serialize by dependency.
```

- [ ] **Step 11.3: Verify**

```bash
grep -n "Cross-chunk types\|Avoid same-file" skills/plan/SKILL.md
```
Expected: both terms appear.

- [ ] **Step 11.4: Commit**

```bash
git add skills/plan/SKILL.md
git commit -m "docs(plan-skill): Cross-chunk types convention + same-file overlap warning (F6, F8)"
```

---

## Task 12: Integration test — `tests/test_v08_bundle.py`

**Files:**
- Create: `tests/test_v08_bundle.py`

- [ ] **Step 12.1: Write the integration test**

Create `tests/test_v08_bundle.py`:

```python
"""End-to-end integration test exercising all v0.8 items together.

Synthetic 3-chunk project with:
  - chunk A owning src/shared.py + tests/test_a.py
  - chunk B owning src/shared.py + src/b.py + tests/test_b.py (deliberate overlap with A)
  - chunk C owning src/c.py + tests/test_c.py (no overlap)

Asserts:
  1. chunk_topo.plan_waves splits [A, B, C] into two waves: [A, C] then [B]
     (B overlaps A on shared.py).
  2. blueprint_slice returns A's section + architecture overview + cross-chunk types;
     does NOT include B's or C's sections.
  3. git_iter_commit rejects a schema-invalid iteration JSON with exit 2.
  4. gate_overrides merging produces the expected narrowed args.
"""
import json
import subprocess
import sys
from pathlib import Path

from scripts.chunk_topo import plan_waves
from scripts.blueprint_slice import slice_blueprint
from scripts.validate_iteration import validate_iteration


INTEGRATION_BLUEPRINT = """\
# Blueprint — integration fixture

## Architecture overview

Three-chunk synthetic project for v0.8 integration testing.

## Cross-chunk types

- `Shared` — defined in `src/shared.py`. Import, do not re-define.

## chunk-a

Chunk A owns src/shared.py.

## chunk-b

Chunk B owns src/shared.py AND src/b.py (deliberate overlap with A).

## chunk-c

Chunk C owns src/c.py (no overlap).
"""

INTEGRATION_CHUNKS = [
    {"id": "chunk-a", "paths": ["src/shared.py", "tests/test_a.py"]},
    {"id": "chunk-b", "depends_on": [], "paths": ["src/shared.py", "src/b.py", "tests/test_b.py"]},
    {"id": "chunk-c", "paths": ["src/c.py", "tests/test_c.py"]},
]


def test_path_overlap_splits_wave():
    """Item 2 (F8): A and B overlap on shared.py; must be in different waves."""
    waves = plan_waves(INTEGRATION_CHUNKS)
    # All 3 chunks have no depends_on; would all be in wave 0 without overlap split.
    # Overlap splits A from B (alphabetical: A, C in one group; B follows).
    a_wave = next(i for i, w in enumerate(waves) if "chunk-a" in w)
    b_wave = next(i for i, w in enumerate(waves) if "chunk-b" in w)
    c_wave = next(i for i, w in enumerate(waves) if "chunk-c" in w)
    assert a_wave != b_wave, "A and B must be in different waves"
    # C doesn't overlap A or B; C can share a wave with either, depending on order
    assert c_wave in (a_wave, b_wave)


def test_blueprint_slice_extracts_chunk_context():
    """Item 4 (F7): slicer returns arch overview + cross-chunk types + chunk's own section."""
    result = slice_blueprint(INTEGRATION_BLUEPRINT, "chunk-a")
    assert "## Architecture overview" in result
    assert "## Cross-chunk types" in result
    assert "## chunk-a" in result
    assert "Chunk A owns src/shared.py." in result
    # Other chunks' sections MUST be absent
    assert "## chunk-b" not in result
    assert "## chunk-c" not in result
    assert "Chunk B owns" not in result
    assert "Chunk C owns" not in result


def test_schema_validation_rejects_bad_iteration():
    """Item 1 (F5+F9): a record missing gate_report fails validation."""
    bad = {"iteration": 1, "chunk_id": "x"}
    errors = validate_iteration(bad)
    assert errors
    assert any("gate_report" in e for e in errors)


def test_git_iter_commit_refuses_invalid_iteration(tmp_path: Path):
    """Item 1 end-to-end: git_iter_commit exits 2 on bad iteration JSON."""
    project = tmp_path / "proj"
    project.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(["git", "-C", str(project), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(project), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(project), "commit", "--allow-empty", "-qm", "init"], check=True)
    iters = project / ".skillgoid" / "iterations"
    iters.mkdir(parents=True)
    bad = iters / "chunk-a-001.json"
    bad.write_text(json.dumps({"iteration": 1, "chunk_id": "chunk-a"}))  # missing gate_report
    (project / ".skillgoid" / "chunks.yaml").write_text(
        "chunks:\n  - id: chunk-a\n    description: x\n    gate_ids: [g]\n"
    )
    result = subprocess.run(
        [sys.executable, "scripts/git_iter_commit.py",
         "--project", str(project),
         "--iteration", str(bad),
         "--chunks-file", str(project / ".skillgoid" / "chunks.yaml")],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2
    assert "validation" in result.stderr.lower() or "gate_report" in result.stderr


def test_gate_overrides_merge():
    """Item 3 (F3+F12): gate_overrides narrow args; other fields preserved."""
    chunk = {
        "id": "chunk-a",
        "gate_overrides": {
            "pytest_chunk": {"args": ["tests/test_a.py"]},
        },
    }
    gates = [
        {"id": "pytest_chunk", "type": "pytest", "args": ["tests/"], "env": {"PYTHONPATH": "src"}},
        {"id": "lint", "type": "ruff", "args": ["check", "."]},
    ]
    # Apply override logic (same algorithm as loop SKILL step 3.1)
    overrides = chunk.get("gate_overrides") or {}
    merged = []
    for g in gates:
        gate = dict(g)
        ov = overrides.get(gate["id"])
        if ov and "args" in ov:
            gate["args"] = list(ov["args"])
        merged.append(gate)
    assert merged[0]["args"] == ["tests/test_a.py"]  # narrowed
    assert merged[0]["env"] == {"PYTHONPATH": "src"}  # preserved
    assert merged[1]["args"] == ["check", "."]  # lint unchanged
```

- [ ] **Step 12.2: Run — all should pass**

```bash
pytest tests/test_v08_bundle.py -v
```
Expected: 5 passed.

- [ ] **Step 12.3: Full suite**

```bash
pytest -q && ruff check .
```
Expected: ~169 passed, ruff clean.

- [ ] **Step 12.4: Commit**

```bash
git add tests/test_v08_bundle.py
git commit -m "test(v08-bundle): integration test exercising all 5 v0.8 items together"
```

---

## Task 13: Version bump + README + CHANGELOG

**Files:**
- Modify: `.claude-plugin/plugin.json`
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 13.1: Bump plugin.json to 0.8.0**

Edit `.claude-plugin/plugin.json`, change `"version": "0.7.0"` to `"version": "0.8.0"`.

- [ ] **Step 13.2: Add CHANGELOG entry**

Prepend to `CHANGELOG.md` (after the initial header, before the `[0.7.0]` entry):

```markdown
## [0.8.0] — 2026-04-18

### Changed
- `scripts/git_iter_commit.py` now validates iteration JSON against `schemas/iterations.schema.json` before acquiring the commit lock. Records missing required fields (e.g., `gate_report`) or with wrong types (e.g., `iteration: "001"` as string) are refused with exit 2 and a clear error pointing at the bad field.
- `scripts/chunk_topo.py` `plan_waves()` now auto-serializes chunks in the same wave whose `paths:` overlap. When overlap is detected, the wave is split into consecutive sub-waves (alphabetical by `chunk_id` for determinism). Prevents the same-file-same-wave commit cross-contamination observed in the minischeme stress run where `tail-calls` and `error-handling` both modified `evaluator.py`.
- `skills/build/SKILL.md` subagent prompt construction now invokes `scripts/blueprint_slice.py` and passes only the chunk's section + `## Architecture overview` + `## Cross-chunk types` (when present) to each subagent. Replaces v0.2's "passes whole file" punt.
- `skills/loop/SKILL.md` applies `chunk.gate_overrides` when filtering the criteria subset for measurement.
- `skills/plan/SKILL.md` instructs blueprint authors to include a `## Cross-chunk types` section, propose `gate_overrides` per chunk, and avoid same-file chunks in the same wave.

### Added
- `scripts/validate_iteration.py` — iteration JSON schema validator (importable + CLI).
- `scripts/blueprint_slice.py` — chunk-aware blueprint slicer (importable + CLI).
- `chunks.yaml` schema gains optional `gate_overrides:` field per chunk.
- New `tests/test_validate_iteration.py`, `tests/test_blueprint_slice.py`, `tests/test_gate_overrides.py`, `tests/test_v08_bundle.py`. Plus +4 tests to `test_chunk_topo.py`, +3 to `test_schemas.py`, +2 to `test_git_iter_commit.py`. Total new tests: ~20.

### Formally closed (sufficient evidence)
- **Plan refinement mid-build.** Zero evidence across 8 real runs (including the 18-chunk minischeme stress run — canonical case for mid-build IR-shape discovery, did not trigger the need). Roadmap updated to move this from "Deferred" to "Formally closed."

### Backward compatibility
- Existing `criteria.yaml`: unchanged behavior.
- Existing `chunks.yaml` without `gate_overrides`: unchanged.
- Existing `chunks.yaml` without `paths:` or with non-overlapping paths: `chunk_topo` behaves identically to v0.7.
- Existing `blueprint.md` without `## Cross-chunk types`: slicer warns but proceeds.
- Existing `blueprint.md` without `## <chunk_id>` H2 headings (legacy pre-v0.2 projects): slicer falls back to full-blueprint return with warning.
- Existing iteration JSONs that were always schema-valid: continue to pass. Records that were silently-schema-non-conforming (rare; observed once in minischeme stress run's `error-handling-001.json`) will now fail on resume — the migration path is to fix the bad record and re-run.
```

- [ ] **Step 13.3: Add README "What's new in v0.8"**

Insert in `README.md` before the `## What's new in v0.7` section:

```markdown
## What's new in v0.8

Correctness + subagent discipline bundle driven by the `minischeme` 18-chunk stress run:

- **Iteration JSON validated before commit.** `git_iter_commit` now refuses to commit when the iteration record fails `schemas/iterations.schema.json`. Catches the silent-corruption cases where a subagent writes `status`/`gates` instead of `exit_reason`/`gate_report`, or zero-pads the integer `iteration` field. Commit-message-lies-about-status goes away.
- **`chunk_topo` auto-serializes same-file chunks.** Two chunks in the same wave whose `paths:` overlap used to risk one's changes getting committed under the other's chunk message. `plan_waves` now splits overlapping pairs into consecutive sub-waves automatically.
- **Per-chunk `gate_overrides:` in `chunks.yaml`.** Declare per-chunk gate argument narrowing upfront (e.g., `pytest_chunk.args = ["tests/test_<chunk>.py"]`) instead of having every parallel-wave subagent reinvent the defensive pattern. Loop skill applies them when building the criteria subset.
- **Blueprint slicing, finally.** v0.2 punted on this. v0.8 delivers: subagents now receive only their chunk's section + the architecture overview + the new `## Cross-chunk types` section, not the whole blueprint. Kills the "Wave 4 implements Wave 5's code" ahead-of-scope pattern.
- **`## Cross-chunk types` blueprint convention.** Authoritative section declaring types that multiple chunks consume and the canonical module each lives in. Prevents duplicate-singleton planting (parser-side `Nil` and values-side `Nil` turning out to be different objects).

Fully backward-compatible with v0.7. Also: plan-refinement-mid-build is formally closed after 8 runs of zero evidence.
```

- [ ] **Step 13.4: Final check**

```bash
pytest -q && ruff check .
```
Expected: all pass, ruff clean.

- [ ] **Step 13.5: Commit**

```bash
git add .claude-plugin/plugin.json README.md CHANGELOG.md
git commit -m "release: v0.8.0 — Correctness + Subagent Discipline Bundle"
```

---

## Task 14: Update `docs/roadmap.md`

**Files:**
- Modify: `docs/roadmap.md`

- [ ] **Step 14.1: Add v0.8 to Shipped**

Under `## Shipped`, after the v0.7 entry, add:

```markdown
### v0.8 — Correctness + Subagent Discipline Bundle (2026-04-18)
Five items covering 7 findings from the minischeme 18-chunk stress run:
- Iteration JSON schema validation before commit (F5, F9)
- `chunk_topo` auto-serializes same-file chunks in parallel waves (F8)
- `chunks.yaml` gains optional `gate_overrides:` for per-chunk gate arg narrowing (F3, F12)
- Blueprint slicing via `scripts/blueprint_slice.py` — finally, after being deferred since v0.2 (F7)
- `## Cross-chunk types` blueprint convention (F6)
Spec: `docs/superpowers/specs/2026-04-18-skillgoid-v0.8-correctness-and-discipline.md`
Plan: `docs/superpowers/plans/2026-04-18-skillgoid-v0.8.md`
```

- [ ] **Step 14.2: Add "Formally closed" section**

After the existing "Dropped from roadmap" section (or adjacent to it), add:

```markdown
## Formally closed (sufficient evidence)

- **Plan refinement mid-build.** Zero evidence across 8 real runs: jyctl, taskq, mdstats, indexgrep, findings, taskbridge (polyglot), minischeme (18-chunk stress), plus the v0.6 ship-less decision point. The minischeme run was the canonical case where plan refinement "should" have been needed — compiler-style project with mid-build IR-shape discovery — and it wasn't. Not reopening without qualitatively new evidence.
```

- [ ] **Step 14.3: Rename "How to pick up v0.7" → "How to pick up v0.9"**

If `## How to pick up v0.8` currently exists (from v0.7's roadmap update), rename to `## How to pick up v0.9` and prepend:

```markdown
## How to pick up v0.9

Currently deferred v0.8+ items:
- **Polyglot language support** (`languages[]` migration, polyglot clarify defaults, node-gates adapter, multi-language vault/metrics). Waits on 2-3 ORGANIC polyglot runs. `taskbridge` was synthetic; doesn't count. If and when real polyglot-user projects surface, design v0.9 around their shape.
- **F10 (out-of-pipeline commits by subagents fixing adjacent chunks' tests):** one observation in minischeme. Needs 2+ more to justify machinery. Document the pattern but don't formalize yet.
- **F11 (double-commit symptom):** v0.8 schema validation should incidentally address it. If it recurs post-v0.8, investigate separately.
- **Glob-aware paths overlap detection:** v0.8 uses exact-string match. If a user project shows overlapping globs the exact matcher misses, add glob-aware matching in v0.9.
- **Per-chunk blueprint files (alternative to in-memory slicing):** v0.8 went with in-memory. If users want on-disk per-chunk blueprints for audit, revisit.
- **Rehearsal mode, gate-type plugins, dashboards:** unchanged from v0.7's deferred list — no new evidence.

Keep the old v0.7 intake-discipline note below; the philosophy hasn't changed.
```

(Preserve whatever existing v0.7/v0.8 intake prose lives below the heading.)

- [ ] **Step 14.4: Commit**

```bash
git add docs/roadmap.md
git commit -m "docs(roadmap): v0.8 shipped + plan-refinement formally closed + v0.9 intake"
```

---

## Task 15: Manual spot-check against minischeme

**Files:** none modified (verification only)

- [ ] **Step 15.1: Validate minischeme's error-handling iteration JSON with the new validator**

This is the bad record from the stress run (missing `gate_report`).

```bash
. /home/flip/Development/skillgoid/skillgoid-plugin/.venv/bin/activate
python scripts/validate_iteration.py \
  /home/flip/Development/skillgoid-test/minischeme/.skillgoid/iterations/error-handling-001.json
```
Expected: exit 2, stderr naming the missing `gate_report` field. Confirms F9 closes.

- [ ] **Step 15.2: Slice the minischeme blueprint for a chunk**

```bash
python scripts/blueprint_slice.py \
  --blueprint /home/flip/Development/skillgoid-test/minischeme/.skillgoid/blueprint.md \
  --chunk-id parser
```
Expected: stdout contains `## Architecture overview` + `## parser`; stderr warns that `## Cross-chunk types` is absent (minischeme's blueprint doesn't have it). Confirms F7 slicer works on a real blueprint.

- [ ] **Step 15.3: Run chunk_topo against minischeme's chunks.yaml**

```bash
python scripts/chunk_topo.py \
  --chunks-file /home/flip/Development/skillgoid-test/minischeme/.skillgoid/chunks.yaml
```
Expected: JSON wave output. Since minischeme's `tail-calls` and `error-handling` both declared `paths: [src/minischeme/evaluator.py, ...]`, they should now appear in CONSECUTIVE SUB-WAVES, not the same wave 6. Confirms F8 fix applies to the real evidence case.

- [ ] **Step 15.4: No commit — spot check only**

---

## Task 16: Merge feat/v0.8 → main + tag v0.8.0

- [ ] **Step 16.1: Final check**

```bash
cd /home/flip/Development/skillgoid/skillgoid-plugin
pytest -q && ruff check .
git log --oneline main..feat/v0.8 | wc -l
```
Expected: green; ~14 commits on the branch.

- [ ] **Step 16.2: Merge**

```bash
git checkout main
git merge --no-ff feat/v0.8 -m "merge: v0.8 Correctness + Subagent Discipline Bundle"
```

- [ ] **Step 16.3: Tag**

```bash
git tag -a v0.8.0 -m "Skillgoid v0.8.0 — Correctness + Subagent Discipline Bundle"
```

- [ ] **Step 16.4: Verify final state**

```bash
git log --oneline -5
git tag -l "v0.8.0"
```
Expected: merge commit at head; tag v0.8.0 present.

---

## Self-review checklist (done before user review)

- [x] **Spec coverage:** every spec section mapped to tasks.
  - Item 1 (F5+F9): Tasks 2-3
  - Item 2 (F8): Tasks 4-5
  - Item 3 (F3+F12): Tasks 6-7
  - Item 4 (F7): Tasks 8-10
  - Item 5 (F6): Task 11 (+ integration via Task 10's slicer usage)
  - Integration test: Task 12
  - Release mechanics: Tasks 13-14
  - Spot check: Task 15
  - Merge: Task 16
  - Plan-refinement formal closure: Task 14 Step 14.2
- [x] **No placeholders:** no TBDs, TODOs, "similar to task N", etc. Every code step has actual code; every run step has exact commands + expected output.
- [x] **Type/name consistency:** `validate_iteration`, `slice_blueprint`, `plan_waves`, `_split_wave_on_overlap`, `_paths_overlap`, `gate_overrides`, `Cross-chunk types` — all match between tasks and the spec.
- [x] **Every new script has importable + CLI surface** consistent with existing `scripts/*.py` conventions.
- [x] **Every SKILL.md change references the v0.8 finding it addresses** so future retrospect can trace provenance.
- [x] **Back-compat invariants preserved** in each item per spec Section 8: additive fields, graceful fallback warnings, no hard-fail on legacy shapes.
