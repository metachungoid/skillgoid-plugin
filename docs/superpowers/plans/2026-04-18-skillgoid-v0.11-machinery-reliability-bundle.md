# Skillgoid v0.11 — Machinery Reliability Bundle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close two known cracks in the build-loop machinery — F6 (loop subagent can silently skip the iteration JSON write) and H8 (integration retry path never exercised) — by adding a post-dispatch verification script, a deterministic suspect-identification script, a language-agnostic reference fixture, and prose edits to `loop/SKILL.md` and `build/SKILL.md`.

**Architecture:** Two new scripts (`verify_iteration_written.py`, `integration_suspect.py`) each follow the project's existing CLI pattern (argparse, JSON stdout, `main()`/`raise SystemExit(main())`). The verification script delegates schema validation to the existing `scripts/validate_iteration.py`. All deliverables are language-agnostic: they work off the generic `gate_report` and iteration schemas with no assumption about which language adapter is in use.

**Tech Stack:** Python ≥3.11, pytest, pyyaml, jsonschema. All in `[project.optional-dependencies].dev`. No new dependencies.

---

## File map

| Action | Path | What it does |
|---|---|---|
| Create | `scripts/verify_iteration_written.py` | Post-dispatch check: finds latest `<chunk_id>-*.json`, validates JSON + schema, returns structured result |
| Create | `scripts/integration_suspect.py` | Maps failed integration gate output → suspect chunk_id via path substring matching |
| Create | `tests/test_verify_iteration_written.py` | Unit tests for verify script |
| Create | `tests/test_integration_suspect.py` | Unit tests for suspect script |
| Create | `tests/fixtures/integration-retry/project/src/lib_a.sh` | Defines `fn_a` |
| Create | `tests/fixtures/integration-retry/project/src/lib_b.sh` | Defines `fn_b` with deliberate `fn_a_typo` |
| Create | `tests/fixtures/integration-retry/project/integration/check.sh` | Sources both libs and calls them — fails when typo present |
| Create | `tests/fixtures/integration-retry/project/.skillgoid/criteria.yaml` | `run-command`-only gates |
| Create | `tests/fixtures/integration-retry/project/.skillgoid/chunks.yaml` | Two chunks with `paths:` |
| Create | `tests/fixtures/integration-retry/project/.skillgoid/blueprint.md` | Minimal blueprint |
| Create | `tests/fixtures/integration-retry/project/.skillgoid/iterations/lib_a-001.json` | Pre-seeded success record |
| Create | `tests/fixtures/integration-retry/project/.skillgoid/iterations/lib_b-001.json` | Pre-seeded success record |
| Create | `tests/fixtures/integration-retry/project/.skillgoid/integration/1.json` | Pre-seeded failed integration attempt — stderr mentions `src/lib_b.sh` |
| Create | `tests/fixtures/integration-retry/README.md` | Purpose and usage |
| Create | `tests/test_integration_retry_fixture.py` | End-to-end: suspect → fix → verify passes |
| Modify | `skills/loop/SKILL.md` | Terminal-MUST requirement for iteration-file write |
| Modify | `skills/build/SKILL.md` | Two edits: post-dispatch verify step + scripted suspect identification |

---

## Task 1: `verify_iteration_written.py` (TDD)

**Files:**
- Create: `tests/test_verify_iteration_written.py`
- Create: `scripts/verify_iteration_written.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_verify_iteration_written.py`:

