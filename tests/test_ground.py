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


def test_cache_dir_uses_xdg_when_set(tmp_path, monkeypatch):
    from scripts.synthesize.ground import _cache_dir
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    result = _cache_dir()
    assert result == tmp_path / "skillgoid" / "analogues"
    assert result.is_dir()


def test_cache_dir_defaults_to_home_cache_when_xdg_unset(tmp_path, monkeypatch):
    from scripts.synthesize.ground import _cache_dir
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    # Path.home() is read from HOME on POSIX
    result = _cache_dir()
    assert result == tmp_path / ".cache" / "skillgoid" / "analogues"
    assert result.is_dir()


def test_cache_dir_falls_back_to_tmpdir_when_unwritable(tmp_path, monkeypatch, capsys):
    from scripts.synthesize import ground
    # Force XDG_CACHE_HOME to a path that cannot be created (a file, not a dir)
    blocker = tmp_path / "blocker"
    blocker.write_text("")  # it's a file, so making subdirs under it fails
    monkeypatch.setenv("XDG_CACHE_HOME", str(blocker))
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmp"))
    result = ground._cache_dir()
    assert result.is_dir()
    assert str(result).startswith(str(tmp_path / "tmp"))
    captured = capsys.readouterr()
    assert "warning" in captured.err.lower()
