"""Gate `env:` field — merged into subprocess env at dispatch."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "scripts" / "measure_python.py"


def run_cli(criteria: str, project: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(ADAPTER), "--project", str(project), "--criteria-stdin"],
        input=criteria, capture_output=True, text=True, check=False, timeout=30,
    )
    return json.loads(result.stdout)


def test_gate_env_overrides_for_subprocess(tmp_path: Path):
    """A gate env: key should be visible to the subprocess via its environment."""
    criteria = """
gates:
  - id: check_env
    type: run-command
    command: ["sh", "-c", "echo $MYVAR"]
    expect_exit: 0
    expect_stdout_match: "hello-from-env"
    env:
      MYVAR: "hello-from-env"
"""
    report = run_cli(criteria, tmp_path)
    assert report["passed"] is True
    assert "hello-from-env" in report["results"][0]["stdout"]


def test_gate_env_overrides_outer_env(tmp_path: Path, monkeypatch):
    """Gate env: value should win against a pre-existing value in os.environ."""
    monkeypatch.setenv("MYVAR", "outer-value")
    criteria = """
gates:
  - id: check_override
    type: run-command
    command: ["sh", "-c", "echo $MYVAR"]
    expect_exit: 0
    expect_stdout_match: "inner-value"
    env:
      MYVAR: "inner-value"
"""
    report = run_cli(criteria, tmp_path)
    assert report["passed"] is True
    assert "inner-value" in report["results"][0]["stdout"]


def test_cli_command_runs_with_env(tmp_path: Path):
    """cli-command-runs also honors env:."""
    criteria = """
gates:
  - id: cli_with_env
    type: cli-command-runs
    command: ["sh", "-c", "echo $PYTHONPATH"]
    expect_exit: 0
    expect_stdout_match: "/custom/path"
    env:
      PYTHONPATH: "/custom/path"
"""
    report = run_cli(criteria, tmp_path)
    assert report["passed"] is True


def test_skillgoid_python_env_is_exported(tmp_path: Path):
    """SKILLGOID_PYTHON should be set to sys.executable in the gate subprocess."""
    criteria = """
gates:
  - id: check
    type: run-command
    command: ["sh", "-c", "echo $SKILLGOID_PYTHON"]
    expect_exit: 0
"""
    report = run_cli(criteria, tmp_path)
    assert report["passed"] is True
    stdout = report["results"][0]["stdout"].strip()
    assert stdout.endswith("python") or stdout.endswith("python3") or "/python" in stdout, \
        f"expected python path, got: {stdout!r}"


def test_shell_string_uses_skillgoid_python_successfully(tmp_path: Path):
    """A bash -c command referencing $SKILLGOID_PYTHON should run the right interpreter."""
    criteria = """
gates:
  - id: check
    type: run-command
    command: ["bash", "-c", "$SKILLGOID_PYTHON -c 'print(42)'"]
    expect_exit: 0
    expect_stdout_match: "42"
"""
    report = run_cli(criteria, tmp_path)
    assert report["passed"] is True
    assert "42" in report["results"][0]["stdout"]
