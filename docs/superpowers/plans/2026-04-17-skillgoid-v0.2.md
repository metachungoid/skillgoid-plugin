# Skillgoid v0.2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Skillgoid v0.2 — the Production Hardening Bundle. Three structural upgrades that take Skillgoid from "concept ships" to "architecturally credible at real multi-chunk project scale."

**Architecture:** Bundle A (stall+git) adds a deterministic stall-detection helper and per-iteration git commits, wrapped into the existing `loop` skill. Bundle B (integration gate) extends the criteria schema with an optional `integration_gates` array, extends `clarify` to draft one by default, and extends `build` with a post-chunk integration phase that can auto-repair on failure. Bundle C (subagent dispatch) rewrites `build` so each chunk runs in a fresh subagent (via the `Agent` tool) with curated context — main session becomes a pure dispatcher.

**Tech Stack:** Python 3.11+ (pytest, jsonschema, pyyaml), bash (hooks), Claude Code skills (markdown + YAML frontmatter), `Agent` tool for subagent dispatch. No new runtime dependencies beyond v0's stack.

**Backward compatibility:** Fully additive. v0 `criteria.yaml` / `chunks.yaml` / iteration records parse unchanged. New fields (`integration_gates`, `integration_retries`, `loop.skip_git`, `failure_signature`) are optional.

**Spec:** `docs/superpowers/specs/2026-04-17-skillgoid-v0.2-production-hardening.md` (commit `f60057f`).
**Roadmap (v0.3 items deferred):** `docs/roadmap.md`.

---

## Repo layout changes

```
skillgoid-plugin/
├── scripts/
│   ├── measure_python.py          # unchanged in v0.2
│   ├── stall_check.py             # NEW
│   └── git_iter_commit.py         # NEW
├── schemas/
│   ├── criteria.schema.json       # MODIFIED (integration_gates, retries, skip_git)
│   ├── chunks.schema.json         # unchanged
│   └── iterations.schema.json     # NEW (locks iteration JSON shape)
├── skills/
│   ├── build/SKILL.md             # REWRITTEN (subagent dispatch + integration phase)
│   ├── loop/SKILL.md              # MODIFIED (stall sig + git commit per iteration)
│   ├── clarify/SKILL.md           # MODIFIED (draft default integration gate)
│   ├── plan/SKILL.md              # MODIFIED (require per-module headings in blueprint)
│   └── (python-gates, retrieve, retrospect — unchanged)
├── tests/
│   ├── test_stall_check.py        # NEW
│   ├── test_git_iter_commit.py    # NEW
│   ├── test_schemas.py            # MODIFIED (new fields)
│   ├── test_integration.py        # MODIFIED (integration-gate flow)
│   └── test_integration_gate_flow.py   # NEW (end-to-end flow test)
├── docs/
│   ├── roadmap.md                 # unchanged
│   └── CHANGELOG.md               # NEW (v0.2 release notes)
└── README.md                      # MODIFIED (v0.2 feature summary)
```

---

## Task 1: Branch setup

**Files:** no file changes — purely git housekeeping.

- [ ] **Step 1.1: Verify current baseline**

Run: `cd /home/flip/Development/skillgoid/skillgoid-plugin && . .venv/bin/activate && pytest -v && ruff check .`
Expected: `28 passed` and `All checks passed!`. Clean tree.

- [ ] **Step 1.2: Merge v0 to main**

```bash
git checkout main
git merge --ff-only feat/v0-implementation
```

Expected: fast-forward (main is at `fb5c119`, feat branch has 25+ commits ahead).
If it fails as non-ff, stop — something has diverged. Report BLOCKED.

- [ ] **Step 1.3: Create v0.2 branch**

```bash
git checkout -b feat/v0.2
git branch -d feat/v0-implementation
pytest -v && ruff check .
```

Expected: 28 tests pass, ruff clean. `feat/v0-implementation` deleted; `feat/v0.2` is current.

- [ ] **Step 1.4: Confirm no commit needed** — this task produced no file changes. Just verify branch state.

```bash
git status  # should be clean
git log --oneline -3  # should show HEAD == main == latest v0 commit
```

---

## Task 2: `scripts/stall_check.py` + tests

**Files:**
- Create: `scripts/stall_check.py`
- Create: `tests/test_stall_check.py`

- [ ] **Step 2.1: Write failing tests first — `tests/test_stall_check.py`**

```python
"""Tests for the deterministic stall signature helper.

A stall signature is a 16-char hex derived from the failing gate IDs + the
first 200 chars of each failing gate's stderr. Two iterations with identical
failure payloads must produce identical signatures; any difference in failing
IDs or stderr prefix must change the signature.
"""
import json
import subprocess
import sys
from pathlib import Path

from scripts.stall_check import signature

ROOT = Path(__file__).resolve().parents[1]
CLI = [sys.executable, str(ROOT / "scripts" / "stall_check.py")]


def _record(**gate_results) -> dict:
    return {
        "iteration": 1,
        "gate_report": {
            "passed": all(r["passed"] for r in gate_results.values()),
            "results": [
                {"gate_id": gid, **r}
                for gid, r in gate_results.items()
            ],
        },
    }


def test_identical_failures_produce_identical_signatures():
    rec_a = _record(pytest={"passed": False, "stdout": "", "stderr": "E assert 1==2"})
    rec_b = _record(pytest={"passed": False, "stdout": "", "stderr": "E assert 1==2"})
    assert signature(rec_a) == signature(rec_b)


def test_different_failing_gates_produce_different_signatures():
    rec_a = _record(pytest={"passed": False, "stdout": "", "stderr": "e"})
    rec_b = _record(ruff={"passed": False, "stdout": "", "stderr": "e"})
    assert signature(rec_a) != signature(rec_b)


def test_different_stderr_prefix_produces_different_signatures():
    rec_a = _record(pytest={"passed": False, "stdout": "", "stderr": "E foo"})
    rec_b = _record(pytest={"passed": False, "stdout": "", "stderr": "E bar"})
    assert signature(rec_a) != signature(rec_b)


def test_passing_gates_do_not_contribute_to_signature():
    rec_failing = _record(pytest={"passed": False, "stdout": "", "stderr": "E"})
    rec_failing_plus_passing = _record(
        pytest={"passed": False, "stdout": "", "stderr": "E"},
        ruff={"passed": True, "stdout": "ok", "stderr": ""},
    )
    # Adding a passing gate shouldn't change the signature
    assert signature(rec_failing) == signature(rec_failing_plus_passing)


def test_stderr_beyond_200_chars_does_not_change_signature():
    short = _record(pytest={"passed": False, "stdout": "", "stderr": "X" * 200})
    long = _record(pytest={"passed": False, "stdout": "", "stderr": "X" * 200 + "Y" * 500})
    assert signature(short) == signature(long)


def test_cli_prints_signature_to_stdout(tmp_path: Path):
    rec = _record(pytest={"passed": False, "stdout": "", "stderr": "E assert"})
    iter_file = tmp_path / "001.json"
    iter_file.write_text(json.dumps(rec))

    result = subprocess.run(
        CLI + [str(iter_file)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0
    sig = result.stdout.strip()
    assert len(sig) == 16
    assert all(c in "0123456789abcdef" for c in sig)
    assert sig == signature(rec)


def test_signature_is_16_hex_chars():
    rec = _record(pytest={"passed": False, "stdout": "", "stderr": ""})
    sig = signature(rec)
    assert len(sig) == 16
    assert all(c in "0123456789abcdef" for c in sig)
```

