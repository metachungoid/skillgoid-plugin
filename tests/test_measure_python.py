import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = [sys.executable, str(ROOT / "scripts" / "measure_python.py")]


def run_cli(criteria_yaml: str, project_path: Path) -> dict:
    result = subprocess.run(
        CLI + ["--project", str(project_path), "--criteria-stdin"],
        input=criteria_yaml,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode in (0, 1, 2), f"stderr: {result.stderr}"
    return json.loads(result.stdout)


def test_run_command_gate_passing(tmp_path: Path):
    criteria = """
gates:
  - id: echo
    type: run-command
    command: ["echo", "hello"]
    expect_exit: 0
"""
    report = run_cli(criteria, tmp_path)
    assert report["passed"] is True
    assert len(report["results"]) == 1
    assert report["results"][0]["gate_id"] == "echo"
    assert report["results"][0]["passed"] is True


def test_run_command_gate_failing(tmp_path: Path):
    criteria = """
gates:
  - id: fail
    type: run-command
    command: ["false"]
    expect_exit: 0
"""
    report = run_cli(criteria, tmp_path)
    assert report["passed"] is False
    result = report["results"][0]
    assert result["passed"] is False
    assert "exit=1" in result["hint"] or "expected 0" in result["hint"]
    assert result["stderr"] == ""  # `false` emits nothing


def test_missing_command_field(tmp_path: Path):
    criteria = """
gates:
  - id: bad
    type: run-command
"""
    report = run_cli(criteria, tmp_path)
    assert report["passed"] is False
    assert "no command specified" in report["results"][0]["hint"]
    assert report["results"][0]["stderr"] == ""


def test_unsupported_gate_type(tmp_path: Path):
    criteria = """
gates:
  - id: mystery
    type: unknown-gate
"""
    report = run_cli(criteria, tmp_path)
    assert report["passed"] is False
    assert "unsupported gate type" in report["results"][0]["hint"]
    assert report["results"][0]["stderr"] == ""


def test_malformed_yaml_returns_error_json(tmp_path: Path):
    # Intentionally broken YAML triggers the exit-2 internal-error path
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "measure_python.py"),
         "--project", str(tmp_path), "--criteria-stdin"],
        input=": : :",  # malformed
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    report = json.loads(result.stdout)
    assert report["passed"] is False
    assert "error" in report


PASSING = ROOT / "tests" / "fixtures" / "passing-project"
FAILING = ROOT / "tests" / "fixtures" / "failing-project"


def test_pytest_gate_passing():
    criteria = """
gates:
  - id: pytest
    type: pytest
    args: ["-q"]
"""
    report = run_cli(criteria, PASSING)
    assert report["passed"] is True
    assert report["results"][0]["gate_id"] == "pytest"


def test_pytest_gate_failing():
    criteria = """
gates:
  - id: pytest
    type: pytest
    args: ["-q"]
"""
    report = run_cli(criteria, FAILING)
    assert report["passed"] is False
    assert "FAIL" in report["results"][0]["stdout"] or "failed" in report["results"][0]["stdout"].lower()


def test_ruff_gate_passing():
    criteria = """
gates:
  - id: lint
    type: ruff
    args: ["check", "--isolated", "."]
"""
    report = run_cli(criteria, PASSING)
    assert report["passed"] is True


def test_ruff_gate_failing():
    criteria = """
gates:
  - id: lint
    type: ruff
    args: ["check", "--isolated", "."]
"""
    report = run_cli(criteria, FAILING)
    assert report["passed"] is False
    stdout_lower = report["results"][0]["stdout"].lower()
    assert "os" in stdout_lower or "unused" in stdout_lower or "f401" in stdout_lower


def test_mypy_gate_on_passing_fixture():
    criteria = """
gates:
  - id: types
    type: mypy
    args: ["src"]
"""
    report = run_cli(criteria, PASSING)
    assert report["passed"] is True


def test_import_clean_passes():
    criteria = """
gates:
  - id: imp
    type: import-clean
    module: mypkg
"""
    report = run_cli(criteria, PASSING)
    assert report["passed"] is True


def test_import_clean_fails_on_nonexistent_module(tmp_path: Path):
    criteria = """
gates:
  - id: imp
    type: import-clean
    module: does_not_exist_xyz
"""
    report = run_cli(criteria, tmp_path)
    assert report["passed"] is False


def test_cli_command_runs_passing(tmp_path: Path):
    criteria = """
gates:
  - id: cli
    type: cli-command-runs
    command: ["echo", "hello world"]
    expect_exit: 0
    expect_stdout_match: "hello"
"""
    report = run_cli(criteria, tmp_path)
    assert report["passed"] is True


def test_cli_command_runs_fails_on_stdout_mismatch(tmp_path: Path):
    criteria = """
gates:
  - id: cli
    type: cli-command-runs
    command: ["echo", "goodbye"]
    expect_exit: 0
    expect_stdout_match: "hello"
"""
    report = run_cli(criteria, tmp_path)
    assert report["passed"] is False
    assert "stdout" in report["results"][0]["hint"].lower()
