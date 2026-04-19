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


def test_bare_gate_report_without_wrapper(tmp_path):
    # File IS the gate_report directly (no integration attempt wrapper)
    # The fallback attempt.get("gate_report", attempt) should handle this
    bare_report = _write_attempt(tmp_path, {
        "passed": False,
        "results": [{"gate_id": "g", "passed": False, "stdout": "", "stderr": "src/lib_c.py error"}],
    })
    chunks = _write_chunks(tmp_path, [("lib_c", ["src/lib_c.py"])])

    result = identify_suspect(bare_report, chunks)

    assert result["suspect_chunk_id"] == "lib_c"


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
