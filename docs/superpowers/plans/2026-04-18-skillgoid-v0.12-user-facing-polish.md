# Skillgoid v0.12 — User-Facing Polish Bundle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship four user-facing polish items on top of v0.11's machinery — `/skillgoid:status` in-flight view, `/skillgoid:explain <chunk_id>` post-mortem, auto-partial-retrospective on every terminal state, and `/skillgoid:unstick --dry-run` preview — by adding two language-agnostic extraction scripts, two thin skill wrappers, one grep-verified build-prose edit, and one grep-verified unstick-prose edit.

**Architecture:** Two new scripts (`scripts/status_reader.py`, `scripts/explain_chunk.py`) follow the project's existing CLI pattern (argparse, stdout markdown, `main()`/`raise SystemExit(main())`). Both read from the generic iteration / chunks / integration JSON schemas — zero language-adapter coupling. Wave computation in `status_reader.py` reuses `scripts/chunk_topo.plan_waves()` rather than reimplementing. Auto-retrospect is a prose edit in `skills/build/SKILL.md` with a bundle test locking in outcome classification (`partial` for stall, `abandoned` for empty) through `scripts/metrics_append.py`. Unstick `--dry-run` is prose-only in `skills/unstick/SKILL.md`, verified by grep plus a manual smoke test against the v0.11 integration-retry fixture.

**Tech Stack:** Python ≥3.11, pytest, pyyaml (already installed), ruff. No new dependencies. All deliverables additive and backward-compatible with v0.11 schemas and state.

---

## File map

| Action | Path | What it does |
|---|---|---|
| Create | `scripts/status_reader.py` | Reads `.skillgoid/` in CWD; emits markdown snapshot of chunk/integration state |
| Create | `scripts/explain_chunk.py` | Reads all `<chunk_id>-*.json` iterations; emits timeline table + stall signal + verbatim reflections |
| Create | `skills/status/SKILL.md` | Thin wrapper: invokes `status_reader.py`, passes stdout through |
| Create | `skills/explain/SKILL.md` | Thin wrapper: invokes `explain_chunk.py` with `chunk_id`, passes stdout through |
| Create | `tests/test_status_reader.py` | Unit tests for status_reader: state table, wave grouping, truncation, integration section |
| Create | `tests/test_explain_chunk.py` | Unit tests for explain_chunk: timeline rows, stall signal, reflections, missing-field backcompat |
| Create | `tests/test_auto_retrospect_trigger.py` | Bundle test: grep-verify build-prose edit + lock in `_outcome()` classification |
| Modify | `skills/build/SKILL.md` | Add auto-retrospect step before final summary (success, stalled, budget_exhausted); document skip conditions |
| Modify | `skills/unstick/SKILL.md` | Add `--dry-run` flag prose branch: print constructed prompt, no dispatch |

---

## Task 1: `scripts/status_reader.py` (TDD)

**Files:**
- Create: `tests/test_status_reader.py`
- Create: `scripts/status_reader.py`

The script reads `.skillgoid/chunks.yaml`, `.skillgoid/iterations/*.json`, and optionally `.skillgoid/integration/*.json`. It reuses `scripts.chunk_topo.plan_waves` for the wave grouping and emits markdown on stdout.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_status_reader.py`:

```python
"""Tests for scripts/status_reader.py.

status_reader is read-only: it never mutates .skillgoid/ state. These tests
exercise the pure rendering logic plus the CLI end-to-end via tmp_path.
"""
import json
import subprocess
import sys
from pathlib import Path

from scripts.status_reader import render_status

ROOT = Path(__file__).resolve().parents[1]
CLI = [sys.executable, str(ROOT / "scripts" / "status_reader.py")]


def _write_chunks(sg: Path, chunks: list[dict]) -> None:
    import yaml
    (sg / "chunks.yaml").write_text(yaml.safe_dump({"chunks": chunks}))


def _write_iter(sg: Path, filename: str, *, chunk_id: str, iteration: int,
                exit_reason: str, gate_report: dict | None = None,
                files_touched: list[str] | None = None) -> None:
    iters_dir = sg / "iterations"
    iters_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "iteration": iteration,
        "chunk_id": chunk_id,
        "gate_report": gate_report or {"passed": exit_reason == "success", "results": []},
        "exit_reason": exit_reason,
    }
    if files_touched is not None:
        record["changes"] = {"files_touched": files_touched}
    (iters_dir / filename).write_text(json.dumps(record))


def _write_integration(sg: Path, attempt: int, *, passed: bool,
                       stderr: str = "") -> None:
    integ_dir = sg / "integration"
    integ_dir.mkdir(parents=True, exist_ok=True)
    (integ_dir / f"{attempt}.json").write_text(json.dumps({
        "iteration": attempt,
        "chunk_id": "__integration__",
        "started_at": "2026-04-18T10:01:00Z",
        "gate_report": {
            "passed": passed,
            "results": [
                {"gate_id": "integration_check", "passed": passed,
                 "stdout": "", "stderr": stderr, "hint": ""}
            ],
        },
    }))


