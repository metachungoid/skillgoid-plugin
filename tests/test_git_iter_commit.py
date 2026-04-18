"""Tests for the git-per-iteration commit helper.

Contract: given a project path, chunk id, and iteration record, the
helper commits any pending changes with a structured message. Noops
cleanly on non-git projects. Tolerates zero-diff iterations via
--allow-empty. Never crashes the loop on a git error.
"""
import json
import subprocess
import sys
from pathlib import Path

from scripts.git_iter_commit import commit_iteration, is_git_repo

ROOT = Path(__file__).resolve().parents[1]
CLI = [sys.executable, str(ROOT / "scripts" / "git_iter_commit.py")]


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit",
                    "--allow-empty", "-q", "-m", "init"], cwd=path, check=True)


def _record(iteration: int, chunk_id: str, failing: bool, signature: str = "abc1234567890def") -> dict:
    return {
        "iteration": iteration,
        "chunk_id": chunk_id,
        "gate_report": {
            "passed": not failing,
            "results": [
                {"gate_id": "pytest", "passed": not failing, "stdout": "", "stderr": "E" if failing else "", "hint": ""}
            ],
        },
        "failure_signature": signature,
        "exit_reason": "in_progress",
    }


def test_is_git_repo_true(tmp_path: Path):
    _init_repo(tmp_path)
    assert is_git_repo(tmp_path) is True


def test_is_git_repo_false(tmp_path: Path):
    assert is_git_repo(tmp_path) is False


def test_commit_noop_on_non_git_project(tmp_path: Path):
    record = _record(1, "core-api", failing=True)
    result = commit_iteration(tmp_path, record)
    assert result is False


def test_commit_with_diff_creates_commit(tmp_path: Path):
    _init_repo(tmp_path)
    (tmp_path / "foo.py").write_text("print(1)\n")
    record = _record(1, "core-api", failing=True)
    result = commit_iteration(tmp_path, record)
    assert result is True

    log = subprocess.run(
        ["git", "log", "--oneline", "-1"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout
    assert "skillgoid:" in log.lower()
    assert "core-api" in log
    assert "iter 1" in log or "iteration 1" in log


def test_commit_zero_diff_uses_allow_empty(tmp_path: Path):
    _init_repo(tmp_path)
    record = _record(1, "core-api", failing=True)
    result = commit_iteration(tmp_path, record)
    assert result is True

    count = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert count == "2"  # init + our iteration commit


def test_commit_message_includes_signature_and_gate_summary(tmp_path: Path):
    _init_repo(tmp_path)
    (tmp_path / "foo.py").write_text("x = 1\n")
    record = _record(2, "core-api", failing=True, signature="feedfacecafebabe")
    commit_iteration(tmp_path, record)

    log = subprocess.run(
        ["git", "log", "-1", "--pretty=%B"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout
    assert "feedfacecafebabe" in log
    assert "pytest" in log.lower()


def test_cli_works(tmp_path: Path):
    _init_repo(tmp_path)
    (tmp_path / "foo.py").write_text("y = 2\n")
    iter_file = tmp_path / "001.json"
    iter_file.write_text(json.dumps(_record(1, "demo", failing=True)))

    result = subprocess.run(
        CLI + ["--project", str(tmp_path), "--iteration", str(iter_file)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout
    assert len(log.strip().split("\n")) == 2  # init + iteration commit


def test_cli_noop_on_non_git_exits_zero(tmp_path: Path):
    iter_file = tmp_path / "001.json"
    iter_file.write_text(json.dumps(_record(1, "demo", failing=True)))
    result = subprocess.run(
        CLI + ["--project", str(tmp_path), "--iteration", str(iter_file)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr


def test_iteration_relative_path_resolves_against_project(tmp_path, monkeypatch):
    """F25: --iteration as a relative path should resolve against --project,
    not caller's cwd."""
    import subprocess
    from scripts.git_iter_commit import main

    project = tmp_path / "proj"
    project.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(["git", "-C", str(project), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(project), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(project), "commit", "--allow-empty", "-qm", "init"], check=True)

    iters = project / ".skillgoid" / "iterations"
    iters.mkdir(parents=True)
    iter_file = iters / "scaffold-001.json"
    iter_file.write_text(json.dumps({
        "iteration": 1, "chunk_id": "scaffold",
        "gate_report": {"passed": True, "results": []},
        "exit_reason": "success",
    }))

    # Create a stub chunks.yaml (v0.7 flow requires it for paths resolution)
    (project / ".skillgoid" / "chunks.yaml").write_text(
        "chunks:\n  - id: scaffold\n    description: s\n    gate_ids: [g]\n"
    )

    # Call main from a cwd that is NOT the project
    monkeypatch.chdir(tmp_path)
    exit_code = main([
        "--project", str(project),
        "--iteration", ".skillgoid/iterations/scaffold-001.json",
        "--chunks-file", ".skillgoid/chunks.yaml",
    ])
    assert exit_code == 0
    log = subprocess.run(["git", "-C", str(project), "log", "--oneline"],
                         capture_output=True, text=True, check=True)
    assert "iter 1 of chunk scaffold" in log.stdout


def test_iteration_unreadable_hard_fails(tmp_path, capsys):
    """v0.7: replace soft-fail with exit 2 + stderr."""
    from scripts.git_iter_commit import main
    project = tmp_path / "proj"
    project.mkdir()
    exit_code = main([
        "--project", str(project),
        "--iteration", "/nonexistent/path.json",
        "--chunks-file", "/nonexistent/chunks.yaml",
    ])
    assert exit_code == 2
    captured = capsys.readouterr()
    assert "cannot read iteration" in captured.err
