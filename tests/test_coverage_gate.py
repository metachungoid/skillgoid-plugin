"""Coverage gate — pytest-cov-based floor check (Task 2) and baseline
regression check (Task 3, not this task)."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "scripts" / "measure_python.py"
PASSING = ROOT / "tests" / "fixtures" / "passing-project"
LOW_COV = ROOT / "tests" / "fixtures" / "low-coverage-project"


def run_cli(criteria_yaml: str, project_path: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(ADAPTER), "--project", str(project_path), "--criteria-stdin"],
        input=criteria_yaml,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    return json.loads(result.stdout)


def test_coverage_gate_passes_when_above_floor():
    # passing-project has one function (add), one test (test_add) → 100% cov.
    criteria = """
gates:
  - id: cov
    type: coverage
    target: mypkg
    min_percent: 80
"""
    report = run_cli(criteria, PASSING)
    assert report["passed"] is True
    assert report["results"][0]["gate_id"] == "cov"
    # Current percent stored in stdout for later iterations to read as baseline
    assert "coverage:" in report["results"][0]["stdout"].lower()
    assert "100" in report["results"][0]["stdout"]


def test_coverage_gate_fails_below_floor():
    # low-coverage-project has mostly-untested code.
    criteria = """
gates:
  - id: cov
    type: coverage
    target: mypkg
    min_percent: 80
"""
    report = run_cli(criteria, LOW_COV)
    assert report["passed"] is False
    hint = report["results"][0]["hint"].lower()
    assert "below floor" in hint or "coverage" in hint
    assert "80" in report["results"][0]["hint"]


def test_coverage_gate_handles_missing_pytest_cov(tmp_path: Path):
    # In a completely empty project, pytest-cov will have no tests to run.
    # The handler should fail cleanly (no-data, not crash).
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="empty"\nversion="0.0.1"\nrequires-python=">=3.11"\n'
    )
    criteria = """
gates:
  - id: cov
    type: coverage
    target: empty
    min_percent: 80
"""
    report = run_cli(criteria, tmp_path)
    # Either coverage=0% fail, or a clean "no coverage data" fail.
    assert report["passed"] is False
    assert report["results"][0]["gate_id"] == "cov"
