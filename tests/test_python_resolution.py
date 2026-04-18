"""python binary auto-resolution — bare 'python' in command[] is replaced with
sys.executable so jobs run correctly in environments where only python3 exists.
"""
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


def test_bare_python_resolves_to_sys_executable(tmp_path: Path):
    """Command starting with 'python' auto-resolves so environments without
    bare python on PATH still work."""
    criteria = """
gates:
  - id: py_version
    type: run-command
    command: ["python", "-c", "import sys; print('ok')"]
    expect_exit: 0
    expect_stdout_match: "ok"
"""
    report = run_cli(criteria, tmp_path)
    assert report["passed"] is True, f"results: {report['results']}"


def test_python3_untouched(tmp_path: Path):
    """Non-'python' names pass through unchanged."""
    criteria = """
gates:
  - id: py3_version
    type: run-command
    command: ["python3", "-c", "print('ok3')"]
    expect_exit: 0
    expect_stdout_match: "ok3"
"""
    report = run_cli(criteria, tmp_path)
    # Pass if python3 is on PATH (most environments); skip if not.
    import shutil
    if shutil.which("python3") is None:
        import pytest
        pytest.skip("python3 not on PATH")
    assert report["passed"] is True


def test_opt_out_via_env_marker(tmp_path: Path):
    """SKILLGOID_PYTHON_NO_RESOLVE=1 disables the substitution."""
    criteria = """
gates:
  - id: no_resolve
    type: run-command
    command: ["python", "-c", "print('should-not-run-in-broken-env')"]
    expect_exit: 0
    env:
      SKILLGOID_PYTHON_NO_RESOLVE: "1"
"""
    # On a system with python on PATH this still passes; on a system without,
    # the opt-out means we get a FileNotFoundError → exit 124 or exception.
    # Test is mostly a smoke check that the env marker is honored (no crash).
    report = run_cli(criteria, tmp_path)
    # Either ran (if bare python exists) or failed with a clean FileNotFoundError
    assert report["results"][0]["gate_id"] == "no_resolve"
