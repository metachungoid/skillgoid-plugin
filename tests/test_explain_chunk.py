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
