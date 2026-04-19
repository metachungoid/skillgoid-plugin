"""Tests for scripts/synthesize/ground_analogue.py.

Reads vendored mini-flask-demo fixture and asserts observation extraction.
"""
import json
import subprocess
import sys
from pathlib import Path

from scripts.synthesize.ground_analogue import (
    Observation,
    detect_language,
    extract_observations,
    parse_pyproject_test_command,
    parse_workflow_steps,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "synthesize" / "mini-flask-demo"
CLI = [sys.executable, str(ROOT / "scripts" / "synthesize" / "ground_analogue.py")]


def test_detect_language_python_from_pyproject():
    assert detect_language(FIXTURE) == "python"


def test_detect_language_unknown_when_no_manifest(tmp_path):
    assert detect_language(tmp_path) == "unknown"


def test_parse_pyproject_test_command_returns_pytest_for_miniflask():
    cmd = parse_pyproject_test_command(FIXTURE / "pyproject.toml")
    # pyproject declares testpaths = ["tests"], pytest is the implied runner
    assert cmd == ["pytest", "tests"]


def test_parse_workflow_steps_extracts_run_lines():
    steps = parse_workflow_steps(FIXTURE / ".github" / "workflows" / "test.yml")
    # Workflow has: pip install, ruff check ., pytest -v
    assert "ruff check ." in steps
    assert "pytest -v" in steps


def test_extract_observations_returns_typed_observations():
    obs = extract_observations(FIXTURE)
    # Must include at least: pytest from pyproject, ruff from workflow,
    # pytest variant from workflow
    types_seen = {o.observed_type for o in obs}
    assert "pytest" in types_seen
    assert "ruff" in types_seen


def test_extract_observations_each_carries_source_ref():
    obs = extract_observations(FIXTURE)
    for o in obs:
        assert o.source == "analogue"
        assert o.ref.startswith(str(FIXTURE.name))  # ref is relative-ish to the repo
        assert o.command  # never empty


def test_observation_to_dict_round_trip():
    o = Observation(
        source="analogue",
        ref="mini-flask-demo/pyproject.toml",
        command="pytest tests",
        context="declared test command",
        observed_type="pytest",
    )
    d = o.to_dict()
    assert d == {
        "source": "analogue",
        "ref": "mini-flask-demo/pyproject.toml",
        "command": "pytest tests",
        "context": "declared test command",
        "observed_type": "pytest",
    }


def test_cli_emits_json_list_to_stdout():
    result = subprocess.run(
        CLI + [str(FIXTURE)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert isinstance(payload, list)
    assert len(payload) >= 2
    for entry in payload:
        assert entry["source"] == "analogue"


def test_cli_exits_one_on_missing_repo(tmp_path):
    result = subprocess.run(
        CLI + [str(tmp_path / "nope")],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "does not exist" in result.stderr