```python
"""Tests for scripts/verify_iteration_written.py.

The build orchestrator calls this after every loop subagent returns.
These tests verify it correctly reports ok/missing/invalid states.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.verify_iteration_written import verify

ROOT = Path(__file__).resolve().parents[1]
CLI = [sys.executable, str(ROOT / "scripts" / "verify_iteration_written.py")]


def _make_valid_record(chunk_id: str, iteration: int, exit_reason: str = "success") -> dict:
    return {
        "iteration": iteration,
        "chunk_id": chunk_id,
        "gate_report": {"passed": exit_reason == "success", "results": []},
        "exit_reason": exit_reason,
    }


def _write_iter(iters_dir: Path, filename: str, record: dict) -> Path:
    p = iters_dir / filename
    p.write_text(json.dumps(record))
    return p


def _run_cli(chunk_id: str, skillgoid_dir: Path) -> tuple[int, dict]:
    result = subprocess.run(
        CLI + ["--chunk-id", chunk_id, "--skillgoid-dir", str(skillgoid_dir)],
        capture_output=True, text=True,
    )
    return result.returncode, json.loads(result.stdout.strip())


def test_file_present_and_valid(tmp_path):
    sg = tmp_path / ".skillgoid"
    iters = sg / "iterations"
    iters.mkdir(parents=True)
    _write_iter(iters, "parser-002.json", _make_valid_record("parser", 2))

    code, result = verify("parser", sg)

    assert code == 0
    assert result["ok"] is True
    assert result["iteration_number"] == 2
    assert result["exit_reason"] == "success"
    assert "parser-002.json" in result["latest_iteration"]


def test_file_missing(tmp_path):
    sg = tmp_path / ".skillgoid"
    (sg / "iterations").mkdir(parents=True)

    code, result = verify("parser", sg)

    assert code == 1
    assert result["ok"] is False
    assert "parser" in result["reason"]
    assert "searched_glob" in result


def test_missing_iterations_directory(tmp_path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()  # iterations/ subdirectory does NOT exist

    code, result = verify("parser", sg)

    assert code == 1
    assert result["ok"] is False


def test_multiple_files_picks_latest_by_mtime(tmp_path):
    sg = tmp_path / ".skillgoid"
    iters = sg / "iterations"
    iters.mkdir(parents=True)

    older = _write_iter(iters, "parser-001.json", _make_valid_record("parser", 1))
    newer = _write_iter(iters, "parser-003.json", _make_valid_record("parser", 3))
    # Force older to be 10s in the past
    old_mtime = older.stat().st_mtime - 10
    os.utime(older, (old_mtime, old_mtime))
    # newer has the latest mtime

    code, result = verify("parser", sg)

    assert code == 0
    assert result["ok"] is True
    assert result["iteration_number"] == 3
    assert "parser-003.json" in result["latest_iteration"]


def test_file_invalid_json(tmp_path):
    sg = tmp_path / ".skillgoid"
    iters = sg / "iterations"
    iters.mkdir(parents=True)
    (iters / "parser-001.json").write_text("not valid json {{{")

    code, result = verify("parser", sg)

    assert code == 2
    assert result["ok"] is False
    assert "not valid JSON" in result["reason"]
    assert isinstance(result["errors"], list)


def test_file_fails_schema_validation(tmp_path):
    sg = tmp_path / ".skillgoid"
    iters = sg / "iterations"
    iters.mkdir(parents=True)
    # Missing all required fields: iteration, chunk_id, gate_report
    (iters / "parser-001.json").write_text(json.dumps({"exit_reason": "success"}))

    code, result = verify("parser", sg)

    assert code == 2
    assert result["ok"] is False
    assert "schema validation" in result["reason"]
    assert len(result["errors"]) > 0


def test_cli_interface(tmp_path):
    """CLI wrapper emits JSON to stdout and matches the library function."""
    sg = tmp_path / ".skillgoid"
    iters = sg / "iterations"
    iters.mkdir(parents=True)
    _write_iter(iters, "mylib-001.json", _make_valid_record("mylib", 1))

    exit_code, result = _run_cli("mylib", sg)

    assert exit_code == 0
    assert result["ok"] is True
    assert result["iteration_number"] == 1
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
.venv/bin/pytest tests/test_verify_iteration_written.py -v
```

Expected: 7 failures — `ModuleNotFoundError: No module named 'scripts.verify_iteration_written'`

- [ ] **Step 3: Implement `scripts/verify_iteration_written.py`**

```python
#!/usr/bin/env python3
"""Post-dispatch iteration-file verification.

Called by the build orchestrator (build/SKILL.md) after each loop subagent
returns. Confirms that .skillgoid/iterations/<chunk-id>-*.json exists, parses
as valid JSON, and satisfies the iteration schema.

CLI:
    python scripts/verify_iteration_written.py --chunk-id <id> --skillgoid-dir <path>
    Exit 0: ok (JSON result on stdout)
    Exit 1: file missing
    Exit 2: file present but invalid JSON or schema failure

Library:
    from scripts.verify_iteration_written import verify
    code, result = verify("parser", Path(".skillgoid"))
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow cross-script import when invoked directly as python scripts/verify_iteration_written.py
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.validate_iteration import validate_iteration  # noqa: E402


def verify(chunk_id: str, skillgoid_dir: str | Path) -> tuple[int, dict]:
    """Return (exit_code, result_dict).

    0 = ok, 1 = file missing, 2 = invalid JSON or schema failure.
    """
    iters_dir = Path(skillgoid_dir) / "iterations"
    glob_pattern = f"{chunk_id}-*.json"

    try:
        files = list(iters_dir.glob(glob_pattern))
    except (OSError, FileNotFoundError):
        files = []

    if not files:
        return 1, {
            "ok": False,
            "reason": f"no iteration files found for chunk {chunk_id!r}",
            "searched_glob": str(iters_dir / glob_pattern),
        }

    latest = max(files, key=lambda p: p.stat().st_mtime)

    try:
        record = json.loads(latest.read_text())
    except Exception as exc:
        return 2, {
            "ok": False,
            "reason": "file is not valid JSON",
            "file": str(latest),
            "errors": [str(exc)],
        }

    errors = validate_iteration(record)
    if errors:
        return 2, {
            "ok": False,
            "reason": "iteration file failed schema validation",
            "file": str(latest),
            "errors": errors,
        }

    name = latest.stem  # e.g. "parser-002"
    try:
        iteration_number = int(name.rsplit("-", 1)[-1])
    except (ValueError, IndexError):
        iteration_number = None

    result: dict = {
        "ok": True,
        "latest_iteration": str(latest),
        "exit_reason": record.get("exit_reason") or record.get("status"),
    }
    if iteration_number is not None:
        result["iteration_number"] = iteration_number
    return 0, result


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    ap = argparse.ArgumentParser(
        description="Verify loop subagent wrote its iteration file"
    )
    ap.add_argument("--chunk-id", required=True, help="Chunk ID to check")
    ap.add_argument("--skillgoid-dir", required=True, help="Path to .skillgoid dir")
    args = ap.parse_args(argv)

    code, result = verify(args.chunk_id, args.skillgoid_dir)
    sys.stdout.write(json.dumps(result) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
.venv/bin/pytest tests/test_verify_iteration_written.py -v
```

Expected: 7 passed

- [ ] **Step 5: Lint check**

