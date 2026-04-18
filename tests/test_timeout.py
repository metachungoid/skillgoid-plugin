"""Adapter timeout handling — gates that exceed their timeout fail with a
clean GateResult instead of hanging the adapter forever.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "scripts" / "measure_python.py"


def run_cli(criteria_yaml: str, project_path: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(ADAPTER), "--project", str(project_path), "--criteria-stdin"],
        input=criteria_yaml,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,  # test harness: kill if adapter itself hangs
    )
    return json.loads(result.stdout)


def test_gate_under_timeout_passes(tmp_path: Path):
    criteria = """
gates:
  - id: fast
    type: run-command
    command: ["echo", "ok"]
    expect_exit: 0
    timeout: 5
"""
    report = run_cli(criteria, tmp_path)
    assert report["passed"] is True
    assert report["results"][0]["passed"] is True


def test_gate_over_timeout_fails_cleanly(tmp_path: Path):
    # `sleep 10` vs. `timeout: 1` — must fail fast with a clear hint.
    criteria = """
gates:
  - id: slow
    type: run-command
    command: ["sleep", "10"]
    timeout: 1
"""
    report = run_cli(criteria, tmp_path)
    assert report["passed"] is False
    result = report["results"][0]
    assert result["passed"] is False
    assert "timed out" in result["hint"].lower()