- [ ] **Step 2.2: Run test — confirm failure**

Run: `. .venv/bin/activate && pytest tests/test_stall_check.py -v`
Expected: FAIL — module `scripts.stall_check` not found.

- [ ] **Step 2.3: Implement `scripts/stall_check.py`**

```python
#!/usr/bin/env python3
"""Deterministic stall-detection signature helper.

Loops need a reliable way to detect "same failure, same root cause" across
iterations so they can exit on stall rather than burn the whole loop budget
on an unsolvable problem. Claude-judged comparisons are fragile; a hash
is not.

Signature contract:
    sha256 of  f"{sorted_failing_gate_ids}::{concatenated_stderr_prefixes}"
    truncated to 16 hex chars.

Only failing gates contribute. Only the first 200 chars of each failing
gate's stderr contribute. Timestamps, absolute paths beyond 200 chars, and
any other noise are excluded — same root cause -> same signature.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


STDERR_PREFIX_BYTES = 200
SIGNATURE_LEN = 16


def signature(record: dict) -> str:
    """Compute the deterministic stall signature for an iteration record."""
    report = record.get("gate_report") or {}
    results = report.get("results") or []
    failing = [r for r in results if not r.get("passed")]

    failing_ids = sorted(r.get("gate_id", "") for r in failing)
    stderr_blob = "".join(
        (r.get("stderr") or "")[:STDERR_PREFIX_BYTES] for r in failing
    )
    payload = f"{failing_ids}::{stderr_blob}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:SIGNATURE_LEN]


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 1:
        sys.stderr.write("usage: stall_check.py <iteration.json>\n")
        return 2
    path = Path(argv[0])
    try:
        record = json.loads(path.read_text())
    except Exception as exc:
        sys.stderr.write(f"stall_check: {exc}\n")
        return 2
    print(signature(record))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2.4: Run tests — confirm pass**

Run: `pytest tests/test_stall_check.py -v`
Expected: 7 tests pass.

- [ ] **Step 2.5: Full test + lint**

Run: `pytest -v && ruff check .`
Expected: 35 total (28 + 7), ruff clean.

- [ ] **Step 2.6: Commit**

```bash
git add scripts/stall_check.py tests/test_stall_check.py
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "feat(stall): deterministic stall signature helper

Hashes sorted failing gate IDs + first 200 chars of each failing
gate's stderr to produce a 16-hex-char signature. Two iterations
with the same failure payload produce the same signature,
eliminating Claude-judged comparisons for stall detection."
```

---

## Task 3: `scripts/git_iter_commit.py` + tests

A small helper called by the `loop` skill after each iteration. Takes the iteration record path and a chunk id, makes a `git commit` with a structured message, and is safe on non-git projects (no-op) and on repos with no changes (`--allow-empty`).

**Files:**
- Create: `scripts/git_iter_commit.py`
- Create: `tests/test_git_iter_commit.py`

- [ ] **Step 3.1: Write failing tests — `tests/test_git_iter_commit.py`**

```python
"""Tests for the git-per-iteration commit helper.

Contract: given a project path, chunk id, and iteration record, the
helper commits any pending changes with a structured message. Noops
cleanly on non-git projects. Tolerates zero-diff iterations via
--allow-empty. Never crashes the loop on a git error.
"""
import json
import subprocess
import sys
from pathlib import Path

from scripts.git_iter_commit import commit_iteration, is_git_repo

ROOT = Path(__file__).resolve().parents[1]
CLI = [sys.executable, str(ROOT / "scripts" / "git_iter_commit.py")]


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit",
                    "--allow-empty", "-q", "-m", "init"], cwd=path, check=True)


def _record(iteration: int, chunk_id: str, failing: bool, signature: str = "abc1234567890def") -> dict:
    return {
        "iteration": iteration,
        "chunk_id": chunk_id,
        "gate_report": {
            "passed": not failing,
            "results": [
                {"gate_id": "pytest", "passed": not failing, "stdout": "", "stderr": "E" if failing else "", "hint": ""}
            ],
        },
        "failure_signature": signature,
        "exit_reason": "in_progress",
    }


def test_is_git_repo_true(tmp_path: Path):
    _init_repo(tmp_path)
    assert is_git_repo(tmp_path) is True


def test_is_git_repo_false(tmp_path: Path):
    # tmp_path is not a git repo by default
    assert is_git_repo(tmp_path) is False


def test_commit_noop_on_non_git_project(tmp_path: Path):
    # Not a git repo — helper should return False (noop) without raising.
    record = _record(1, "core-api", failing=True)
    result = commit_iteration(tmp_path, record)
    assert result is False