```bash
.venv/bin/ruff check scripts/verify_iteration_written.py tests/test_verify_iteration_written.py
```

Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add scripts/verify_iteration_written.py tests/test_verify_iteration_written.py
git commit -m "feat(v0.11): verify_iteration_written — post-dispatch iteration-file check"
```

---

## Task 2: `integration_suspect.py` (TDD)

**Files:**
- Create: `tests/test_integration_suspect.py`
- Create: `scripts/integration_suspect.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_integration_suspect.py`:

```python
"""Tests for scripts/integration_suspect.py.

Verifies the deterministic suspect-chunk identification algorithm used by
build/SKILL.md step 4g when integration gates fail.
"""
import json
import subprocess
import sys
from pathlib import Path

import yaml

from scripts.integration_suspect import identify_suspect

ROOT = Path(__file__).resolve().parents[1]
CLI = [sys.executable, str(ROOT / "scripts" / "integration_suspect.py")]


def _attempt(failing_results: list[dict]) -> dict:
    """Wrap gate results in an integration attempt file shape."""
    return {
        "iteration": 1,
        "chunk_id": "__integration__",
        "gate_report": {"passed": False, "results": failing_results},
    }


def _write_attempt(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "attempt.json"
    p.write_text(json.dumps(data))
    return p


def _write_chunks(tmp_path: Path, chunk_defs: list[tuple[str, list[str]]]) -> Path:
    p = tmp_path / "chunks.yaml"
    p.write_text(yaml.dump({
        "chunks": [
            {"id": cid, "gate_ids": ["g"], "description": f"chunk {cid}", "paths": paths}
            for cid, paths in chunk_defs
        ]
    }))
    return p


def test_single_chunk_filename_match(tmp_path):
    attempt = _write_attempt(tmp_path, _attempt([{
        "gate_id": "cli_test", "passed": False,
        "stdout": "", "stderr": "Error in src/parser.py line 42: unexpected token",
    }]))
    chunks = _write_chunks(tmp_path, [("parser", ["src/parser.py"]),
                                       ("formatter", ["src/formatter.py"])])

    result = identify_suspect(attempt, chunks)

    assert result["suspect_chunk_id"] == "parser"
    assert result["confidence"] == "filename-match"
    assert "parser" in result["evidence"]


def test_highest_match_count_wins(tmp_path):
    # lib_a has 2 paths in failing output; lib_b has 1 → lib_a wins on count
    attempt = _write_attempt(tmp_path, _attempt([{
        "gate_id": "integration_gate", "passed": False,
        "stdout": "",
        "stderr": "src/lib_a.sh error; src/lib_a_utils.sh also failed; src/lib_b.sh fine",
    }]))
    chunks = _write_chunks(tmp_path, [
        ("lib_a", ["src/lib_a.sh", "src/lib_a_utils.sh"]),
        ("lib_b", ["src/lib_b.sh"]),
    ])

    result = identify_suspect(attempt, chunks)

    assert result["suspect_chunk_id"] == "lib_a"


def test_tiebreak_by_latest_gate_index(tmp_path):
    # Equal match counts; lib_b's match is in the later-indexed gate
    attempt = _write_attempt(tmp_path, _attempt([
        {"gate_id": "gate_early", "passed": False,
         "stdout": "", "stderr": "src/lib_a.sh failed"},   # index 0
        {"gate_id": "gate_late", "passed": False,
         "stdout": "", "stderr": "src/lib_b.sh failed"},   # index 1
    ]))
    chunks = _write_chunks(tmp_path, [("lib_a", ["src/lib_a.sh"]),
                                       ("lib_b", ["src/lib_b.sh"])])

    result = identify_suspect(attempt, chunks)

    assert result["suspect_chunk_id"] == "lib_b"


def test_tiebreak_by_alphabetical_chunk_id(tmp_path):
    # Equal match counts and same gate index → alphabetical wins
    attempt = _write_attempt(tmp_path, _attempt([{
        "gate_id": "gate", "passed": False,
        "stdout": "", "stderr": "src/alpha.py and src/beta.py both failed",
    }]))
    chunks = _write_chunks(tmp_path, [("alpha_chunk", ["src/alpha.py"]),
                                       ("beta_chunk", ["src/beta.py"])])

    result = identify_suspect(attempt, chunks)

    assert result["suspect_chunk_id"] == "alpha_chunk"


def test_no_match_returns_null(tmp_path):
    attempt = _write_attempt(tmp_path, _attempt([{
        "gate_id": "gate", "passed": False,
        "stdout": "", "stderr": "connection refused at localhost:8080",
    }]))
    chunks = _write_chunks(tmp_path, [("frontend", ["src/frontend.py"]),
                                       ("backend", ["src/backend.py"])])

    result = identify_suspect(attempt, chunks)

    assert result["suspect_chunk_id"] is None
    assert result["confidence"] is None
    assert "no chunk path" in result["evidence"]


def test_no_failing_gates_returns_null(tmp_path):
    attempt = _write_attempt(tmp_path, {
        "iteration": 1, "chunk_id": "__integration__",
        "gate_report": {"passed": True,
                        "results": [{"gate_id": "g", "passed": True, "stderr": "", "stdout": ""}]},
    })
    chunks = _write_chunks(tmp_path, [("lib_a", ["src/lib_a.sh"])])

    result = identify_suspect(attempt, chunks)

    assert result["suspect_chunk_id"] is None


def test_malformed_gate_report_not_an_object(tmp_path):
    # gate_report is a string — identify_suspect should raise, CLI should exit 2
    attempt_path = tmp_path / "attempt.json"
    attempt_path.write_text(json.dumps({
        "iteration": 1, "chunk_id": "__integration__",
        "gate_report": "this is not valid",
    }))
    chunks = _write_chunks(tmp_path, [("lib_a", ["src/lib_a.py"])])

    proc = subprocess.run(
        CLI + ["--gate-report", str(attempt_path), "--chunks", str(chunks)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 2


def test_cli_happy_path(tmp_path):
    """CLI wrapper emits JSON on stdout with correct suspect_chunk_id."""
    attempt = _write_attempt(tmp_path, _attempt([{
        "gate_id": "g", "passed": False, "stdout": "", "stderr": "src/mylib.py crash",
    }]))
    chunks = _write_chunks(tmp_path, [("mylib", ["src/mylib.py"])])

    proc = subprocess.run(
        CLI + ["--gate-report", str(attempt), "--chunks", str(chunks)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0
    data = json.loads(proc.stdout.strip())
    assert data["suspect_chunk_id"] == "mylib"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
.venv/bin/pytest tests/test_integration_suspect.py -v
```

Expected: failures — `ModuleNotFoundError: No module named 'scripts.integration_suspect'`

- [ ] **Step 3: Implement `scripts/integration_suspect.py`**

```python
#!/usr/bin/env python3
"""Identify the suspect chunk from a failed integration gate report.

Called by the build orchestrator (build/SKILL.md step 4g) when integration
gates fail and one chunk needs to be re-dispatched for auto-repair.

Scoring algorithm (deterministic):
1. For each chunk, collect its paths[] entries.
2. For each failing gate result, concatenate stdout + "\\n" + stderr.
3. Count how many of the chunk's paths appear as substrings in that output.
4. Rank by: (a) total matches desc, (b) latest failing-gate index desc,
   (c) alphabetical chunk_id asc.
5. Zero matches across all chunks → suspect_chunk_id: null.

CLI:
    python scripts/integration_suspect.py \\
        --gate-report .skillgoid/integration/1.json \\
        --chunks     .skillgoid/chunks.yaml
    Always exits 0 (result in JSON). Internal errors exit 2.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml


def _get_failing_results(gate_report: dict | list) -> list[dict]:
    if isinstance(gate_report, list):
        results = gate_report
    elif isinstance(gate_report, dict):
        results = gate_report.get("results") or []
    else:
        raise TypeError(
            f"gate_report must be a dict or list, got {type(gate_report).__name__!r}"
        )
    return [r for r in results if not r.get("passed")]


def identify_suspect(gate_report_path: Path, chunks_path: Path) -> dict:
    """Return suspect identification dict. Raises on malformed input."""
    attempt = json.loads(gate_report_path.read_text())
    gate_report = attempt.get("gate_report", attempt)

    failing = _get_failing_results(gate_report)
    if not failing:
        return {
            "suspect_chunk_id": None,
            "confidence": None,
            "evidence": "no failing gates in the report",
        }

    data = yaml.safe_load(chunks_path.read_text())
    chunks = data.get("chunks", [])

    # scores[chunk_id] = (total_matches, latest_gate_index)
    scores: dict[str, tuple[int, int]] = {}
    evidence_map: dict[str, str] = {}

    for chunk in chunks:
        chunk_id = chunk.get("id", "")
        paths = chunk.get("paths") or []
        if not paths:
            continue

        total = 0
        latest_idx = -1
        best_evidence = ""

        for gate_idx, gate in enumerate(failing):
            combined = (gate.get("stdout") or "") + "\n" + (gate.get("stderr") or "")
            for p in paths:
                if p in combined:
                    total += 1
                    if gate_idx > latest_idx:
                        latest_idx = gate_idx
                        gate_id = gate.get("gate_id", "unknown")
                        best_evidence = (
                            f"chunk {chunk_id!r} path {p!r} matched gate {gate_id!r} output"
                        )

        if total > 0:
            scores[chunk_id] = (total, latest_idx)
            evidence_map[chunk_id] = best_evidence

    if not scores:
        return {
            "suspect_chunk_id": None,
            "confidence": None,
            "evidence": "no chunk path appeared in any failed gate's stdout/stderr",
        }

    ranked = sorted(
        scores,
        key=lambda cid: (-scores[cid][0], -scores[cid][1], cid),
    )
    winner = ranked[0]
    return {
        "suspect_chunk_id": winner,
        "confidence": "filename-match",
        "evidence": evidence_map[winner],
    }


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    ap = argparse.ArgumentParser(
        description="Identify suspect chunk from failed integration gate report"
    )
    ap.add_argument("--gate-report", required=True,
                    help="Path to .skillgoid/integration/<attempt>.json")
    ap.add_argument("--chunks", required=True,
                    help="Path to .skillgoid/chunks.yaml")
    args = ap.parse_args(argv)

    try:
        result = identify_suspect(Path(args.gate_report), Path(args.chunks))
    except Exception as exc:
        sys.stderr.write(f"integration_suspect: {exc}\n")
        return 2

    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
.venv/bin/pytest tests/test_integration_suspect.py -v
```

Expected: 8 passed

- [ ] **Step 5: Lint check**

```bash
.venv/bin/ruff check scripts/integration_suspect.py tests/test_integration_suspect.py
```

Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add scripts/integration_suspect.py tests/test_integration_suspect.py
git commit -m "feat(v0.11): integration_suspect — deterministic suspect-chunk identification"
```

---

## Task 3: Integration-retry fixture

**Files:**
- Create: `tests/fixtures/integration-retry/README.md`
- Create: `tests/fixtures/integration-retry/project/src/lib_a.sh`
- Create: `tests/fixtures/integration-retry/project/src/lib_b.sh`
- Create: `tests/fixtures/integration-retry/project/integration/check.sh`
- Create: `tests/fixtures/integration-retry/project/.skillgoid/criteria.yaml`
- Create: `tests/fixtures/integration-retry/project/.skillgoid/chunks.yaml`
- Create: `tests/fixtures/integration-retry/project/.skillgoid/blueprint.md`
- Create: `tests/fixtures/integration-retry/project/.skillgoid/iterations/lib_a-001.json`
- Create: `tests/fixtures/integration-retry/project/.skillgoid/iterations/lib_b-001.json`
- Create: `tests/fixtures/integration-retry/project/.skillgoid/integration/1.json`

- [ ] **Step 1: Create directory tree**

```bash
mkdir -p tests/fixtures/integration-retry/project/src
mkdir -p tests/fixtures/integration-retry/project/integration
mkdir -p tests/fixtures/integration-retry/project/.skillgoid/iterations
mkdir -p tests/fixtures/integration-retry/project/.skillgoid/integration
```

- [ ] **Step 2: Create `tests/fixtures/integration-retry/README.md`**

```markdown
# integration-retry fixture

Language-agnostic reference fixture for Skillgoid's integration-retry path
(build/SKILL.md step 4g, addressed in v0.11).

## What it models

Two bash library chunks (`lib_a`, `lib_b`). Both pass per-chunk syntax-check
gates individually. The integration gate (`bash integration/check.sh`) fails
because `lib_b.sh` contains a deliberate typo: `fn_a_typo` instead of `fn_a`.
The pre-seeded `integration/1.json` records this failure — its stderr mentions
`src/lib_b.sh`, so `integration_suspect.py` correctly identifies `lib_b` as
the suspect chunk.

## Using it in tests

Copy `project/` to `tmp_path`, run `integration_suspect.py` against
`project/.skillgoid/integration/1.json`, assert `suspect_chunk_id == "lib_b"`,
then fix the typo (simulating the loop subagent's retry) and rerun
`bash integration/check.sh` to assert it now passes.

See `tests/test_integration_retry_fixture.py`.

## Why bash / run-command gates

`run-command` is the cross-adapter common denominator: every language adapter
must support it. This fixture validates orchestrator logic without coupling to
any specific language adapter. It works identically once TypeScript or Go
adapters are added in future versions.
```

- [ ] **Step 3: Create `tests/fixtures/integration-retry/project/src/lib_a.sh`**

```bash
#!/usr/bin/env bash
# lib_a: defines fn_a
fn_a() {
    echo "fn_a called"
}
```

- [ ] **Step 4: Create `tests/fixtures/integration-retry/project/src/lib_b.sh`**

```bash
#!/usr/bin/env bash
# lib_b: defines fn_b (calls fn_a — deliberate typo: fn_a_typo)
fn_b() {
    fn_a_typo  # BUG: should be fn_a; fix by replacing fn_a_typo with fn_a
    echo "fn_b called"
}
```

- [ ] **Step 5: Create `tests/fixtures/integration-retry/project/integration/check.sh`**

```bash
#!/usr/bin/env bash
# Integration check: source both libs and invoke fn_a and fn_b.
# Fails when lib_b.sh has the fn_a_typo bug.
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/../src/lib_a.sh"
source "$SCRIPT_DIR/../src/lib_b.sh"
fn_a
fn_b
echo "integration check passed"
```

- [ ] **Step 6: Create `.skillgoid/criteria.yaml`**

```yaml
language: sh
gates:
  - id: syntax_check_lib_a
    type: run-command
    args: ["bash", "-n", "src/lib_a.sh"]
  - id: syntax_check_lib_b
    type: run-command
    args: ["bash", "-n", "src/lib_b.sh"]
integration_gates:
  - id: integration_check
    type: run-command
    args: ["bash", "integration/check.sh"]
integration_retries: 1
```

- [ ] **Step 7: Create `.skillgoid/chunks.yaml`**

```yaml
chunks:
  - id: lib_a
    description: "Defines fn_a — the shared utility function"
    gate_ids: [syntax_check_lib_a]
    paths: [src/lib_a.sh]
  - id: lib_b
    description: "Defines fn_b — depends on fn_a from lib_a"
    gate_ids: [syntax_check_lib_b]
    paths: [src/lib_b.sh]
```

- [ ] **Step 8: Create `.skillgoid/blueprint.md`**

```markdown
# integration-retry fixture blueprint

## Architecture overview

Two-file bash library. `lib_a.sh` provides `fn_a`. `lib_b.sh` provides `fn_b`,
which internally calls `fn_a`. The integration check sources both and calls
both functions.

## lib_a

File: `src/lib_a.sh`
Responsibility: define `fn_a`.

## lib_b

File: `src/lib_b.sh`
Responsibility: define `fn_b`, which calls `fn_a` from lib_a.
```

- [ ] **Step 9: Create pre-seeded iteration records**

`tests/fixtures/integration-retry/project/.skillgoid/iterations/lib_a-001.json`:
```json
{
  "iteration": 1,
  "chunk_id": "lib_a",
  "started_at": "2026-04-18T10:00:00Z",
  "ended_at": "2026-04-18T10:00:01Z",
  "gate_report": {
    "passed": true,
    "results": [
      {"gate_id": "syntax_check_lib_a", "passed": true, "stdout": "", "stderr": "", "hint": ""}
    ]
  },
  "exit_reason": "success",
  "notable": false,
  "reflection": "lib_a.sh passes bash -n syntax check."
}
```

`tests/fixtures/integration-retry/project/.skillgoid/iterations/lib_b-001.json`:
```json
{
  "iteration": 1,
  "chunk_id": "lib_b",
  "started_at": "2026-04-18T10:00:02Z",
  "ended_at": "2026-04-18T10:00:03Z",
  "gate_report": {
    "passed": true,
    "results": [
      {"gate_id": "syntax_check_lib_b", "passed": true, "stdout": "", "stderr": "", "hint": ""}
    ]
  },
  "exit_reason": "success",
  "notable": false,
  "reflection": "lib_b.sh passes bash -n syntax check. The fn_a_typo bug is a runtime error, not a syntax error."
}
```

- [ ] **Step 10: Create pre-seeded failed integration attempt**

`tests/fixtures/integration-retry/project/.skillgoid/integration/1.json`:

The stderr here must contain `src/lib_b.sh` so `integration_suspect.py` identifies `lib_b` as the suspect.

```json
{
  "iteration": 1,
  "chunk_id": "__integration__",
  "started_at": "2026-04-18T10:01:00Z",
  "ended_at": "2026-04-18T10:01:01Z",
  "gate_report": {
    "passed": false,
    "results": [
      {
        "gate_id": "integration_check",
        "passed": false,
        "stdout": "",
        "stderr": "tests/fixtures/integration-retry/project/src/lib_b.sh: line 5: fn_a_typo: command not found",
        "hint": "exit=127, expected 0"
      }
    ]
  }
}
```

**Note:** the stderr path should be relative so it matches `chunks.yaml`'s `paths: [src/lib_b.sh]`. Use just `src/lib_b.sh`:

```json
{
  "iteration": 1,
  "chunk_id": "__integration__",
  "started_at": "2026-04-18T10:01:00Z",
  "ended_at": "2026-04-18T10:01:01Z",
  "gate_report": {
    "passed": false,
    "results": [
      {
        "gate_id": "integration_check",
        "passed": false,
        "stdout": "",
        "stderr": "src/lib_b.sh: line 5: fn_a_typo: command not found",
        "hint": "exit=127, expected 0"
      }
    ]
  }
}
```

- [ ] **Step 11: Verify the fixture runs correctly by hand**

```bash
# Check that lib_a.sh passes syntax check
bash -n tests/fixtures/integration-retry/project/src/lib_a.sh && echo "lib_a: PASS"

# Check that lib_b.sh passes syntax check (fn_a_typo is a runtime error, not syntax)
bash -n tests/fixtures/integration-retry/project/src/lib_b.sh && echo "lib_b syntax: PASS"

# Check that integration/check.sh FAILS (fn_a_typo not defined at runtime)
bash tests/fixtures/integration-retry/project/integration/check.sh && echo "SHOULD NOT REACH HERE" || echo "integration: FAIL (expected)"
```

Expected output:
```
lib_a: PASS
lib_b syntax: PASS
tests/fixtures/integration-retry/project/src/lib_b.sh: line X: fn_a_typo: command not found
integration: FAIL (expected)
```

- [ ] **Step 12: Commit**

```bash
git add tests/fixtures/integration-retry/
git commit -m "feat(v0.11): integration-retry fixture — language-agnostic bash retry demo"
```

---

## Task 4: `test_integration_retry_fixture.py`

**Files:**
- Create: `tests/test_integration_retry_fixture.py`

- [ ] **Step 1: Write the tests**

```python
"""End-to-end integration retry fixture test.

Validates the orchestrator-layer scripts through a realistic failure →
identify suspect → simulate fix → re-run → pass cycle. No real subagent
is invoked: we simulate the loop subagent's retry fix with a Python string
replacement on lib_b.sh.

This is the test for v0.11's H8 coverage: the integration retry path that
was never exercised in the v0.9 chrondel stress run.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "integration-retry"
SUSPECT_CLI = [sys.executable, str(ROOT / "scripts" / "integration_suspect.py")]
VERIFY_CLI = [sys.executable, str(ROOT / "scripts" / "verify_iteration_written.py")]


def test_suspect_identifies_lib_b_from_preseeded_failure(tmp_path):
    """integration_suspect.py names lib_b from the pre-seeded failed integration attempt."""
    project = tmp_path / "project"
    shutil.copytree(FIXTURE_DIR / "project", project)

    proc = subprocess.run(
        SUSPECT_CLI + [
            "--gate-report", str(project / ".skillgoid" / "integration" / "1.json"),
            "--chunks",      str(project / ".skillgoid" / "chunks.yaml"),
        ],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0
    data = json.loads(proc.stdout.strip())
    assert data["suspect_chunk_id"] == "lib_b", (
        f"expected lib_b, got {data['suspect_chunk_id']!r}. evidence: {data.get('evidence')}"
    )
    assert data["confidence"] == "filename-match"


def test_integration_gate_fails_before_fix(tmp_path):
    """integration/check.sh fails when lib_b.sh still contains fn_a_typo."""
    project = tmp_path / "project"
    shutil.copytree(FIXTURE_DIR / "project", project)

    proc = subprocess.run(
        ["bash", "integration/check.sh"],
        capture_output=True, text=True, cwd=project,
    )
    assert proc.returncode != 0, "integration/check.sh should fail before the fix"
    assert "fn_a_typo" in proc.stderr or "lib_b.sh" in proc.stderr, (
        f"expected fn_a_typo or lib_b.sh in stderr, got: {proc.stderr!r}"
    )


def test_integration_gate_passes_after_fix(tmp_path):
    """After fixing the typo (simulating loop subagent retry), check.sh passes."""
    project = tmp_path / "project"
    shutil.copytree(FIXTURE_DIR / "project", project)

    lib_b = project / "src" / "lib_b.sh"
    lib_b.write_text(lib_b.read_text().replace("fn_a_typo", "fn_a"))

    proc = subprocess.run(
        ["bash", "integration/check.sh"],
        capture_output=True, text=True, cwd=project,
    )
    assert proc.returncode == 0, (
        f"integration/check.sh should pass after fix. stderr: {proc.stderr!r}"
    )


def test_verify_confirms_preseeded_iteration_records(tmp_path):
    """verify_iteration_written.py confirms the pre-seeded lib_a and lib_b records are valid."""
    project = tmp_path / "project"
    shutil.copytree(FIXTURE_DIR / "project", project)

    for chunk_id in ("lib_a", "lib_b"):
        proc = subprocess.run(
            VERIFY_CLI + ["--chunk-id", chunk_id,
                          "--skillgoid-dir", str(project / ".skillgoid")],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, (
            f"verify failed for {chunk_id}: {proc.stdout.strip()}"
        )
        data = json.loads(proc.stdout.strip())
        assert data["ok"] is True
        assert data["exit_reason"] == "success"


def test_full_retry_cycle(tmp_path):
    """Full orchestrator contract: identify suspect → fix → integration passes."""
    project = tmp_path / "project"
    shutil.copytree(FIXTURE_DIR / "project", project)

    # Step 1: Integration failed — run suspect identification on pre-seeded report
    proc = subprocess.run(
        SUSPECT_CLI + [
            "--gate-report", str(project / ".skillgoid" / "integration" / "1.json"),
            "--chunks",      str(project / ".skillgoid" / "chunks.yaml"),
        ],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0
    suspect = json.loads(proc.stdout.strip())
    assert suspect["suspect_chunk_id"] == "lib_b"

    # Step 2: "Loop subagent" fixes the suspect chunk (Python string replace = the fix)
    lib_b = project / "src" / "lib_b.sh"
    lib_b.write_text(lib_b.read_text().replace("fn_a_typo", "fn_a"))

    # Step 3: Re-run integration gate — must pass now
    check = subprocess.run(
        ["bash", "integration/check.sh"],
        capture_output=True, text=True, cwd=project,
    )
    assert check.returncode == 0, (
        f"integration/check.sh must pass after lib_b fix. stderr: {check.stderr!r}"
    )
```

- [ ] **Step 2: Run tests to confirm they pass**

```bash
.venv/bin/pytest tests/test_integration_retry_fixture.py -v
```

Expected: 5 passed. (These tests depend on Tasks 1–3 being complete.)

- [ ] **Step 3: Lint check**

```bash
.venv/bin/ruff check tests/test_integration_retry_fixture.py
```

Expected: `All checks passed!`

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration_retry_fixture.py
git commit -m "test(v0.11): end-to-end integration retry fixture — suspect → fix → pass cycle"
```

---

## Task 5: `skills/loop/SKILL.md` — terminal-MUST prose edit

**Files:**
- Modify: `skills/loop/SKILL.md`

The edit goes at line 157 — between step 8.2 (diff summary) and step 9 (exit conditions). The current content at that boundary is:

```
    The output JSON has shape `{files_touched: [...], net_lines: int, diff_summary: str}`. Inject this as the `changes` field when writing `iterations/NNN.json`. If `loop.skip_git == true` or the project isn't a git repo (`diff_summary.py` returns `"git not available"`), omit the `changes` field.

9. **Exit conditions — evaluate in order:**
```

- [ ] **Step 1: Insert the terminal-MUST paragraph**

Open `skills/loop/SKILL.md` and insert the following block between the last sentence of step 8.2 and the heading of step 9:

```
### Terminal requirement — write the iteration file before returning

Your final action before returning from this invocation must be writing `.skillgoid/iterations/<chunk_id>-NNN.json` and confirming the file exists on disk (e.g. `Path(...).exists()`). The build orchestrator invokes `scripts/verify_iteration_written.py` immediately after you return; a missing or schema-invalid file halts the wave and alerts the user.

Never return with the iteration file unwritten — not on success, not on failure, not on stall. If you encounter an error late in the process (gate adapter crash, unexpected state, partial write), write a record with `exit_reason: "stalled"` and as much context as you have before returning. A partial record is recoverable; no record is not.
```

After the insert, step 9 follows immediately (no blank lines required beyond normal markdown spacing).

- [ ] **Step 2: Verify the edit looks right**

```bash
grep -n "Terminal requirement" skills/loop/SKILL.md
grep -n "verify_iteration_written" skills/loop/SKILL.md
```

Expected: both lines found in the file.

- [ ] **Step 3: Commit**

```bash
git add skills/loop/SKILL.md
git commit -m "loop: terminal-MUST for iteration-file write before returning (v0.11)"
```

---

## Task 6: `skills/build/SKILL.md` — two prose edits

**Files:**
- Modify: `skills/build/SKILL.md`

### Edit A: Post-dispatch verify step (between step 3e and step 3f)

The current text around the insertion point (lines 84–86):

```
   3e. Parse each subagent's JSON response and accumulate into orchestration state.

   3f. **Wave gate check**, evaluated after ALL subagents in the wave report:
```

- [ ] **Step 1: Insert the verify step between 3e and 3f**

Insert the following block between step 3e and step 3f (keep the existing blank line between 3e and 3f; insert after 3e's paragraph):

```
   3e-verify. **Verify each dispatched chunk wrote its iteration file.** For every chunk dispatched in this wave (excluding resume-skipped chunks from step 3a), immediately invoke:

      ```bash
      python <plugin-root>/scripts/verify_iteration_written.py \
        --chunk-id <chunk_id> \
        --skillgoid-dir .skillgoid
      ```

      If any invocation exits non-zero, halt the wave **before** the gate check (3f). Surface to the user:
      - Each chunk that failed to produce a valid iteration file
      - The reason from the script's JSON output (`reason` field)
      - The corresponding subagent's final response text (for manual reconstruction)

      Do not proceed to step 3f, subsequent waves, or integration until the iteration file(s) are written or the user intervenes. This is a distinct failure surface from the stall/budget recovery menu in 3f — a missing iteration file means the subagent never declared an `exit_reason` at all.
```

### Edit B: Replace hand-grep prose in step 4g

The current text of the "Identify suspect chunk(s)" bullet in step 4g (line 162):

```
      - **Identify suspect chunk(s).** For each failing gate, grep its `stderr` and `stdout` for filenames that appear in the chunks' blueprint/impl paths. Pick the chunk whose file is most recently mentioned. If no filename match, ask the user which chunk to retry.
```

- [ ] **Step 2: Replace with the scripted version**

Replace that bullet with:

```
      - **Identify suspect chunk.** Invoke:

        ```bash
        python <plugin-root>/scripts/integration_suspect.py \
          --gate-report .skillgoid/integration/<attempt>.json \
          --chunks     .skillgoid/chunks.yaml
        ```

        Parse `suspect_chunk_id` from the stdout JSON. If non-null, proceed to re-dispatch that chunk's loop subagent with the `integration_failure_context` slot populated. If null (no deterministic path match), ask the user which chunk to retry — the script's `evidence` field explains what it searched.
```

- [ ] **Step 3: Verify both edits are present**

```bash
grep -n "verify_iteration_written" skills/build/SKILL.md
grep -n "integration_suspect" skills/build/SKILL.md
```

Expected: both grep lines return matches.

- [ ] **Step 4: Commit**

```bash
git add skills/build/SKILL.md
git commit -m "build: post-dispatch verify step + scripted integration suspect (v0.11)"
```

---

## Task 7: Full suite + tag

**Files:** None (verification only)

- [ ] **Step 1: Run the full test suite**

```bash
.venv/bin/pytest -v
```

Expected: all tests pass, no regressions. Count should be ≥ 171 (the v0.10.0 baseline) plus the new tests from this release.

- [ ] **Step 2: Lint the full codebase**

```bash
.venv/bin/ruff check .
```

Expected: `All checks passed!`

- [ ] **Step 3: Confirm success criteria from spec**

```bash
# 1. integration_suspect tests pass
.venv/bin/pytest tests/test_integration_suspect.py -v

# 2. verify_iteration_written tests pass
.venv/bin/pytest tests/test_verify_iteration_written.py -v

# 3. fixture end-to-end tests pass
.venv/bin/pytest tests/test_integration_retry_fixture.py -v

# 4. prose edits present
grep "verify_iteration_written" skills/build/SKILL.md skills/loop/SKILL.md
grep "integration_suspect" skills/build/SKILL.md
```

- [ ] **Step 4: Tag v0.11.0**

```bash
git tag v0.11.0
```

---

## Self-review

**Spec coverage check:**

| Spec requirement | Task that covers it |
|---|---|
| `scripts/integration_suspect.py` with deterministic scoring | Task 2 |
| `scripts/verify_iteration_written.py` with ok/missing/invalid exits | Task 1 |
| `skills/build/SKILL.md` post-dispatch verify step (Edit A) | Task 6 |
| `skills/build/SKILL.md` integration_suspect.py in step 4g (Edit B) | Task 6 |
| `skills/loop/SKILL.md` terminal-MUST paragraph | Task 5 |
| `tests/fixtures/integration-retry/` fixture structure | Task 3 |
| `tests/test_integration_retry_fixture.py` passing | Task 4 |
| Full test suite passes | Task 7 |
| Lint clean | Task 7 |

**Placeholder scan:** None found.

**Type/name consistency:** `identify_suspect()` used in test import and Task 2 script. `verify()` used in test import and Task 1 script. CLI arg names (`--chunk-id`, `--skillgoid-dir`, `--gate-report`, `--chunks`) consistent across script, test, and fixture test. `suspect_chunk_id` key consistent in all JSON output references.