def test_empty_project_all_pending(tmp_path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    _write_chunks(sg, [
        {"id": "scaffold", "paths": ["src/app.py"]},
        {"id": "parser", "paths": ["src/parser.py"], "depends_on": ["scaffold"]},
    ])

    out = render_status(sg, project_label="demo")

    assert "# Skillgoid status — demo" in out
    assert "| scaffold" in out
    assert "| parser" in out
    # No iterations → state is pending for both
    assert out.count("pending") >= 2
    # No integration dir → no integration section
    assert "Latest integration attempt" not in out


def test_mixed_state_renders_per_chunk_exit_reason(tmp_path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    _write_chunks(sg, [
        {"id": "scaffold", "paths": ["src/app.py"]},
        {"id": "parser", "paths": ["src/parser.py"], "depends_on": ["scaffold"]},
        {"id": "formatter", "paths": ["src/format.py"], "depends_on": ["scaffold"]},
        {"id": "renderer", "paths": ["src/render.py"],
         "depends_on": ["parser", "formatter"]},
    ])
    _write_iter(sg, "scaffold-001.json", chunk_id="scaffold",
                iteration=1, exit_reason="success")
    _write_iter(sg, "parser-001.json", chunk_id="parser",
                iteration=1, exit_reason="in_progress")
    _write_iter(sg, "parser-002.json", chunk_id="parser",
                iteration=2, exit_reason="in_progress")
    _write_iter(sg, "parser-003.json", chunk_id="parser",
                iteration=3, exit_reason="stalled")
    _write_iter(sg, "formatter-001.json", chunk_id="formatter",
                iteration=1, exit_reason="in_progress")
    # renderer: no iterations → pending

    out = render_status(sg, project_label="demo")

    assert "| scaffold" in out and "success" in out
    assert "| parser" in out and "stalled" in out
    assert "| formatter" in out and "in_progress" in out
    assert "| renderer" in out and "pending" in out


def test_wave_column_reflects_chunk_topo(tmp_path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    _write_chunks(sg, [
        {"id": "scaffold", "paths": ["src/app.py"]},
        {"id": "parser", "paths": ["src/parser.py"], "depends_on": ["scaffold"]},
        {"id": "formatter", "paths": ["src/format.py"], "depends_on": ["scaffold"]},
        {"id": "renderer", "paths": ["src/render.py"],
         "depends_on": ["parser", "formatter"]},
    ])

    out = render_status(sg, project_label="demo")

    # scaffold = wave 1, parser + formatter = wave 2, renderer = wave 3
    # The rendered table must show 1, 2, 2, 3 in the wave column for the four chunks.
    lines = [ln for ln in out.splitlines() if ln.startswith("| ")]
    row_by_id = {
        ln.split("|")[1].strip(): ln
        for ln in lines if not ln.strip().startswith("| chunk_id") and not ln.strip().startswith("|---")
    }
    assert " 1 " in row_by_id["scaffold"], f"scaffold row: {row_by_id['scaffold']!r}"
    assert " 2 " in row_by_id["parser"], f"parser row: {row_by_id['parser']!r}"
    assert " 2 " in row_by_id["formatter"], f"formatter row: {row_by_id['formatter']!r}"
    assert " 3 " in row_by_id["renderer"], f"renderer row: {row_by_id['renderer']!r}"


def test_files_touched_truncation(tmp_path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    _write_chunks(sg, [{"id": "big", "paths": ["src/big.py"]}])
    _write_iter(sg, "big-001.json", chunk_id="big", iteration=1,
                exit_reason="success",
                files_touched=["a.py", "b.py", "c.py", "d.py", "e.py"])

    out = render_status(sg, project_label="demo")

    # First 2 shown, remainder summarised
    assert "a.py" in out and "b.py" in out
    assert "(+3 more)" in out
    # Not all 5 listed in the files column
    assert "c.py" not in out or "d.py" not in out


def test_gate_state_truncation(tmp_path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    _write_chunks(sg, [{"id": "big", "paths": ["src/big.py"]}])
    _write_iter(sg, "big-001.json", chunk_id="big", iteration=1,
                exit_reason="in_progress",
                gate_report={
                    "passed": False,
                    "results": [
                        {"gate_id": "ruff", "passed": True},
                        {"gate_id": "mypy", "passed": True},
                        {"gate_id": "pytest_unit", "passed": False,
                         "stderr": "assertion error"},
                        {"gate_id": "pytest_integration", "passed": False,
                         "stderr": "fixture error"},
                        {"gate_id": "coverage", "passed": False, "stderr": "below 80%"},
                    ],
                })

    out = render_status(sg, project_label="demo")

    # First 3 gate names rendered, remainder summarised
    assert "ruff" in out and "mypy" in out and "pytest_unit" in out
    assert "(+2 more)" in out


def test_integration_section_rendered_when_present(tmp_path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    _write_chunks(sg, [{"id": "one", "paths": ["src/a.py"]}])
    _write_iter(sg, "one-001.json", chunk_id="one", iteration=1,
                exit_reason="success")
    _write_integration(sg, 1, passed=False,
                       stderr="src/a.py:42: AssertionError in test_one")

    out = render_status(sg, project_label="demo")

    assert "Latest integration attempt" in out
    assert "Attempt 1" in out
    assert "FAILED" in out
    assert "AssertionError" in out


def test_cli_no_skillgoid_dir_exits_one(tmp_path):
    # No .skillgoid/ in tmp_path → CLI exits 1 with clear stderr
    result = subprocess.run(
        CLI + ["--skillgoid-dir", str(tmp_path / ".skillgoid")],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "not a Skillgoid project" in result.stderr


def test_cli_happy_path_round_trip(tmp_path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    _write_chunks(sg, [{"id": "one", "paths": ["src/a.py"]}])
    _write_iter(sg, "one-001.json", chunk_id="one", iteration=1,
                exit_reason="success")

    result = subprocess.run(
        CLI + ["--skillgoid-dir", str(sg)],
        capture_output=True, text=True, cwd=tmp_path,
    )
    assert result.returncode == 0
    assert "# Skillgoid status" in result.stdout
    assert "| one" in result.stdout
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_status_reader.py -v
```

Expected: all tests FAIL with `ModuleNotFoundError: No module named 'scripts.status_reader'` (or similar import error).

- [ ] **Step 3: Implement `scripts/status_reader.py`**

Create the script:

```python
#!/usr/bin/env python3
"""Skillgoid status reader.

Reads `.skillgoid/chunks.yaml`, `.skillgoid/iterations/*.json`, and optionally
`.skillgoid/integration/*.json` in the current working directory. Emits a
markdown snapshot of the project's in-flight state.

Read-only. Never modifies any file.

Contract:
    render_status(sg: Path, project_label: str) -> str

CLI:
    python scripts/status_reader.py [--skillgoid-dir .skillgoid]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from scripts.chunk_topo import plan_waves


def _load_chunks(sg: Path) -> list[dict]:
    chunks_file = sg / "chunks.yaml"
    if not chunks_file.exists():
        return []
    data = yaml.safe_load(chunks_file.read_text()) or {}
    chunks = data.get("chunks") or []
    return chunks if isinstance(chunks, list) else []


def _latest_iteration_for_chunk(sg: Path, chunk_id: str) -> dict | None:
    iters_dir = sg / "iterations"
    if not iters_dir.is_dir():
        return None
    candidates = list(iters_dir.glob(f"{chunk_id}-*.json"))
    if not candidates:
        return None
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    try:
        return json.loads(latest.read_text())
    except Exception:
        return None


def _latest_integration(sg: Path) -> tuple[int, dict] | None:
    integ_dir = sg / "integration"
    if not integ_dir.is_dir():
        return None
    candidates = [p for p in integ_dir.glob("*.json")]
    if not candidates:
        return None
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    try:
        record = json.loads(latest.read_text())
    except Exception:
        return None
    try:
        attempt = int(latest.stem)
    except ValueError:
        attempt = record.get("iteration", 0)
    return attempt, record


def _wave_for_chunk(waves: list[list[str]], chunk_id: str) -> int | None:
    for idx, wave in enumerate(waves, start=1):
        if chunk_id in wave:
            return idx
    return None


def _gate_state_summary(record: dict | None) -> str:
    if record is None:
        return "—"
    gate_report = record.get("gate_report") or {}
    results = gate_report.get("results") if isinstance(gate_report, dict) else gate_report
    if not results:
        return "—"
    parts: list[str] = []
    for r in results[:3]:
        gid = r.get("gate_id", "?")
        passed = r.get("passed", False)
        parts.append(f"{gid} {'pass' if passed else 'FAIL'}")
    summary = ", ".join(parts)
    remainder = len(results) - 3
    if remainder > 0:
        summary += f" (+{remainder} more)"
    return summary


def _files_touched_summary(record: dict | None) -> str:
    if record is None:
        return "—"
    changes = record.get("changes") or {}
    files = changes.get("files_touched") or []
    if not files:
        return "—"
    shown = files[:2]
    summary = ", ".join(shown)
    remainder = len(files) - 2
    if remainder > 0:
        summary += f" (+{remainder} more)"
    return summary


def _truncate_stderr(text: str, limit: int = 120) -> str:
    if not text:
        return ""
    first_line = text.splitlines()[0] if text else ""
    if len(first_line) > limit:
        return first_line[:limit] + "..."
    return first_line


def render_status(sg: Path, project_label: str) -> str:
    chunks = _load_chunks(sg)
    try:
        waves = plan_waves(chunks) if chunks else []
    except Exception:
        waves = []

    lines: list[str] = []
    lines.append(f"# Skillgoid status — {project_label}")
    lines.append("")

    wave_count = len(waves)
    if wave_count:
        lines.append(f"**Phase:** {wave_count} wave(s) planned")
    else:
        lines.append("**Phase:** no chunks planned")
    lines.append("")

    lines.append("## Chunks")
    lines.append("| chunk_id | wave | state | iter | latest gate state | files touched |")
    lines.append("|----------|------|-------|------|-------------------|---------------|")

    for chunk in chunks:
        cid = chunk.get("id", "?")
        wave = _wave_for_chunk(waves, cid)
        wave_cell = str(wave) if wave is not None else "—"
        record = _latest_iteration_for_chunk(sg, cid)
        if record is None:
            state = "pending"
            iter_num = "—"
        else:
            state = record.get("exit_reason", "in_progress")
            iter_num = str(record.get("iteration", "?"))
        gate = _gate_state_summary(record)
        files = _files_touched_summary(record)
        lines.append(
            f"| {cid} | {wave_cell} | {state} | {iter_num} | {gate} | {files} |"
        )

    integ = _latest_integration(sg)
    if integ is not None:
        attempt, record = integ
        lines.append("")
        lines.append("## Latest integration attempt")
        gate_report = record.get("gate_report") or {}
        passed = gate_report.get("passed", False)
        status = "PASSED" if passed else "FAILED"
        ts = record.get("started_at", "")
        lines.append(f"- Attempt {attempt} ({ts}) — {status}")
        results = gate_report.get("results") or []
        for r in results:
            if r.get("passed"):
                continue
            gid = r.get("gate_id", "?")
            stderr = _truncate_stderr(r.get("stderr", ""))
            if stderr:
                lines.append(f"  - Gate `{gid}` stderr: `{stderr}`")

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Skillgoid project status reader")
    ap.add_argument("--skillgoid-dir", type=Path, default=Path(".skillgoid"))
    args = ap.parse_args(argv)

    sg = args.skillgoid_dir.resolve()
    if not sg.is_dir():
        sys.stderr.write("not a Skillgoid project: .skillgoid/ not found\n")
        return 1

    project_label = sg.parent.name or "unknown"
    sys.stdout.write(render_status(sg, project_label))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_status_reader.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Lint**

```bash
.venv/bin/ruff check scripts/status_reader.py tests/test_status_reader.py
```

Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add scripts/status_reader.py tests/test_status_reader.py
git commit -m "status_reader: markdown snapshot of in-flight project state (v0.12)"
```

---

## Task 2: `skills/status/SKILL.md` thin wrapper

**Files:**
- Create: `skills/status/SKILL.md`

- [ ] **Step 1: Write the skill**

Create `skills/status/SKILL.md`:

```markdown
---
name: status
description: Use when the user wants to see the current project's in-flight state — which chunks have passed, which are stuck, which are pending, and whether the last integration attempt failed. Invokable as `/skillgoid:status`. Read-only; never modifies `.skillgoid/`.
---

# status

## What this skill does

Reads `.skillgoid/chunks.yaml`, `.skillgoid/iterations/*.json`, and `.skillgoid/integration/*.json` in the current working directory and produces a markdown snapshot of the project's current state.

## When to use

- The user asks "what's Skillgoid doing right now?" / "which chunk is stuck?" / "did integration pass?".
- Mid-run, when a wave has been working silently for a while and the user wants an overview without reading `iterations/*.json` by hand.
- Before invoking `/skillgoid:unstick` or `/skillgoid:explain <chunk_id>`, to identify the chunk of interest.

**NOT** for:
- Cross-project metrics (use `/skillgoid:stats` instead).
- Modifying state (this skill is strictly read-only).
- Chunk-level post-mortem (use `/skillgoid:explain <chunk_id>` for an iteration timeline).

## Inputs

- None required. Runs against `./.skillgoid/` in the current working directory.
- Optional `skillgoid_dir` path override — defaults to `./.skillgoid`.

## Procedure

1. Invoke:
   ```bash
   python <plugin-root>/scripts/status_reader.py [--skillgoid-dir .skillgoid]
   ```
2. The script emits a markdown report on stdout. Pass it through to the user unchanged. Do not re-interpret or re-synthesize; the script's output is the authoritative view.

## Output format

```markdown
# Skillgoid status — <cwd basename>

**Phase:** N wave(s) planned

## Chunks
| chunk_id | wave | state | iter | latest gate state | files touched |
| scaffold | 1 | success | 1 | ruff pass, pytest pass | src/app.py |
| parser | 2 | stalled | 3 | pytest_unit FAIL | src/parser.py |
...

## Latest integration attempt
- Attempt 1 (2026-04-18T10:01:00Z) — FAILED
  - Gate `integration_check` stderr: `src/parser.py:42: AssertionError...`
```

## What this skill does NOT do

- Write to or modify `.skillgoid/`.
- Dispatch any loop / integration / retrospect subagents.
- Render HTML or fetch remote data.
- Summarize across projects — that is `/skillgoid:stats`.
```

- [ ] **Step 2: Verify the skill file is well-formed**

```bash
grep -n "^name: status" skills/status/SKILL.md
grep -n "status_reader.py" skills/status/SKILL.md
```

Expected: both lines found.

- [ ] **Step 3: Commit**

```bash
git add skills/status/SKILL.md
git commit -m "status: thin wrapper skill for in-flight project snapshot (v0.12)"
```

---

## Task 3: `scripts/explain_chunk.py` (TDD)

**Files:**
- Create: `tests/test_explain_chunk.py`
- Create: `scripts/explain_chunk.py`

Reads all `.skillgoid/iterations/<chunk_id>-*.json` files in numeric order and emits a timeline table, stall-signal section (if any two consecutive iterations share a signature), and verbatim reflections.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_explain_chunk.py`:

```python
"""Tests for scripts/explain_chunk.py.

explain_chunk reads every iteration for a chunk and renders a compact
timeline with verbatim reflections. Read-only.
"""
import json
import subprocess
import sys
from pathlib import Path

from scripts.explain_chunk import render_explain

ROOT = Path(__file__).resolve().parents[1]
CLI = [sys.executable, str(ROOT / "scripts" / "explain_chunk.py")]


def _write_iter(iters_dir: Path, filename: str, record: dict) -> None:
    iters_dir.mkdir(parents=True, exist_ok=True)
    (iters_dir / filename).write_text(json.dumps(record))


def _stalled_record(chunk_id: str, iteration: int, *, exit_reason: str,
                    signature: str, stderr: str,
                    reflection: str | None = None,
                    files_touched: list[str] | None = None) -> dict:
    record = {
        "iteration": iteration,
        "chunk_id": chunk_id,
        "gate_report": {
            "passed": exit_reason == "success",
            "results": [
                {"gate_id": "pytest_unit", "passed": False,
                 "stderr": stderr, "hint": ""}
            ],
        },
        "exit_reason": exit_reason,
        "failure_signature": signature,
    }
    if reflection is not None:
        record["reflection"] = reflection
    if files_touched is not None:
        record["changes"] = {"files_touched": files_touched}
    return record


def test_three_iteration_stalled_chunk_renders_timeline(tmp_path):
    sg = tmp_path / ".skillgoid"
    iters = sg / "iterations"
    sig = "a1b2c3d4e5f6a7b8"
    _write_iter(iters, "parser-001.json", _stalled_record(
        "parser", 1, exit_reason="in_progress", signature=sig,
        stderr="AssertionError in test_parse_iso",
        reflection="Tried adding timezone handling; still fails.",
        files_touched=["src/parser.py"]))
    _write_iter(iters, "parser-002.json", _stalled_record(
        "parser", 2, exit_reason="in_progress", signature=sig,
        stderr="AssertionError in test_parse_iso",
        reflection="Tried using dateutil; still fails same way.",
        files_touched=["src/parser.py"]))
    _write_iter(iters, "parser-003.json", _stalled_record(
        "parser", 3, exit_reason="stalled", signature=sig,
        stderr="AssertionError in test_parse_iso",
        reflection="Same failure 3rd time. Signature unchanged.",
        files_touched=["src/parser.py"]))

    out = render_explain(sg, chunk_id="parser")

    assert "# Chunk `parser` — 3 iterations" in out
    assert "## Timeline" in out
    assert "| 1 |" in out
    assert "| 2 |" in out
    assert "| 3 |" in out
    # Signature is truncated to 8 chars in the sig column
    assert "a1b2c3d4" in out
    assert "## Stall signal" in out
    assert "Signature `a1b2c3d4` repeated" in out
    # Reflections section has one subheading per iteration
    assert "## Reflections" in out
    assert "### Iteration 1" in out
    assert "### Iteration 2" in out
    assert "### Iteration 3" in out
    assert "Tried adding timezone handling" in out


def test_single_iteration_success_has_no_stall_section(tmp_path):
    sg = tmp_path / ".skillgoid"
    iters = sg / "iterations"
    _write_iter(iters, "scaffold-001.json", {
        "iteration": 1,
        "chunk_id": "scaffold",
        "gate_report": {"passed": True, "results": []},
        "exit_reason": "success",
        "reflection": "Scaffold landed cleanly.",
    })

    out = render_explain(sg, chunk_id="scaffold")

    assert "# Chunk `scaffold` — 1 iteration" in out
    assert "| 1 |" in out
    assert "## Stall signal" not in out
    assert "Scaffold landed cleanly" in out


def test_same_signature_annotation_and_stall_section(tmp_path):
    sg = tmp_path / ".skillgoid"
    iters = sg / "iterations"
    sig = "deadbeefdeadbeef"
    _write_iter(iters, "parser-001.json", _stalled_record(
        "parser", 1, exit_reason="in_progress", signature=sig,
        stderr="same error line",
        reflection="try 1"))
    _write_iter(iters, "parser-002.json", _stalled_record(
        "parser", 2, exit_reason="in_progress", signature=sig,
        stderr="same error line",
        reflection="try 2"))

    out = render_explain(sg, chunk_id="parser")

    # Second iteration row shows `(same)` on the stderr column
    timeline_rows = [ln for ln in out.splitlines() if ln.startswith("| ")]
    row_2 = next(r for r in timeline_rows if r.strip().startswith("| 2 |"))
    assert "(same)" in row_2, f"row 2 missing (same): {row_2!r}"
    assert "## Stall signal" in out
    assert "deadbeef" in out


def test_missing_reflection_field_is_omitted(tmp_path):
    sg = tmp_path / ".skillgoid"
    iters = sg / "iterations"
    _write_iter(iters, "scaffold-001.json", {
        "iteration": 1,
        "chunk_id": "scaffold",
        "gate_report": {"passed": True, "results": []},
        "exit_reason": "success",
    })
    _write_iter(iters, "scaffold-002.json", {
        "iteration": 2,
        "chunk_id": "scaffold",
        "gate_report": {"passed": True, "results": []},
        "exit_reason": "success",
        "reflection": "Iteration 2 had a reflection.",
    })

    out = render_explain(sg, chunk_id="scaffold")

    assert "### Iteration 2" in out
    assert "Iteration 2 had a reflection" in out
    # Iteration 1 has no reflection → its subheading is omitted
    assert "### Iteration 1" not in out


def test_missing_failure_signature_renders_dash(tmp_path):
    sg = tmp_path / ".skillgoid"
    iters = sg / "iterations"
    _write_iter(iters, "legacy-001.json", {
        "iteration": 1,
        "chunk_id": "legacy",
        "gate_report": {
            "passed": False,
            "results": [
                {"gate_id": "pytest_unit", "passed": False,
                 "stderr": "some failure", "hint": ""}
            ],
        },
        "exit_reason": "stalled",
        # No failure_signature field on purpose
    })

    out = render_explain(sg, chunk_id="legacy")

    timeline_rows = [ln for ln in out.splitlines() if ln.startswith("| 1 ")]
    assert any("—" in r for r in timeline_rows), \
        f"expected em-dash in sig column, rows: {timeline_rows!r}"


def test_unknown_chunk_exits_one(tmp_path):
    sg = tmp_path / ".skillgoid"
    (sg / "iterations").mkdir(parents=True)

    result = subprocess.run(
        CLI + ["--chunk-id", "nope", "--skillgoid-dir", str(sg)],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "no iteration files for chunk" in result.stderr


def test_cli_happy_path(tmp_path):
    sg = tmp_path / ".skillgoid"
    iters = sg / "iterations"
    _write_iter(iters, "scaffold-001.json", {
        "iteration": 1,
        "chunk_id": "scaffold",
        "gate_report": {"passed": True, "results": []},
        "exit_reason": "success",
        "reflection": "Done.",
    })

    result = subprocess.run(
        CLI + ["--chunk-id", "scaffold", "--skillgoid-dir", str(sg)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "# Chunk `scaffold`" in result.stdout
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_explain_chunk.py -v
```

Expected: all tests FAIL with import error.

- [ ] **Step 3: Implement `scripts/explain_chunk.py`**

Create the script:

```python
#!/usr/bin/env python3
"""Skillgoid chunk explain.

Reads all `.skillgoid/iterations/<chunk_id>-*.json` files in order and emits a
markdown timeline + stall-signal section + verbatim reflections. Read-only.

Contract:
    render_explain(sg: Path, chunk_id: str) -> str

CLI:
    python scripts/explain_chunk.py --chunk-id <id> [--skillgoid-dir .skillgoid]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


_ITER_RE = re.compile(r"-(\d+)\.json$")


def _iteration_number(path: Path) -> int:
    m = _ITER_RE.search(path.name)
    return int(m.group(1)) if m else 0


def _load_iterations(sg: Path, chunk_id: str) -> list[dict]:
    iters_dir = sg / "iterations"
    if not iters_dir.is_dir():
        return []
    paths = sorted(iters_dir.glob(f"{chunk_id}-*.json"), key=_iteration_number)
    records: list[dict] = []
    for p in paths:
        try:
            records.append(json.loads(p.read_text()))
        except Exception:
            continue
    return records


def _first_stderr_or_hint(record: dict) -> str:
    gate_report = record.get("gate_report") or {}
    results = gate_report.get("results") if isinstance(gate_report, dict) else gate_report
    if not results:
        return ""
    for r in results:
        if r.get("passed"):
            continue
        stderr = (r.get("stderr") or "").strip()
        if stderr:
            first = stderr.splitlines()[0]
            return first[:80]
        hint = (r.get("hint") or "").strip()
        if hint:
            return hint[:80]
    return ""


def _gate_state_summary(record: dict) -> str:
    gate_report = record.get("gate_report") or {}
    results = gate_report.get("results") if isinstance(gate_report, dict) else gate_report
    if not results:
        return "—"
    parts = []
    for r in results[:3]:
        gid = r.get("gate_id", "?")
        parts.append(f"{gid} {'pass' if r.get('passed') else 'FAIL'}")
    summary = ", ".join(parts)
    if len(results) > 3:
        summary += f" (+{len(results) - 3} more)"
    return summary


def _files_touched_summary(record: dict) -> str:
    changes = record.get("changes") or {}
    files = changes.get("files_touched") or []
    if not files:
        return "—"
    shown = files[:2]
    summary = ", ".join(shown)
    if len(files) > 2:
        summary += f" (+{len(files) - 2} more)"
    return summary


def _signature_short(record: dict) -> str:
    sig = record.get("failure_signature")
    if not sig:
        return "—"
    return sig[:8]


def _detect_stall(records: list[dict]) -> tuple[str, int, int] | None:
    """Return (short_signature, repeat_count, stall_iteration) if any two
    consecutive iterations share a failure_signature, else None.

    repeat_count is the total number of records sharing that signature.
    stall_iteration is the iteration number of the LAST record sharing
    the signature — the closest to terminal, matching spec example.
    """
    if len(records) < 2:
        return None
    for i in range(1, len(records)):
        sig_prev = records[i - 1].get("failure_signature")
        sig_curr = records[i].get("failure_signature")
        if sig_prev and sig_curr and sig_prev == sig_curr:
            matching = [
                r for r in records if r.get("failure_signature") == sig_curr
            ]
            count = len(matching)
            stall_iter = matching[-1].get("iteration", len(matching))
            return sig_curr[:8], count, stall_iter
    return None


def render_explain(sg: Path, chunk_id: str) -> str:
    records = _load_iterations(sg, chunk_id)
    if not records:
        raise FileNotFoundError(f"no iteration files for chunk {chunk_id!r}")

    n = len(records)
    lines: list[str] = []
    lines.append(f"# Chunk `{chunk_id}` — {n} iteration{'s' if n != 1 else ''}")
    lines.append("")
    lines.append("## Timeline")
    lines.append("| iter | gate state | files touched | first stderr / hint | exit_reason | sig |")
    lines.append("|------|------------|---------------|---------------------|-------------|-----|")

    prev_first = None
    for r in records:
        iter_num = r.get("iteration", "?")
        gate = _gate_state_summary(r)
        files = _files_touched_summary(r)
        first = _first_stderr_or_hint(r)
        annotated = first
        if prev_first is not None and first and first == prev_first:
            annotated = f"{first} (same)"
        prev_first = first if first else prev_first
        exit_reason = r.get("exit_reason", "in_progress")
        sig = _signature_short(r)
        lines.append(
            f"| {iter_num} | {gate} | {files} | {annotated} | {exit_reason} | {sig} |"
        )

    stall = _detect_stall(records)
    if stall is not None:
        sig, count, stall_iter = stall
        lines.append("")
        lines.append("## Stall signal")
        lines.append(
            f"Signature `{sig}` repeated {count} times — loop detected no-progress "
            f"at iteration {stall_iter}."
        )

    reflections = [(r.get("iteration", "?"), r.get("reflection")) for r in records
                   if r.get("reflection")]
    if reflections:
        lines.append("")
        lines.append("## Reflections")
        for iter_num, text in reflections:
            lines.append(f"### Iteration {iter_num}")
            lines.append(text)
            lines.append("")

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Skillgoid chunk iteration explainer")
    ap.add_argument("--chunk-id", required=True)
    ap.add_argument("--skillgoid-dir", type=Path, default=Path(".skillgoid"))
    args = ap.parse_args(argv)

    sg = args.skillgoid_dir.resolve()
    try:
        out = render_explain(sg, chunk_id=args.chunk_id)
    except FileNotFoundError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 1
    sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_explain_chunk.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Lint**

```bash
.venv/bin/ruff check scripts/explain_chunk.py tests/test_explain_chunk.py
```

Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add scripts/explain_chunk.py tests/test_explain_chunk.py
git commit -m "explain_chunk: per-chunk iteration timeline with stall signal (v0.12)"
```

---

## Task 4: `skills/explain/SKILL.md` thin wrapper

**Files:**
- Create: `skills/explain/SKILL.md`

- [ ] **Step 1: Write the skill**

Create `skills/explain/SKILL.md`:

```markdown
---
name: explain
description: Use when the user wants a compact post-mortem of a chunk — iteration-by-iteration timeline, stall signature, and verbatim reflections. Invokable as `/skillgoid:explain <chunk_id>`. Read-only; never modifies `.skillgoid/`.
---

# explain

## What this skill does

Reads every `.skillgoid/iterations/<chunk_id>-*.json` record for the named chunk and produces a compact markdown timeline + stall signal + verbatim reflection section. Use it to understand *why* a chunk behaved the way it did without manually opening each iteration JSON.

## When to use

- A chunk has stalled or succeeded after multiple iterations, and the user wants to see what changed (or didn't) across attempts.
- Before invoking `/skillgoid:unstick <chunk_id> "<hint>"`, to pick an informed hint.
- After a run, as part of a manual post-mortem before the automatic retrospective is written.

**NOT** for:
- In-flight wave overview across all chunks (use `/skillgoid:status` instead).
- Cross-project metrics (use `/skillgoid:stats` instead).
- Writing reflections or modifying iteration records (read-only).

## Inputs

- `chunk_id` (required) — must match a chunk in `.skillgoid/chunks.yaml`. The script glob-matches `.skillgoid/iterations/<chunk_id>-*.json`.
- Optional `skillgoid_dir` path override — defaults to `./.skillgoid`.

## Procedure

1. Invoke:
   ```bash
   python <plugin-root>/scripts/explain_chunk.py --chunk-id <chunk_id> [--skillgoid-dir .skillgoid]
   ```
2. The script emits a markdown report on stdout. Pass it through to the user unchanged. Do not re-interpret or re-synthesize.
3. If the script exits 1 with `"no iteration files for chunk <id>"`, either the chunk id is misspelled or the chunk has not run yet — surface the error to the user with the list of chunk ids from `.skillgoid/chunks.yaml` so they can pick a valid one.

## Output format

```markdown
# Chunk `<id>` — N iterations

## Timeline
| iter | gate state | files touched | first stderr / hint | exit_reason | sig |
| 1 | pytest_unit FAIL | src/parser.py | AssertionError in test_parse_iso | in_progress | a1b2c3d4 |
| 2 | pytest_unit FAIL | src/parser.py | AssertionError in test_parse_iso (same) | in_progress | a1b2c3d4 |
| 3 | pytest_unit FAIL | src/parser.py | AssertionError in test_parse_iso (same) | stalled | a1b2c3d4 |

## Stall signal
Signature `a1b2c3d4` repeated 3 times — loop detected no-progress at iteration 3.

## Reflections
### Iteration 1
<reflection text>
### Iteration 2
<reflection text>
### Iteration 3
<reflection text>
```

## What this skill does NOT do

- Synthesize new narrative — every line in the output is extracted deterministically from iteration JSON.
- Write to `.skillgoid/` or invoke any subagent.
- Cross-reference against blueprint.md or goal.md.
- Render HTML or fetch remote data.
```

- [ ] **Step 2: Verify the skill file is well-formed**

```bash
grep -n "^name: explain" skills/explain/SKILL.md
grep -n "explain_chunk.py" skills/explain/SKILL.md
```

Expected: both lines found.

- [ ] **Step 3: Commit**

```bash
git add skills/explain/SKILL.md
git commit -m "explain: thin wrapper skill for per-chunk iteration timeline (v0.12)"
```

---

## Task 5: Auto-partial-retrospective — `skills/build/SKILL.md` edit + bundle test

**Files:**
- Modify: `skills/build/SKILL.md`
- Create: `tests/test_auto_retrospect_trigger.py`

The edit adds an auto-retrospect step that fires on every terminal state (success, stalled, budget_exhausted) for the `build "<goal>"` and `build resume` invocation modes, with documented skip conditions. The bundle test grep-verifies the prose edit AND locks in the `_outcome()` classification in `scripts/metrics_append.py` for `partial` (stall) and `abandoned` (empty-iterations) cases — the two scenarios v0.10 H9 did not cover.

### Edit A: `skills/build/SKILL.md` — auto-retrospect step

Current state around the retrospect phase (lines 207-213):

```
### Dispatch — Retrospect-only

8. Invoke `skillgoid:retrospect` directly. Used when the user abandons or finalizes early.

### Retrospect phase

9. Invoke `skillgoid:retrospect` once integration (if any) passes or is skipped.
```

The problem: step 9 is only reached on the success/integration-pass path. Stall and budget-exhaust exits from step 3f and step 4h return to the user without reaching step 9, so no retrospective is written.

The fix: add a new step 9 that always runs on any terminal state for `build "<goal>"` / `build resume`, with the existing step 9 becoming a skip-to-10 fall-through (renumber).

- [ ] **Step 1: Replace step 9 with the auto-retrospect section**

Open `skills/build/SKILL.md`. Find the block:

```
### Retrospect phase

9. Invoke `skillgoid:retrospect` once integration (if any) passes or is skipped.
```

Replace it with:

```
### Retrospect phase (auto-invoked on every terminal state since v0.12)

9. **Auto-retrospect trigger.** After every terminal state reached inside the `build "<goal>"` or `build resume` invocation modes — that is, after step 3f stops the wave on a `stalled` / `budget_exhausted` failure, after step 4h exits with integration still failing, OR after step 4f succeeds with integration passing — invoke `skillgoid:retrospect` exactly once before surfacing the final summary to the user.

   **Skip conditions (do NOT auto-invoke retrospect):**
   - Invocation mode is `build retrospect-only` (step 8 already invokes retrospect — avoids double-call).
   - Invocation mode is `build status` (read-only subcommand, no loop ran, no terminal state).
   - `.skillgoid/iterations/` is absent or empty (clarify/plan/feasibility phase aborted before any loop dispatch — nothing to retrospect on).

   **Slug passed to `metrics_append.py`:** use `$(basename "$(pwd)")` (same convention as `/skillgoid:status`). This ensures a metrics line is written for every terminal run, not only the success path. `metrics.jsonl` is append-only — a subsequent `build resume` after an unstick will append a fresh line with the updated outcome; dedup-by-slug display is a v0.13+ concern.

   **Outcome classification is unchanged:** `retrospect` delegates to `scripts/metrics_append.py`, which already returns `success` / `partial` / `abandoned` based on the iteration set (locked in by `tests/test_v10_bundle.py::test_h9_retrospect_only_partial_outcome` and v0.12's `tests/test_auto_retrospect_trigger.py`).

10. Surface the final summary to the user (same content as before: what was built, where artifacts live, and for failure paths, the three-option recovery menu from step 3f or step 4h).
```

- [ ] **Step 2: Verify the edit landed**

```bash
grep -n "Auto-retrospect trigger" skills/build/SKILL.md
grep -n "Skip conditions" skills/build/SKILL.md
grep -n "basename.*pwd" skills/build/SKILL.md
```

Expected: all three grep calls return matches.

- [ ] **Step 3: Write the failing bundle test**

Create `tests/test_auto_retrospect_trigger.py`:

```python
"""Bundle test for v0.12 auto-partial-retrospective.

Two layers:
  1. Grep-verify that skills/build/SKILL.md documents the auto-retrospect
     trigger and the three skip conditions. build orchestration is prose, so
     prose verification IS the contract.
  2. Lock in _outcome() classification in scripts/metrics_append.py for the
     two scenarios v0.10 H9 did NOT cover:
        - All-success → outcome='success'
        - Empty iterations → outcome='abandoned'
     (Partial from budget_exhausted already locked in by v0.10 H9.)

If the prose grep ever fails, the auto-retrospect trigger has regressed.
If the classification tests ever fail, retrospect output would mislead
users about run outcomes.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD_SKILL = ROOT / "skills" / "build" / "SKILL.md"
METRICS_CLI = [sys.executable, str(ROOT / "scripts" / "metrics_append.py")]


def test_build_skill_documents_auto_retrospect_trigger():
    """The step 9 auto-retrospect section must be present verbatim."""
    text = BUILD_SKILL.read_text()
    assert "Auto-retrospect trigger" in text, \
        "skills/build/SKILL.md missing 'Auto-retrospect trigger' heading"
    assert "stalled` / `budget_exhausted" in text or "stalled / budget_exhausted" in text, \
        "auto-retrospect step must mention stalled/budget_exhausted terminal states"


def test_build_skill_documents_all_three_skip_conditions():
    """All three skip conditions must be documented."""
    text = BUILD_SKILL.read_text()
    assert "retrospect-only" in text and "already invokes retrospect" in text, \
        "retrospect-only skip condition missing"
    assert "build status" in text and "no loop ran" in text, \
        "build status skip condition missing"
    assert "iterations/` is absent or empty" in text \
        or "iterations/ is absent or empty" in text, \
        "empty-iterations skip condition missing"


def test_build_skill_documents_slug_source():
    """The slug passed to metrics_append.py must be documented as cwd basename."""
    text = BUILD_SKILL.read_text()
    assert "basename" in text and "pwd" in text, \
        "slug source (basename of cwd) not documented in auto-retrospect step"


def _write_iter(iters_dir: Path, filename: str, *, chunk_id: str, iteration: int,
                exit_reason: str) -> None:
    iters_dir.mkdir(parents=True, exist_ok=True)
    (iters_dir / filename).write_text(json.dumps({
        "iteration": iteration,
        "chunk_id": chunk_id,
        "started_at": "2026-04-18T12:00:00Z",
        "ended_at": "2026-04-18T12:05:00Z",
        "gate_report": {"passed": exit_reason == "success", "results": []},
        "exit_reason": exit_reason,
        "failure_signature": "0" * 16,
    }))


def _write_minimal_criteria_and_chunks(sg: Path, chunk_ids: list[str]) -> None:
    chunks_yaml = "chunks:\n" + "".join(
        f"  - id: {cid}\n    paths: [src/{cid}.py]\n" for cid in chunk_ids
    )
    (sg / "chunks.yaml").write_text(chunks_yaml)
    (sg / "criteria.yaml").write_text(
        "language: python\n"
        "gates:\n"
        "  - id: pytest_unit\n    type: pytest\n    args: []\n"
    )


def test_outcome_success_when_all_chunks_succeed(tmp_path, monkeypatch):
    """Auto-retrospect on happy path → metrics line records outcome=success."""
    monkeypatch.setenv("HOME", str(tmp_path))
    sg = tmp_path / "project" / ".skillgoid"
    iters = sg / "iterations"
    iters.mkdir(parents=True)
    _write_minimal_criteria_and_chunks(sg, ["a", "b"])
    _write_iter(iters, "a-001.json", chunk_id="a", iteration=1, exit_reason="success")
    _write_iter(iters, "b-001.json", chunk_id="b", iteration=1, exit_reason="success")

    result = subprocess.run(
        METRICS_CLI + ["--skillgoid-dir", str(sg), "--slug", "happy-slug"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr

    metrics_path = tmp_path / ".claude" / "skillgoid" / "metrics.jsonl"
    assert metrics_path.exists()
    entry = json.loads(metrics_path.read_text().strip().splitlines()[-1])
    assert entry["outcome"] == "success", \
        f"expected outcome=success, got {entry['outcome']!r}"
    assert entry["slug"] == "happy-slug"


def test_outcome_partial_when_a_chunk_stalls(tmp_path, monkeypatch):
    """Auto-retrospect on stall path → metrics line records outcome=partial.

    Mirrors v0.10 H9 (which covered budget_exhausted); this case covers stalled.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    sg = tmp_path / "project" / ".skillgoid"
    iters = sg / "iterations"
    iters.mkdir(parents=True)
    _write_minimal_criteria_and_chunks(sg, ["a", "b"])
    _write_iter(iters, "a-001.json", chunk_id="a", iteration=1, exit_reason="success")
    _write_iter(iters, "b-001.json", chunk_id="b", iteration=1, exit_reason="in_progress")
    _write_iter(iters, "b-002.json", chunk_id="b", iteration=2, exit_reason="in_progress")
    _write_iter(iters, "b-003.json", chunk_id="b", iteration=3, exit_reason="stalled")

    result = subprocess.run(
        METRICS_CLI + ["--skillgoid-dir", str(sg), "--slug", "stall-slug"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr

    metrics_path = tmp_path / ".claude" / "skillgoid" / "metrics.jsonl"
    entry = json.loads(metrics_path.read_text().strip().splitlines()[-1])
    assert entry["outcome"] == "partial", \
        f"expected outcome=partial for stall, got {entry['outcome']!r}"
    assert entry["stall_count"] == 1
    assert entry["slug"] == "stall-slug"


def test_outcome_abandoned_on_empty_iterations(tmp_path, monkeypatch):
    """Empty-iterations skip condition: metrics_append still runs cleanly but
    records outcome=abandoned. (The build orchestrator SHOULD skip auto-invoke,
    but if it were ever invoked with empty state, the classification must not
    mis-label the run as 'success'.)"""
    monkeypatch.setenv("HOME", str(tmp_path))
    sg = tmp_path / "project" / ".skillgoid"
    (sg / "iterations").mkdir(parents=True)
    _write_minimal_criteria_and_chunks(sg, ["a"])

    result = subprocess.run(
        METRICS_CLI + ["--skillgoid-dir", str(sg), "--slug", "empty-slug"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr

    metrics_path = tmp_path / ".claude" / "skillgoid" / "metrics.jsonl"
    entry = json.loads(metrics_path.read_text().strip().splitlines()[-1])
    assert entry["outcome"] == "abandoned", \
        f"expected outcome=abandoned for empty iterations, got {entry['outcome']!r}"
    assert entry["total_iterations"] == 0
    assert entry["slug"] == "empty-slug"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_auto_retrospect_trigger.py -v
```

Expected: all 6 tests PASS. The 3 grep tests confirm the prose edit from Step 1 landed; the 3 classification tests lock in `_outcome()` behavior for every possible final state.

- [ ] **Step 5: Lint**

```bash
.venv/bin/ruff check tests/test_auto_retrospect_trigger.py
```

Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add skills/build/SKILL.md tests/test_auto_retrospect_trigger.py
git commit -m "build: auto-invoke retrospect on every terminal state (v0.12)"
```

---

## Task 6: `skills/unstick/SKILL.md` — `--dry-run` prose branch

**Files:**
- Modify: `skills/unstick/SKILL.md`

The current dispatch step 4 in `skills/unstick/SKILL.md` reads:

```
4. **Dispatch a fresh chunk subagent** — same dispatch pattern as `build` step 3c, with TWO differences:
   - Inject the `<hint>` into the chunk prompt's `## Integration failure context (populated on integration auto-repair, empty otherwise)` slot (repurpose the v0.2 slot — it was designed for exactly this kind of mid-flight hint injection).
   - Prefix the hint with: `"UNSTICK HINT (from human operator): "` so the subagent knows the source.
```

We add a `--dry-run` branch before step 4's dispatch that prints the constructed prompt without dispatching. The same `UNSTICK HINT (from human operator): ` prefix applies so dry-run output matches real dispatch byte-for-byte apart from the banner.

- [ ] **Step 1: Update the Inputs section**

Find:

```
## Inputs

- `chunk_id` — must match an entry in `.skillgoid/chunks.yaml`.
- `hint` — a single sentence. Shorter is better.
```

Replace with:

```
## Inputs

- `chunk_id` — must match an entry in `.skillgoid/chunks.yaml`.
- `hint` — a single sentence. Shorter is better.
- `--dry-run` (optional flag) — preview the constructed subagent prompt without dispatching. Attempt counter is not reset, no iteration record is written, and unstick budget is not consumed. Useful for validating the hint before spending it.

**Invocation forms:**
- Normal: `/skillgoid:unstick <chunk_id> "<hint>"`
- Dry-run: `/skillgoid:unstick <chunk_id> --dry-run "<hint>"`
```

- [ ] **Step 2: Replace step 4 with the dry-run branch**

Find the current step 4:

```
4. **Dispatch a fresh chunk subagent** — same dispatch pattern as `build` step 3c, with TWO differences:
   - Inject the `<hint>` into the chunk prompt's `## Integration failure context (populated on integration auto-repair, empty otherwise)` slot (repurpose the v0.2 slot — it was designed for exactly this kind of mid-flight hint injection).
   - Prefix the hint with: `"UNSTICK HINT (from human operator): "` so the subagent knows the source.
```

Replace with:

```
4. **Construct the chunk subagent prompt** — same dispatch-prep pattern as `build` step 3c, with TWO differences:
   - Inject the `<hint>` into the chunk prompt's `## Integration failure context (populated on integration auto-repair, empty otherwise)` slot (repurpose the v0.2 slot — it was designed for exactly this kind of mid-flight hint injection).
   - Prefix the hint with: `"UNSTICK HINT (from human operator): "` so the subagent knows the source.

   **If `--dry-run` was passed:** do NOT dispatch the subagent. Instead, print the full constructed prompt to stdout wrapped in a banner:

   ```
   --- begin dispatched prompt ---
   <full prompt including UNSTICK HINT (from human operator): <hint>>
   --- end dispatched prompt ---
   ```

   Return immediately after printing. Do NOT reset the attempt counter (step 5 is skipped), do NOT write an iteration record (step 6 is skipped), do NOT count against the unstick budget from step 3 — a dry-run is a read-only preview.

   **Otherwise (no `--dry-run`):** dispatch the subagent with the constructed prompt and proceed to step 5.
```

- [ ] **Step 3: Update the Output section**

Find:

```
## Output

On success:
```
unstick: chunk <chunk_id> re-dispatched with hint.
Subagent returned: <exit_reason>, iterations_used: N, gates: <summary>
```

On over-budget:
```
unstick: chunk <chunk_id> has already been unstuck 3 times. Break out
with /skillgoid:build retrospect-only or continue manually.
```
```

Replace with:

```
## Output

On success (normal dispatch):
```
unstick: chunk <chunk_id> re-dispatched with hint.
Subagent returned: <exit_reason>, iterations_used: N, gates: <summary>
```

On `--dry-run`:
```
--- begin dispatched prompt ---
<full constructed chunk subagent prompt, including the UNSTICK HINT prefix>
--- end dispatched prompt ---
unstick: dry-run complete. No dispatch, no iteration record, no budget consumed.
```

On over-budget:
```
unstick: chunk <chunk_id> has already been unstuck 3 times. Break out
with /skillgoid:build retrospect-only or continue manually.
```
```

- [ ] **Step 4: Verify the edits landed**

```bash
grep -n "\-\-dry-run" skills/unstick/SKILL.md
grep -n "UNSTICK HINT (from human operator)" skills/unstick/SKILL.md
grep -n "begin dispatched prompt" skills/unstick/SKILL.md
grep -n "no budget consumed" skills/unstick/SKILL.md
```

Expected: every grep call returns at least one match. The `--dry-run` string must appear in the Inputs section and the Output section; the `UNSTICK HINT` prefix must still appear (unchanged from pre-v0.12); the banner and "no budget consumed" text must both be present.

- [ ] **Step 5: Manual smoke test against the v0.11 integration-retry fixture**

This is the testability fallback from the spec. Scripted automated testing of the dry-run branch is deferred to v0.13+ (when `scripts/unstick_prompt.py` may be extracted to deduplicate prompt construction across dry-run and dispatch paths).

From the plugin root:

```bash
cp -a tests/fixtures/integration-retry/project /tmp/skillgoid-unstick-smoke
cd /tmp/skillgoid-unstick-smoke
ls .skillgoid/iterations/
# Expected: lib_a-001.json and lib_b-001.json (pre-seeded by the fixture)
```

Invoke `/skillgoid:unstick lib_b --dry-run "check that fn_a_typo in src/lib_b.sh should be fn_a"` in a Claude Code session cwd'd at `/tmp/skillgoid-unstick-smoke`. Confirm:

- The session prints the constructed prompt wrapped in `--- begin dispatched prompt ---` / `--- end dispatched prompt ---`.
- The prompt contains `UNSTICK HINT (from human operator): check that fn_a_typo in src/lib_b.sh should be fn_a`.
- `ls .skillgoid/iterations/` still shows only `lib_a-001.json` and `lib_b-001.json` — no new iteration record was written.
- No subagent was actually dispatched.

Cleanup:

```bash
rm -rf /tmp/skillgoid-unstick-smoke
```

If the smoke test surfaces any deviation (e.g., prompt missing the banner, iteration record created, subagent dispatched), return to Step 2 and fix the prose before committing.

- [ ] **Step 6: Commit**

```bash
git add skills/unstick/SKILL.md
git commit -m "unstick: --dry-run preview branch, no dispatch no budget (v0.12)"
```

---

## Task 7: Full suite + lint + tag v0.12.0

**Files:** None (verification + tag only)

- [ ] **Step 1: Run the full test suite**

```bash
.venv/bin/pytest -v
```

Expected: all tests pass with no regressions. Count should be ≥ 192 (the v0.11.0 baseline) plus roughly 21 new tests from this release (8 from status_reader + 7 from explain_chunk + 6 from auto_retrospect_trigger).

- [ ] **Step 2: Lint the full codebase**

```bash
.venv/bin/ruff check .
```

Expected: `All checks passed!`

- [ ] **Step 3: Confirm success criteria from spec**

Run each grep/test independently and confirm the documented contracts:

```bash
# 1. status_reader tests pass
.venv/bin/pytest tests/test_status_reader.py -v

# 2. explain_chunk tests pass
.venv/bin/pytest tests/test_explain_chunk.py -v

# 3. auto_retrospect_trigger tests pass (grep + classification)
.venv/bin/pytest tests/test_auto_retrospect_trigger.py -v

# 4. both new skill files exist and shell out to the right scripts
test -f skills/status/SKILL.md && grep -q "status_reader.py" skills/status/SKILL.md
test -f skills/explain/SKILL.md && grep -q "explain_chunk.py" skills/explain/SKILL.md

# 5. build skill has auto-retrospect step
grep -q "Auto-retrospect trigger" skills/build/SKILL.md

# 6. unstick skill has --dry-run branch
grep -q "\-\-dry-run" skills/unstick/SKILL.md
grep -q "begin dispatched prompt" skills/unstick/SKILL.md
```

Each command must exit 0. If any fails, return to the corresponding task and fix before proceeding.

- [ ] **Step 4: Tag v0.12.0**

```bash
git tag v0.12.0
```

Follow the v0.10.0 / v0.11.0 pattern: tag the final commit that includes any post-code polish (README update, if any). If a README update follows in a subsequent commit, move the tag forward with `git tag -f v0.12.0` to match the v0.11.0 precedent (tag was initially placed at the code commit, then moved to the README-update commit so `git describe` on main reflects the user-visible release).

---

## Self-review

**Spec coverage check:**

| Spec requirement | Task that covers it |
|---|---|
| `scripts/status_reader.py` with Path-based CLI and markdown output | Task 1 |
| Status output: chunk table + wave + gate truncation + integration section | Task 1 (tests lock in each) |
| `scripts/explain_chunk.py` with `--chunk-id` argument and markdown output | Task 3 |
| Explain output: timeline + (same) annotation + stall signal + reflections | Task 3 (tests lock in each) |
| `skills/status/SKILL.md` thin wrapper, stdout passthrough | Task 2 |
| `skills/explain/SKILL.md` thin wrapper, stdout passthrough | Task 4 |
| Auto-retrospect invoked on every terminal state for `build "<goal>"` / `build resume` | Task 5 Edit A |
| Skip conditions: `retrospect-only`, `status`, empty-iterations | Task 5 Edit A + 3 grep tests |
| Slug source = `$(basename "$(pwd)")` for auto-invoke path | Task 5 Edit A + slug-source grep test |
| Outcome classification lock-in for success / partial / abandoned | Task 5 (3 classification tests) |
| `skills/unstick/SKILL.md` supports `--dry-run` — preview only, no dispatch, no budget | Task 6 |
| Unstick dry-run testability: grep + manual smoke test | Task 6 Step 4 + Step 5 |
| Full test suite still passes | Task 7 Step 1 |
| Lint clean | Task 7 Step 2 |
| Tag v0.12.0 | Task 7 Step 4 |

Every spec requirement maps to at least one task. No gaps.

**Placeholder scan:** None found. Every step contains concrete file paths, runnable commands, and complete code bodies. No "TBD", no "implement later", no "similar to Task N" with omitted detail.

**Type / name consistency:**
- `render_status(sg: Path, project_label: str) -> str` — used in `scripts/status_reader.py` body, test imports, and CLI main.
- `render_explain(sg: Path, chunk_id: str) -> str` — used in `scripts/explain_chunk.py` body, test imports, and CLI main.
- CLI flag names consistent across scripts: `--skillgoid-dir` (both), `--chunk-id` (explain_chunk only, and the pre-existing `verify_iteration_written.py` uses the same name).
- Exit codes match contract across both scripts: 0 on success, 1 on "not a Skillgoid project" / "no iteration files".
- Failure-signature short form consistently rendered as first 8 chars; `—` (em-dash) for missing signature matches existing convention in status_reader's "pending" column.
- Grep assertions in Task 5 and Task 6 use the exact strings the prose edits introduce: `"Auto-retrospect trigger"`, `"Skip conditions"`, `"--dry-run"`, `"begin dispatched prompt"`, `"no budget consumed"` — all appear verbatim in the text each task writes.
- Test file names match spec exactly: `tests/test_status_reader.py`, `tests/test_explain_chunk.py`, `tests/test_auto_retrospect_trigger.py`.
- Slug convention (`Path.cwd().name` in Python scripts / `$(basename "$(pwd)")` in skill prose) is consistent with spec section 1 and spec section 3.

**Scope check:** All four deliverables from the spec are present. No out-of-scope work (no schema changes, no retrospect-skill edits, no new hooks, no dashboards, no AI-synthesized narratives). Matches the "What this does NOT change" list in the spec verbatim.