def test_commit_with_diff_creates_commit(tmp_path: Path):
    _init_repo(tmp_path)
    (tmp_path / "foo.py").write_text("print(1)\n")
    record = _record(1, "core-api", failing=True)
    result = commit_iteration(tmp_path, record)
    assert result is True

    log = subprocess.run(
        ["git", "log", "--oneline", "-1"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout
    assert "skillgoid:" in log.lower()
    assert "core-api" in log
    assert "iter 1" in log or "iteration 1" in log


def test_commit_zero_diff_uses_allow_empty(tmp_path: Path):
    _init_repo(tmp_path)
    # No file changes since init commit
    record = _record(1, "core-api", failing=True)
    result = commit_iteration(tmp_path, record)
    assert result is True

    count = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert count == "2"  # init + our iteration commit


def test_commit_message_includes_signature_and_gate_summary(tmp_path: Path):
    _init_repo(tmp_path)
    (tmp_path / "foo.py").write_text("x = 1\n")
    record = _record(2, "core-api", failing=True, signature="feedfacecafebabe")
    commit_iteration(tmp_path, record)

    log = subprocess.run(
        ["git", "log", "-1", "--pretty=%B"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout
    assert "feedfacecafebabe" in log
    assert "pytest" in log.lower()


def test_cli_works(tmp_path: Path):
    _init_repo(tmp_path)
    (tmp_path / "foo.py").write_text("y = 2\n")
    iter_file = tmp_path / "001.json"
    iter_file.write_text(json.dumps(_record(1, "demo", failing=True)))

    result = subprocess.run(
        CLI + ["--project", str(tmp_path), "--iteration", str(iter_file)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    # Commit landed
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout
    assert len(log.strip().split("\n")) == 2  # init + iteration commit


def test_cli_noop_on_non_git_exits_zero(tmp_path: Path):
    iter_file = tmp_path / "001.json"
    iter_file.write_text(json.dumps(_record(1, "demo", failing=True)))
    result = subprocess.run(
        CLI + ["--project", str(tmp_path), "--iteration", str(iter_file)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
```

- [ ] **Step 3.2: Run — confirm failure**

Run: `pytest tests/test_git_iter_commit.py -v`
Expected: all FAIL — module not found.

- [ ] **Step 3.3: Implement `scripts/git_iter_commit.py`**

```python
#!/usr/bin/env python3
"""Git-per-iteration commit helper.

Called by the `loop` skill after writing each iteration record. Makes a
structured git commit of any pending changes so users get free rollback
targets per iteration and a clean audit trail of loop work.

Contract:
- On non-git projects: noop (return False, exit 0).
- On git projects: stage all changes and commit with a structured message
  (uses --allow-empty so zero-diff iterations still produce a commit).
- On any git error: log to stderr and return False — never crash the loop.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def is_git_repo(project: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=project,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


def _build_message(record: dict) -> str:
    chunk_id = record.get("chunk_id", "?")
    iteration = record.get("iteration", "?")
    signature = record.get("failure_signature", "unknown")
    report = record.get("gate_report") or {}
    passed = report.get("passed")
    status = "passed" if passed else ("failing" if passed is False else "in-progress")
    exit_reason = record.get("exit_reason", "in_progress")

    gate_summary_parts = []
    for r in (report.get("results") or []):
        gid = r.get("gate_id", "?")
        ok = "pass" if r.get("passed") else "fail"
        gate_summary_parts.append(f"{gid} ({ok})")
    gate_line = ", ".join(gate_summary_parts) if gate_summary_parts else "no gates"

    return (
        f"skillgoid: iter {iteration} of chunk {chunk_id} ({status})\n\n"
        f"Gates: {gate_line}\n"
        f"Signature: {signature}\n"
        f"Exit: {exit_reason}"
    )


def commit_iteration(project: Path, record: dict) -> bool:
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Skillgoid git-per-iteration commit helper")
    ap.add_argument("--project", required=True, type=Path)
    ap.add_argument("--iteration", required=True, type=Path)
    args = ap.parse_args(argv)

    try:
        record = json.loads(args.iteration.read_text())
    except Exception as exc:
        sys.stderr.write(f"git_iter_commit: cannot read iteration file: {exc}\n")
        return 0  # soft-fail: never block the loop

    commit_iteration(args.project.resolve(), record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3.4: Run tests — confirm pass**

Run: `pytest tests/test_git_iter_commit.py -v`
Expected: 8 tests pass.

- [ ] **Step 3.5: Full test + lint**

Run: `pytest -v && ruff check .`
Expected: 43 total (35 + 8), ruff clean.

- [ ] **Step 3.6: Commit**

```bash
git add scripts/git_iter_commit.py tests/test_git_iter_commit.py
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "feat(git): per-iteration commit helper

Commits any pending changes in the target project after each loop
iteration with a structured 'skillgoid:' message containing chunk id,
iteration number, gate pass/fail summary, signature, and exit reason.
Noops silently on non-git projects, uses --allow-empty for zero-diff
iterations, and never crashes the loop on a git error."
```

---

## Task 4: `loop` skill update — call stall + git helpers

**Files:**
- Modify: `skills/loop/SKILL.md`

- [ ] **Step 4.1: Read the current file**

Current `loop` SKILL.md was written in v0. We're appending two sub-steps to the Reflect step (step 8 in the v0 procedure) and adding a new configuration note about `loop.skip_git`.

- [ ] **Step 4.2: Replace step 8 ("Reflect") and add step 8.1 ("Git commit")**

Open `skills/loop/SKILL.md` and locate the "Loop (iteration N = 1, 2, 3, ...)" section. Replace the existing step 8 with:

```markdown
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
     "failure_signature": "<computed via scripts/stall_check.py>",
     "exit_reason": "in_progress"
   }
   ```
   Mark `notable: true` when the reflection surfaces a non-obvious lesson (unexpected tool behavior, surprising library edge case, a design decision that changed the plan). Boring iterations stay `notable: false`.

   After writing the file, compute and persist the stall signature by running:
   ```bash
   SIG=$(python <plugin-root>/scripts/stall_check.py .skillgoid/iterations/NNN.json)
   # Update the file's failure_signature field to $SIG (re-serialize the JSON).
   ```

8.1. **Git commit step.** Run:
   ```bash
   python <plugin-root>/scripts/git_iter_commit.py --project <project_path> --iteration .skillgoid/iterations/NNN.json
   ```
   This commits the iteration's changes with a structured message. On non-git projects it silently noops. Skip this step entirely if `criteria.yaml → loop.skip_git == true`.
```

And update step 9 to use the signature-based stall check:

```markdown
9. **Exit conditions — evaluate in order:**
   - **Success:** `gate_report.passed == true` for all *structured* gates. (Acceptance scenarios from §7 are soft — they inform test-writing during the loop but do not block exit.) Write a final iteration record with `exit_reason: "success"` and return.
   - **Budget exhausted:** `N >= max_attempts`. Write `exit_reason: "budget_exhausted"` and return with failure.
   - **No-progress stall:** the current iteration's `failure_signature` exactly equals the previous iteration's `failure_signature`. (Use `scripts/stall_check.py` — never rely on judgment.) Write `exit_reason: "stalled"`, surface a summary to the user, and return with failure.
   - **Otherwise:** increment N and continue the loop.
```

Also add a "Configuration" note right after the "Procedure" intro:

```markdown
## Configuration notes

- `criteria.yaml → loop.max_attempts` — maximum iterations per chunk (default 5).
- `criteria.yaml → loop.skip_git` — set to `true` to disable git-per-iteration commits in this project (default `false`). Useful for projects that have strict commit-message conventions.
```

- [ ] **Step 4.3: Verify YAML frontmatter still parses**

Run: `python -c "import yaml; f=open('skills/loop/SKILL.md'); lines=f.read().split('---', 2); print(yaml.safe_load(lines[1]))"`
Expected: prints `{'name': 'loop', 'description': '...'}`.

- [ ] **Step 4.4: Commit**

```bash
git add skills/loop/SKILL.md
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "feat(loop): deterministic stall signature + git-per-iteration

Updates the loop skill procedure: after writing each iterations/NNN.json,
compute the stall signature via scripts/stall_check.py and commit the
iteration's changes via scripts/git_iter_commit.py. Stall exit condition
is now signature-based (deterministic), not Claude-judged.

New config: criteria.yaml → loop.skip_git (default false) opts out of
the git commits."
```

---

## Task 5: Schema updates + new iteration JSON schema

**Files:**
- Modify: `schemas/criteria.schema.json`
- Create: `schemas/iterations.schema.json`
- Modify: `tests/test_schemas.py`

- [ ] **Step 5.1: Modify `schemas/criteria.schema.json`**

Replace the entire file contents with:

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
        "max_attempts": {"type": "integer", "minimum": 1, "default": 5},
        "skip_git": {"type": "boolean", "default": false, "description": "If true, skip git-per-iteration commits"}
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
    "integration_gates": {
      "type": "array",
      "description": "Optional gates run once after ALL chunk gates pass. Same shape as gates[] items. Catches green-gates-broken-product failures.",
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
    "integration_retries": {
      "type": "integer",
      "minimum": 0,
      "default": 2,
      "description": "Number of auto-repair retries if integration_gates fail. After exhaustion, surface to user."
    },
    "acceptance": {
      "type": "array",
      "items": {"type": "string"}
    }
  }
}
```

- [ ] **Step 5.2: Create `schemas/iterations.schema.json`**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Skillgoid .skillgoid/iterations/NNN.json",
  "type": "object",
  "required": ["iteration", "chunk_id", "gate_report"],
  "properties": {
    "iteration": {"type": "integer", "minimum": 1},
    "chunk_id": {"type": "string"},
    "started_at": {"type": "string"},
    "ended_at": {"type": "string"},
    "gates_run": {"type": "array", "items": {"type": "string"}},
    "gate_report": {
      "type": "object",
      "required": ["passed", "results"],
      "properties": {
        "passed": {"type": "boolean"},
        "results": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["gate_id", "passed"],
            "properties": {
              "gate_id": {"type": "string"},
              "passed": {"type": "boolean"},
              "stdout": {"type": "string"},
              "stderr": {"type": "string"},
              "hint": {"type": "string"}
            },
            "additionalProperties": true
          }
        },
        "error": {"type": "string"}
      },
      "additionalProperties": true
    },
    "reflection": {"type": "string"},
    "notable": {"type": "boolean", "default": false},
    "failure_signature": {
      "type": "string",
      "pattern": "^[0-9a-f]{16}$",
      "description": "16-char hex signature from scripts/stall_check.py"
    },
    "exit_reason": {
      "type": "string",
      "enum": ["in_progress", "success", "budget_exhausted", "stalled"]
    }
  },
  "additionalProperties": true
}
```

- [ ] **Step 5.3: Extend `tests/test_schemas.py` — add new tests at the end of the file**

Append:

```python
# ----- v0.2 additions -----

def test_criteria_with_integration_gates_passes():
    data = {
        "gates": [{"id": "p", "type": "pytest"}],
        "integration_gates": [
            {"id": "smoke", "type": "cli-command-runs", "command": ["myapp", "--help"]},
        ],
        "integration_retries": 2,
    }
    errors = list(_validator("criteria.schema.json").iter_errors(data))
    assert errors == []


def test_criteria_integration_gates_enforces_enum():
    data = {
        "gates": [{"id": "p", "type": "pytest"}],
        "integration_gates": [{"id": "x", "type": "nonsense"}],
    }
    errors = list(_validator("criteria.schema.json").iter_errors(data))
    assert any(e.validator == "enum" for e in errors)


def test_criteria_loop_skip_git_is_boolean():
    data = {"gates": [{"id": "p", "type": "pytest"}], "loop": {"skip_git": "yes"}}
    errors = list(_validator("criteria.schema.json").iter_errors(data))
    assert any("boolean" in str(e.message) or e.validator == "type" for e in errors)


def test_criteria_integration_retries_must_be_non_negative():
    data = {"gates": [{"id": "p", "type": "pytest"}], "integration_retries": -1}
    errors = list(_validator("criteria.schema.json").iter_errors(data))
    assert any(e.validator == "minimum" for e in errors)


def test_iterations_schema_validates_complete_record():
    record = {
        "iteration": 3,
        "chunk_id": "core-api",
        "gate_report": {
            "passed": False,
            "results": [
                {"gate_id": "pytest", "passed": False, "stdout": "", "stderr": "E", "hint": "fix"},
            ],
        },
        "failure_signature": "0123456789abcdef",
        "exit_reason": "in_progress",
    }
    errors = list(_validator("iterations.schema.json").iter_errors(record))
    assert errors == []


def test_iterations_schema_rejects_bad_signature_format():
    record = {
        "iteration": 1,
        "chunk_id": "x",
        "gate_report": {"passed": True, "results": []},
        "failure_signature": "NOT-HEX",
    }
    errors = list(_validator("iterations.schema.json").iter_errors(record))
    assert any(e.validator == "pattern" for e in errors)


def test_iterations_schema_rejects_unknown_exit_reason():
    record = {
        "iteration": 1,
        "chunk_id": "x",
        "gate_report": {"passed": True, "results": []},
        "exit_reason": "exploded",
    }
    errors = list(_validator("iterations.schema.json").iter_errors(record))
    assert any(e.validator == "enum" for e in errors)
```

- [ ] **Step 5.4: Run tests — confirm pass**

Run: `pytest tests/test_schemas.py -v`
Expected: 14 tests pass (previous 7 + new 7).

- [ ] **Step 5.5: Full test + lint**

Run: `pytest -v && ruff check .`
Expected: 50 total, ruff clean.

- [ ] **Step 5.6: Commit**

```bash
git add schemas/ tests/test_schemas.py
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "feat(schema): integration_gates, skip_git, iterations.schema.json

criteria.yaml gains optional integration_gates (list, same shape as
gates[]), integration_retries (default 2), loop.skip_git (default false).
All additions backward-compatible — v0 files validate unchanged.

New iterations.schema.json locks the shape of .skillgoid/iterations/*.json
including failure_signature (16-hex regex) and exit_reason enum."
```

---

## Task 6: `clarify` skill — draft default integration gate

**Files:**
- Modify: `skills/clarify/SKILL.md`

- [ ] **Step 6.1: Update the clarify procedure**

In `skills/clarify/SKILL.md`, modify step 5 (Draft `criteria.yaml`) to add an `integration_gates:` section, and add a new step 5.1 describing which default gate to propose.

Replace the existing step 5 with:

```markdown
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
   - **Service:** if the user can describe a start/health-check/shutdown sequence, generate a `run-command` that does all three. Otherwise leave `integration_gates` empty and note that one should be added by hand.
   - **Unknown or ambiguous:** leave `integration_gates` empty; the user can add one later.
```

- [ ] **Step 6.2: Verify frontmatter still parses**

Run: `python -c "import yaml; f=open('skills/clarify/SKILL.md'); lines=f.read().split('---', 2); print(yaml.safe_load(lines[1]))"`
Expected: prints the skill name + description.

- [ ] **Step 6.3: Commit**

```bash
git add skills/clarify/SKILL.md
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "feat(clarify): propose default integration_gates by project type

CLI → cli-command-runs on --help. Library → import-clean. Service →
start/health/shutdown run-command if describable. Unknown → leave empty.

Prevents the 'green-gates-broken-product' failure mode by making
integration checks on by default rather than opt-in."
```

---

## Task 7: `build` skill — subagent-per-chunk dispatch

**Files:**
- Modify: `skills/build/SKILL.md`

This rewrites the build orchestrator to dispatch each chunk via the `Agent` tool rather than invoking `skillgoid:loop` inline. Integration orchestration is added in Task 8.

- [ ] **Step 7.1: Replace the procedure section of `skills/build/SKILL.md`**

Open `skills/build/SKILL.md`. Replace the entire "Procedure" section with:

```markdown
## Procedure

### Detection

1. **Detect state** by inspecting the current working directory:
   - `.skillgoid/` exists? Parse `chunks.yaml` and `iterations/` to determine which chunks have exited successfully (look for the most recent iteration per chunk and its `exit_reason`).
   - No `.skillgoid/`? Fresh start.

### Dispatch — Fresh start (rough_goal required)

2. **Main-session prep (in-process, this skill invokes them directly):**
   - Invoke `skillgoid:retrieve` with `rough_goal`. Capture the returned summary — call it `retrieve_summary`.
   - Invoke `skillgoid:clarify`. Reads/writes `.skillgoid/goal.md` + `.skillgoid/criteria.yaml`.
   - Invoke `skillgoid:plan`. Reads/writes `.skillgoid/blueprint.md` + `.skillgoid/chunks.yaml`.

3. **Per-chunk dispatch loop.** For each chunk in `chunks.yaml` in order:

   3a. Check dependencies (`chunk.depends_on`). If any listed chunk has not yet exited with `success`, skip this chunk for now (dependency ordering is already enforced by `plan`, so this is a safety check).

   3b. Build the subagent prompt with a curated context slice:
      - The chunk entry as YAML (id, description, gate_ids, language, depends_on)
      - `retrieve_summary` verbatim
      - `blueprint.md` in full (v0.2 punts on blueprint slicing — passes whole file)
      - Any existing `.skillgoid/iterations/*.json` records for this chunk (if resuming; up to last 2)

   3c. Dispatch via the `Agent` tool:
      ```
      Agent(
        subagent_type="general-purpose",
        model="sonnet",
        description="Execute Skillgoid chunk <chunk_id>",
        prompt=<curated prompt — see template below>,
      )
      ```

      **Subagent prompt template:**
      ```
      You are executing one chunk of a Skillgoid build loop.

      ## Your task
      Invoke `skillgoid:loop` for chunk_id="<chunk_id>". When it returns,
      report the structured summary back to me. Do NOT invoke retrospect —
      the orchestrator handles that.

      ## Chunk spec (from .skillgoid/chunks.yaml)
      ```yaml
      <chunk entry as YAML>
      ```

      ## Retrieved past lessons
      <retrieve_summary>

      ## Blueprint
      <contents of .skillgoid/blueprint.md>

      ## Prior iterations for this chunk (if any)
      <contents of up to 2 most recent iterations/*.json filtered to chunk_id==this chunk>

      ## Return format
      Return a JSON object on your final message (just JSON, no prose):
      {
        "exit_reason": "success" | "budget_exhausted" | "stalled",
        "iterations_used": <int>,
        "final_gate_report": { ... verbatim gate_report ... },
        "notes": "<1–3 sentences, any notable observations for retrospect>"
      }
      ```

   3d. Parse the subagent's JSON response. Accumulate summary in an in-memory orchestration state dict (you don't need to persist it — `.skillgoid/iterations/` already has the ground truth).

   3e. Gate check:
      - If `exit_reason == "success"`: continue to next chunk.
      - If `exit_reason` is `"budget_exhausted"` or `"stalled"`: STOP. Do NOT dispatch subsequent chunks. Surface the failure and the summary to the user. The user decides whether to retry (run `/skillgoid:build resume`) or break out (`/skillgoid:build retrospect-only`).

4. **When all chunks have succeeded**, proceed to the integration gate phase (see Task 8 — added in the next commit).

### Dispatch — Resume (`subcommand == "resume"` or default when `.skillgoid/` exists)

5. Report current state: "On chunk X of N. Chunk X last exited: <success | stalled | budget_exhausted | in-progress>."

6. Continue the per-chunk dispatch loop (step 3) starting with the first chunk that has NOT yet exited `success`.

### Dispatch — Status only

7. Print chunk summary: which chunks have passed, which are pending, which is current. Include recent iteration `exit_reason` per chunk. Do not modify any files, do not dispatch any subagents.

### Dispatch — Retrospect-only

8. Invoke `skillgoid:retrospect` directly. Used when the user abandons or finalizes early.

### Always

9. (Retrospect phase is only reached after integration succeeds — see Task 8.)

## Output

Stream a short progress line after each chunk subagent returns. End with a final summary of what was built and where artifacts live.
```

- [ ] **Step 7.2: Verify frontmatter still parses**

Run: `python -c "import yaml; f=open('skills/build/SKILL.md'); lines=f.read().split('---', 2); print(yaml.safe_load(lines[1]))"`
Expected: prints build's name + description.

- [ ] **Step 7.3: Full test + lint**

Run: `pytest -v && ruff check .`
Expected: 50 tests pass (no new tests, skills are prose). Ruff clean.

- [ ] **Step 7.4: Commit**

```bash
git add skills/build/SKILL.md
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "feat(build): dispatch each chunk as a fresh subagent

Replaces the v0 inline invocation of skillgoid:loop with a subagent
dispatch per chunk via the Agent tool. Main session becomes a pure
orchestrator — it never carries per-chunk working context.

Each subagent gets a curated prompt (chunk spec + retrieve summary +
blueprint + last 2 iterations if resuming) and returns a JSON summary
with exit_reason, iterations_used, final gate_report, and notes.

v0.2 passes the whole blueprint.md to each subagent; blueprint slicing
deferred to v0.3."
```

---

## Task 8: `build` skill — integration gate phase + retry

**Files:**
- Modify: `skills/build/SKILL.md`

- [ ] **Step 8.1: Extend `build` SKILL.md with integration phase**

Open `skills/build/SKILL.md`. Replace step 4 ("When all chunks have succeeded...") with the full integration orchestration:

```markdown
4. **When all chunks have succeeded**, run the integration phase:

   4a. Read `.skillgoid/criteria.yaml`. If `integration_gates` is absent or empty, skip to step 6 (retrospect).

   4b. Create `.skillgoid/integration/` if absent.

   4c. Determine `integration_retries` (default 2). Track `attempt = 1`.

   4d. **Dispatch integration subagent** via the Agent tool:
      ```
      Agent(
        subagent_type="general-purpose",
        model="haiku",          # integration check is pure measurement, no judgment
        description="Run Skillgoid integration gates (attempt <attempt>)",
        prompt=<integration prompt — see template below>,
      )
      ```

      **Integration subagent prompt template:**
      ```
      You are running Skillgoid's integration gates — the end-to-end checks
      that verify the project works as a whole after all chunks have passed
      their individual gates.

      ## Your task
      1. Read `.skillgoid/criteria.yaml` and extract `integration_gates`.
      2. Invoke `skillgoid:python-gates` (or the appropriate language-gates
         skill) with the integration_gates list as the gates to run.
      3. Return the structured JSON report verbatim.

      If `integration_failure_context` is provided below, include it when
      building the chunk's next-iteration context if you need to retry.
      For attempt 1, there is no prior context.

      ## Integration failure context (from previous attempt, if any)
      <empty on attempt 1; set by orchestrator on retries>

      ## Return format
      Return a JSON object on your final message:
      {
        "passed": bool,
        "results": [ ... same shape as any gate_report.results ... ]
      }
      ```

   4e. Write `.skillgoid/integration/<attempt>.json` with the returned report:
      ```json
      {
        "attempt": <attempt>,
        "chunk_id": "__integration__",
        "gate_report": { ... returned verbatim ... },
        "started_at": "ISO-8601",
        "ended_at": "ISO-8601"
      }
      ```

   4f. **If `gate_report.passed == true`**: integration succeeded. Proceed to step 6 (retrospect).

   4g. **If `gate_report.passed == false` and `attempt < integration_retries + 1`**: auto-repair path.

      - **Identify suspect chunk(s).** For each failing gate, grep its `stderr` and `stdout` for filenames that appear in the chunks' blueprint/impl paths. Pick the chunk whose file is most recently mentioned. If no filename match, ask the user which chunk to retry.
      - **Re-dispatch the suspect chunk's loop subagent** (exactly as in step 3c) with extra injected context: a new field `integration_failure_context` in the chunk prompt describing the integration-gate failure (which gate failed, hint, stderr prefix). The loop subagent should interpret this as "your chunk's per-chunk gates pass, but the full system fails at X — fix your chunk to address X."
      - After the chunk subagent returns (with a fresh `success` / `stalled` / `budget_exhausted`), increment `attempt` and return to step 4d to re-run the integration subagent.

   4h. **If `gate_report.passed == false` and attempts exhausted**: Surface to the user. Do NOT auto-invoke retrospect. Print:
      ```
      Integration failed after <N> attempts. See .skillgoid/integration/*.json
      for reports. Run /skillgoid:build retrospect-only to finalize this
      project as-is, or debug manually and re-run.
      ```
      Stop.

5. (The original step 4 is now step 4+.)

6. **Retrospect phase.** Invoke `skillgoid:retrospect`. Used when integration passes, or explicitly via `/skillgoid:build retrospect-only`.
```

Also renumber the "Resume" / "Status only" / "Retrospect-only" subsections to follow the main flow, keeping the document consistent.

- [ ] **Step 8.2: Verify frontmatter still parses**

Run: `python -c "import yaml; f=open('skills/build/SKILL.md'); lines=f.read().split('---', 2); print(yaml.safe_load(lines[1]))"`
Expected: parses cleanly.

- [ ] **Step 8.3: Full test + lint**

Run: `pytest -v && ruff check .`
Expected: 50 tests pass, ruff clean.

- [ ] **Step 8.4: Commit**

```bash
git add skills/build/SKILL.md
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "feat(build): integration-gate phase with auto-repair retries

After all chunks pass, dispatch a fresh Haiku subagent to run
integration_gates via skillgoid:python-gates. On failure, identify
suspect chunk via filename grep against gate stderr, re-dispatch that
chunk's loop subagent with integration_failure_context injected, then
re-run integration. Up to integration_retries attempts (default 2).

Integration attempt records land in .skillgoid/integration/<N>.json.
On exhaustion, surface to user — no silent retrospect-and-ship."
```

---

## Task 9: `plan` skill — blueprint heading discipline

**Files:**
- Modify: `skills/plan/SKILL.md`

v0.2 passes the whole `blueprint.md` to each chunk subagent (no slicing). v0.3 will slice by section heading. Prepare now by insisting that `plan` emits blueprints with clear per-module headings.

- [ ] **Step 9.1: Extend the `plan` skill's blueprint instructions**

Open `skills/plan/SKILL.md`. In step 3 (Write `blueprint.md`), modify the module-layout bullet to require per-module headings:

Replace:
```markdown
3. **Write `blueprint.md`** covering:
   - Architecture overview (1–3 paragraphs)
   - Module layout and responsibilities (which files go where)
```

With:
```markdown
3. **Write `blueprint.md`** covering:
   - Architecture overview (1–3 paragraphs)
   - Module layout and responsibilities — use `## <module-name>` headings for each module/chunk so future blueprint-slicing tools can extract per-chunk sections cleanly. Each heading should match (or obviously relate to) a chunk id in `chunks.yaml`.
```

Also add a short note under "Principles":

```markdown
- **Heading discipline.** Blueprint module headings (`##`) should map 1:1 to chunks in `chunks.yaml`. This keeps each chunk's subagent focused on the right section of the blueprint.
```

- [ ] **Step 9.2: Verify frontmatter**

Run: `python -c "import yaml; f=open('skills/plan/SKILL.md'); lines=f.read().split('---', 2); print(yaml.safe_load(lines[1]))"`
Expected: parses.

- [ ] **Step 9.3: Commit**

```bash
git add skills/plan/SKILL.md
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "feat(plan): require per-module blueprint headings matching chunk ids

v0.2 passes whole blueprint.md to each chunk subagent, but v0.3 will
slice by section heading. Enforce heading discipline now so existing
blueprints are forward-compatible."
```

---

## Task 10: Integration test — integration-gate flow

**Files:**
- Create: `tests/test_integration_gate_flow.py`

Tests the machinery that can be exercised without a live Claude session: that the adapter can accept integration_gates as its gate list, that the integration attempt JSON shape is writable-and-readable, and that `stall_check.py` on an integration attempt behaves the same as on a regular iteration.

- [ ] **Step 10.1: Write `tests/test_integration_gate_flow.py`**

```python
"""End-to-end-ish tests for the integration-gate flow.

Covers the machinery that can be tested without a live Claude session:
- measure_python.py accepts integration_gates as its gate list (they're
  just regular gates with a different semantic meaning).
- The integration attempt JSON shape (iterations-like with chunk_id
  "__integration__") validates against iterations.schema.json.
- stall_check.py handles integration attempt records the same as regular
  iteration records.
"""
import json
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

from scripts.stall_check import signature

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "scripts" / "measure_python.py"
PASSING_PROJECT = ROOT / "tests" / "fixtures" / "passing-project"
FAILING_PROJECT = ROOT / "tests" / "fixtures" / "failing-project"


def _iterations_validator() -> Draft202012Validator:
    schema = json.loads((ROOT / "schemas" / "iterations.schema.json").read_text())
    return Draft202012Validator(schema)


def test_adapter_runs_integration_gates_on_passing_fixture():
    # integration_gates have the exact same shape as gates[]; the adapter
    # doesn't distinguish. We simulate by naming the gate id "integration".
    criteria = """
gates:
  - id: integration_smoke
    type: import-clean
    module: mypkg
"""
    result = subprocess.run(
        [sys.executable, str(ADAPTER), "--project", str(PASSING_PROJECT), "--criteria-stdin"],
        input=criteria, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["passed"] is True
    assert report["results"][0]["gate_id"] == "integration_smoke"


def test_adapter_surfaces_integration_failure_clearly(tmp_path: Path):
    criteria = """
gates:
  - id: integration_smoke
    type: cli-command-runs
    command: ["false"]
    expect_exit: 0
"""
    result = subprocess.run(
        [sys.executable, str(ADAPTER), "--project", str(tmp_path), "--criteria-stdin"],
        input=criteria, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["passed"] is False
    assert "expected 0" in report["results"][0]["hint"] or "exit=" in report["results"][0]["hint"]


def test_integration_attempt_record_validates_against_iterations_schema():
    """Integration attempts use the same schema as per-chunk iterations, with
    chunk_id = '__integration__'. Confirm the record shape the build skill
    writes passes iterations.schema.json."""
    record = {
        "iteration": 1,
        "chunk_id": "__integration__",
        "gate_report": {
            "passed": False,
            "results": [
                {"gate_id": "e2e", "passed": False, "stdout": "", "stderr": "oops", "hint": "check X"}
            ],
        },
        "failure_signature": signature({
            "gate_report": {
                "passed": False,
                "results": [
                    {"gate_id": "e2e", "passed": False, "stdout": "", "stderr": "oops", "hint": "check X"}
                ],
            }
        }),
        "exit_reason": "in_progress",
    }
    errors = list(_iterations_validator().iter_errors(record))
    assert errors == []


def test_stall_signature_on_integration_attempt_is_deterministic():
    """Two integration attempts with identical failures should produce
    identical signatures — same as regular iterations."""
    report = {
        "passed": False,
        "results": [
            {"gate_id": "cli_smoke", "passed": False, "stdout": "", "stderr": "nope"}
        ],
    }
    rec_a = {"chunk_id": "__integration__", "gate_report": report}
    rec_b = {"chunk_id": "__integration__", "gate_report": report}
    assert signature(rec_a) == signature(rec_b)
```

- [ ] **Step 10.2: Run — confirm pass (tests import existing modules, so should run immediately)**

Run: `pytest tests/test_integration_gate_flow.py -v`
Expected: 4 tests pass.

- [ ] **Step 10.3: Full test + lint**

Run: `pytest -v && ruff check .`
Expected: 54 total (50 + 4), ruff clean.

- [ ] **Step 10.4: Commit**

```bash
git add tests/test_integration_gate_flow.py
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "test: integration-gate flow — adapter reuse + schema + stall parity

Covers the integration-gate machinery that's testable without a live
Claude session: measure_python.py runs integration_gates (same shape as
gates), integration attempt JSON validates against iterations.schema.json,
and stall_check produces deterministic signatures on integration records.

Subagent dispatch itself is not unit-testable — it's guaranteed by
Claude Code's Agent tool contract."
```

---

## Task 11: README + CHANGELOG updates

**Files:**
- Modify: `README.md`
- Create: `CHANGELOG.md`

- [ ] **Step 11.1: Extend README with a "What's new in v0.2" section**

Open `README.md`. Insert a new section right before the `## Concepts` section:

```markdown
## What's new in v0.2

Three structural upgrades that make the build loop credible on real projects:

- **Subagent-per-chunk isolation.** Each chunk runs in a fresh subagent with a curated context slice — the main session stays small, cross-chunk interference goes away, and long projects no longer burn tokens on accumulated context.
- **Deterministic stall detection + git-per-iteration.** Stalls are now detected by hash comparison, not judgment. Every iteration produces a git commit (`skillgoid: iter N of chunk <id> …`) for free rollback targets. Opt out with `loop.skip_git: true` in `criteria.yaml`.
- **Integration gate.** Opt-in `integration_gates:` block in `criteria.yaml` runs after all per-chunk gates pass — catches "green gates, broken product" failures. Up to 2 auto-repair retries before surfacing.

All changes are backward-compatible. Existing v0 projects resume unchanged.
```

And in the `## Commands` section, no changes needed — user-facing commands are identical.

- [ ] **Step 11.2: Create `CHANGELOG.md`**

```markdown
# Changelog

All notable changes to Skillgoid. Format: Keep a Changelog. Versioning: SemVer.

## [0.2.0] — 2026-04-17

### Added
- Subagent-per-chunk isolation: `build` skill now dispatches a fresh subagent per chunk via the `Agent` tool, bounding context and preventing cross-chunk interference.
- Deterministic stall detection via `scripts/stall_check.py` — 16-char hex signature from sorted failing gate IDs + first 200 chars of failing stderr.
- Git-per-iteration commits via `scripts/git_iter_commit.py` — structured `skillgoid:` messages with chunk id, iteration number, gate summary, signature. Noops on non-git projects.
- `integration_gates:` criteria field — optional end-to-end gates that run once after all per-chunk gates pass. Uses an integration subagent (Haiku, since it's pure measurement).
- Auto-repair on integration failure: identify suspect chunk via filename grep, re-dispatch that chunk's loop subagent with failure context, re-run integration. Up to `integration_retries` (default 2) attempts.
- `loop.skip_git` config option to opt out of git-per-iteration.
- `schemas/iterations.schema.json` — locks the iteration JSON shape including `failure_signature` (16-hex regex) and `exit_reason` enum.
- `clarify` skill now proposes a sensible default `integration_gates` entry by project type (CLI / library / service).
- `plan` skill now requires per-module blueprint headings that map 1:1 to chunk ids (forward-compat for v0.3 blueprint slicing).

### Changed
- `loop` skill procedure — step 8 now writes `failure_signature` via `stall_check.py`; new step 8.1 runs `git_iter_commit.py`; stall exit condition is signature equality, not judgment.
- `build` skill — rewritten as a pure orchestrator/dispatcher. No longer invokes `skillgoid:loop` inline.

### Backward compatibility
- v0 `criteria.yaml` / `chunks.yaml` / iteration records all parse unchanged.
- Projects not in git are unaffected (git-per-iteration is a noop).
- `integration_gates` is optional — v0 projects skip the phase entirely.

## [0.1.0] — 2026-04-17

Initial v0 release. See `docs/superpowers/specs/2026-04-17-skillgoid-design.md` for the concept.
```

- [ ] **Step 11.3: Commit**

```bash
git add README.md CHANGELOG.md
git -c user.email=flipmlacombe@gmail.com -c user.name=flip commit -m "docs: v0.2 release notes in README and CHANGELOG

User-facing commands unchanged; this documents the architectural
upgrades shipped in v0.2 so users know what changed when they update."
```

---

## Self-review

**Spec coverage check:**

- §3.1 Subagent-per-chunk isolation → Task 7 (`build` rewrite), Task 10 (reuse-via-schema tests).
- §3.2 Stall signature → Tasks 2 + 4 (helper + loop update).
- §3.2 Git-per-iteration → Tasks 3 + 4 (helper + loop update).
- §3.3 Integration gate → Tasks 5 (schema), 6 (clarify default), 8 (build integration phase), 10 (tests).
- §4.1 Iteration JSON field addition → Task 5 (iterations.schema.json locks the shape).
- §4.2 Criteria fields → Task 5 (schema).
- §4.3 `.skillgoid/integration/` directory → Task 8 (build writes it).
- §5 Skill-level changes — `build` (Task 7+8), `loop` (Task 4), `clarify` (Task 6), `plan` (Task 9). All accounted for.
- §6 Hooks — no changes (spec §6 says "no changes"). ✓
- §7 Testing strategy → Tasks 2, 3, 5, 10. stall_check tests (Task 2), git helper tests (Task 3), schema tests (Task 5), integration flow tests (Task 10). Git helper tests cover `tests/test_git_commits.py` requirement from spec §7.
- §8 Backward compatibility → addressed in schema additive design + optional fields, confirmed in CHANGELOG (Task 11).
- §10 Open questions — resolved inline (blueprint slicing punted to v0.3 via Task 9 heading discipline; suspect-chunk heuristic is filename grep per Task 8).
- §11 Diagram → reflected in Tasks 7+8 (build skill body).
- §12 Complexity budget — plan has 11 tasks ≈ 12-task target. ✓
- §13 Definition of done → README + CHANGELOG updates (Task 11), all test assertions preserved (Tasks 2, 3, 5, 10), backward-compat preserved (additive changes only).

**Placeholder scan:** all task steps contain concrete code or exact instructions. The blueprint-slicing and suspect-chunk heuristics are called out as v0.2 simplifications (punt to v0.3 in Task 9 note; filename-grep explicit in Task 8). No "TBD", "TODO", "implement later" anywhere.

**Type / name consistency check:**
- `signature` function (Task 2) — also referenced by Task 10's imports. ✓
- `commit_iteration(project: Path, record: dict) -> bool` + `is_git_repo(project: Path) -> bool` (Task 3) — referenced in Task 3 tests. ✓
- JSON shape `{passed, results[{gate_id, passed, stdout, stderr, hint}]}` — consistent across measure_python.py (v0), loop skill, integration test.
- `failure_signature` field — written in Task 4, read in Task 4 (stall condition), schema in Task 5, tested in Task 2 + Task 10.
- `__integration__` sentinel chunk_id — Task 8 writes it, Task 10 validates it against iterations.schema.json. ✓
- `Agent(subagent_type=..., model=..., description=..., prompt=...)` — consistent across Tasks 7 and 8.

No gaps found. No renames or signature drift between tasks.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-17-skillgoid-v0.2.md`. Two execution options:

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints.

Which approach?
