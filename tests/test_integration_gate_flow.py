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
    # doesn't distinguish. We simulate by naming the gate id "integration_*".
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
