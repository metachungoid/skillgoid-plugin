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
    _write_iter(iters, "parser-003.json", _make_valid_record("parser", 3))
    # Force older to be 10s in the past; parser-003.json retains the latest mtime
    old_mtime = older.stat().st_mtime - 10
    os.utime(older, (old_mtime, old_mtime))

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
