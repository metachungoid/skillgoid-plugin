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
    assert result.returncode in (0, 1), f"stderr: {result.stderr}"
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
    assert report["results"][0]["passed"] is False
