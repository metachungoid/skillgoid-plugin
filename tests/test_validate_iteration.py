"""Tests for scripts/validate_iteration.py — iteration JSON schema validator."""
import json
from pathlib import Path

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
