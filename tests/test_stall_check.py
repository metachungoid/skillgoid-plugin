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
