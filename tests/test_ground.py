"""Tests for scripts/synthesize/ground.py — Stage 1 orchestrator."""
import json
import subprocess
import sys
from pathlib import Path

from scripts.synthesize._common import synthesis_path
from scripts.synthesize.ground import run_ground

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "synthesize" / "mini-flask-demo"
CLI = [sys.executable, str(ROOT / "scripts" / "synthesize" / "ground.py")]


def test_run_ground_writes_grounding_json(tmp_path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()

    out_path = run_ground(sg, analogues=[FIXTURE])

    assert out_path == synthesis_path(sg, "grounding.json")
    assert out_path.exists()
    payload = json.loads(out_path.read_text())
    assert payload["language_detected"] == "python"
    assert isinstance(payload["observations"], list)
    assert len(payload["observations"]) >= 2


def test_run_ground_with_no_analogues_writes_empty_observations(tmp_path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()

    out_path = run_ground(sg, analogues=[])

    payload = json.loads(out_path.read_text())
    assert payload["language_detected"] == "unknown"
    assert payload["observations"] == []


def test_run_ground_multiple_analogues_unions_observations(tmp_path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()

    # Use the same fixture twice — second copy gets a different repo_name
    # by symlinking
    second = tmp_path / "fixture-copy"
    second.symlink_to(FIXTURE)

    out_path = run_ground(sg, analogues=[FIXTURE, second])
    payload = json.loads(out_path.read_text())
    # Observations from BOTH analogues are preserved (refs differ)
    refs = {o["ref"] for o in payload["observations"]}
    assert any("mini-flask-demo" in r for r in refs)
    assert any("fixture-copy" in r for r in refs)


def test_cli_with_analogue_arg_writes_grounding(tmp_path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    result = subprocess.run(
        CLI + ["--skillgoid-dir", str(sg), str(FIXTURE)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (sg / "synthesis" / "grounding.json").exists()


def test_cli_no_analogues_still_writes_empty_grounding(tmp_path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    result = subprocess.run(
        CLI + ["--skillgoid-dir", str(sg)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads((sg / "synthesis" / "grounding.json").read_text())
    assert payload["observations"] == []


def test_cli_missing_skillgoid_dir_exits_one(tmp_path):
    result = subprocess.run(
        CLI + ["--skillgoid-dir", str(tmp_path / "nope")],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "not a Skillgoid project" in result.stderr
