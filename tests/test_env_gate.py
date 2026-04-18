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


def test_pytest_honors_env_pythonpath(tmp_path: Path):
    """F17: gate-level env: PYTHONPATH should win over the hardcoded <project>/src."""
    # Lay out a package under py/src/ (non-standard location)
    pkg = tmp_path / "py" / "src" / "mypkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("VAL = 42\n")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_it.py").write_text(
        "from mypkg import VAL\n"
        "def test_val(): assert VAL == 42\n"
    )
    criteria = """
gates:
  - id: py_test
    type: pytest
    args: ["tests/"]
    env:
      PYTHONPATH: "py/src"
"""
    report = run_cli(criteria, tmp_path)
    assert report["passed"] is True, f"results: {report['results']}"


def test_import_clean_honors_env_pythonpath(tmp_path: Path):
    """F17: gate env: PYTHONPATH respected by import-clean."""
    pkg = tmp_path / "py" / "src" / "mypkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    criteria = """
gates:
  - id: imp
    type: import-clean
    module: mypkg
    env:
      PYTHONPATH: "py/src"
"""
    report = run_cli(criteria, tmp_path)
    assert report["passed"] is True, f"results: {report['results']}"


def test_coverage_honors_env_pythonpath(tmp_path: Path):
    """F17: gate env: PYTHONPATH respected by coverage."""
    pkg = tmp_path / "py" / "src" / "mypkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("def f(): return 1\n")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_it.py").write_text(
        "from mypkg import f\n"
        "def test_f(): assert f() == 1\n"
    )
    criteria = """
gates:
  - id: cov
    type: coverage
    target: "mypkg"
    min_percent: 50
    env:
      PYTHONPATH: "py/src"
"""
    report = run_cli(criteria, tmp_path)
    assert report["passed"] is True, f"results: {report['results']}"


def test_ruff_honors_env(tmp_path: Path):
    """Ruff gate should pass env: through to the subprocess."""
    (tmp_path / "a.py").write_text("x = 1\n")
    criteria = """
gates:
  - id: ruff_env
    type: ruff
    args: ["check", "."]
    env:
      RUFF_CACHE_DIR: "/tmp/ruff-cache-skillgoid-test"
"""
    report = run_cli(criteria, tmp_path)
    # Pass if ruff is installed; env must not cause a crash.
    # (We can't directly observe RUFF_CACHE_DIR from the test, but the gate
    # running cleanly with env specified is the baseline assertion.)
    assert report["results"][0]["gate_id"] == "ruff_env"
    assert report["results"][0]["passed"] is True


def test_mypy_honors_env(tmp_path: Path):
    """Mypy gate should pass env: through to the subprocess."""
    (tmp_path / "a.py").write_text("x: int = 1\n")
    criteria = """
gates:
  - id: mypy_env
    type: mypy
    args: ["a.py"]
    env:
      MYPY_CACHE_DIR: "/tmp/mypy-cache-skillgoid-test"
"""
    report = run_cli(criteria, tmp_path)
    assert report["results"][0]["gate_id"] == "mypy_env"
    assert report["results"][0]["passed"] is True


def test_pytest_default_pythonpath_when_env_absent(tmp_path: Path):
    """Back-compat: absent gate env still gets <project>/src on PYTHONPATH."""
    pkg = tmp_path / "src" / "mypkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("VAL = 7\n")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_it.py").write_text(
        "from mypkg import VAL\n"
        "def test_val(): assert VAL == 7\n"
    )
    criteria = """
gates:
  - id: py_test
    type: pytest
    args: ["tests/"]
"""
    report = run_cli(criteria, tmp_path)
    assert report["passed"] is True, f"results: {report['results']}"
