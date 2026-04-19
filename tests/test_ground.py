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


def test_is_url_detects_common_schemes():
    from scripts.synthesize.ground import _is_url
    assert _is_url("https://github.com/pallets/flask.git")
    assert _is_url("http://example.com/repo.git")
    assert _is_url("git@github.com:pallets/flask.git")
    assert _is_url("ssh://git@host/repo.git")
    assert _is_url("git://host/repo.git")
    assert _is_url("file:///tmp/repo")


def test_is_url_rejects_local_paths():
    from scripts.synthesize.ground import _is_url
    assert not _is_url("/home/user/repo")
    assert not _is_url("./repo")
    assert not _is_url("repo")
    assert not _is_url("../sibling/repo")


def test_slug_for_url_extracts_owner_repo():
    from scripts.synthesize.ground import _slug_for_url
    assert _slug_for_url("https://github.com/pallets/flask.git") == "pallets-flask"
    assert _slug_for_url("https://github.com/pallets/flask") == "pallets-flask"
    assert _slug_for_url("git@github.com:encode/httpx.git") == "encode-httpx"
    assert _slug_for_url("https://gitlab.com/group/sub/project.git") == "sub-project"
    assert _slug_for_url("file:///tmp/myrepo") == "myrepo"


def _make_bare_fixture_repo(tmp_path: Path) -> Path:
    """Create a bare git repo that can be cloned via file:// URL."""
    import subprocess
    src = tmp_path / "src-repo"
    src.mkdir()
    (src / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n"
        "testpaths = ['tests']\n"
    )
    subprocess.run(["git", "init", "-q"], cwd=src, check=True)
    subprocess.run(["git", "add", "."], cwd=src, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init"],
        cwd=src, check=True,
    )
    return src


def test_run_ground_clones_url_into_cache_dir(tmp_path, monkeypatch):
    from scripts.synthesize.ground import run_ground
    src_repo = _make_bare_fixture_repo(tmp_path)
    url = f"file://{src_repo}"
    # Point XDG_CACHE_HOME to a sandbox so the real ~/.cache isn't touched
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    sg = tmp_path / "dest" / ".skillgoid"
    sg.mkdir(parents=True)
    run_ground(sg, [url])
    slug = "src-repo"  # from _slug_for_url of a file:// URL
    cloned = tmp_path / "cache" / "skillgoid" / "analogues" / slug
    assert (cloned / "pyproject.toml").exists()
    # And no project-local clone was created
    assert not (sg / "synthesis" / "analogues" / slug).exists()


def test_run_ground_accepts_local_path_without_copying(tmp_path, monkeypatch):
    from scripts.synthesize.ground import run_ground
    analogue = tmp_path / "analogue-repo"
    analogue.mkdir()
    (analogue / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n"
        "testpaths = ['tests']\n"
    )
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    sg = tmp_path / "proj" / ".skillgoid"
    sg.mkdir(parents=True)
    run_ground(sg, [analogue])
    # Local paths are NOT copied into the cache
    cache_analogues = tmp_path / "cache" / "skillgoid" / "analogues"
    assert not list(cache_analogues.glob("analogue-repo"))
    # grounding.json still reflects observations from the in-place path
    grounding = json.loads((sg / "synthesis" / "grounding.json").read_text())
    assert any(o["command"].startswith("pytest") for o in grounding["observations"])


def test_migrate_moves_legacy_to_cache(tmp_path, monkeypatch, capsys):
    from scripts.synthesize.ground import _migrate_legacy_analogues
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    sg = tmp_path / ".skillgoid"
    legacy = sg / "synthesis" / "analogues" / "pallets-flask"
    legacy.mkdir(parents=True)
    (legacy / "pyproject.toml").write_text("# marker\n")
    _migrate_legacy_analogues(sg)
    moved = tmp_path / "cache" / "skillgoid" / "analogues" / "pallets-flask"
    assert (moved / "pyproject.toml").read_text() == "# marker\n"
    assert not legacy.exists()
    captured = capsys.readouterr()
    assert "migrated pallets-flask" in captured.err


def test_migrate_conflict_leaves_both_and_warns(tmp_path, monkeypatch, capsys):
    from scripts.synthesize.ground import _migrate_legacy_analogues
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    sg = tmp_path / ".skillgoid"
    legacy = sg / "synthesis" / "analogues" / "pallets-flask"
    legacy.mkdir(parents=True)
    (legacy / "LEGACY").write_text("x")
    cached = tmp_path / "cache" / "skillgoid" / "analogues" / "pallets-flask"
    cached.mkdir(parents=True)
    (cached / "CACHED").write_text("y")
    _migrate_legacy_analogues(sg)
    assert (legacy / "LEGACY").exists()  # not moved
    assert (cached / "CACHED").exists()  # untouched
    captured = capsys.readouterr()
    assert "orphaned" in captured.err


def test_migrate_noop_when_no_legacy(tmp_path, monkeypatch):
    from scripts.synthesize.ground import _migrate_legacy_analogues
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    # Nothing to migrate
    _migrate_legacy_analogues(sg)
    # No directories created in cache
    cache_root = tmp_path / "cache" / "skillgoid" / "analogues"
    assert cache_root.is_dir()  # _cache_dir() creates this lazily; OK either way
    assert list(cache_root.iterdir()) == []
