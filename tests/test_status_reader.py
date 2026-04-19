"""Tests for scripts/status_reader.py.

status_reader is read-only: it never mutates .skillgoid/ state. These tests
exercise the pure rendering logic plus the CLI end-to-end via tmp_path.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.status_reader import render_status

ROOT = Path(__file__).resolve().parents[1]
CLI = [sys.executable, str(ROOT / "scripts" / "status_reader.py")]


def _cli_env() -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    return env


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
        capture_output=True, text=True, env=_cli_env(),
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
        capture_output=True, text=True, cwd=tmp_path, env=_cli_env(),
    )
    assert result.returncode == 0
    assert "# Skillgoid status" in result.stdout
    assert "| one" in result.stdout
