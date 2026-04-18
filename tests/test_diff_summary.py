"""Tests for scripts/diff_summary.py — parses `git diff --numstat` output
into a structured changes dict for iteration records.
"""
import json
import subprocess
import sys
from pathlib import Path

from scripts.diff_summary import parse_numstat, summarize_diff

ROOT = Path(__file__).resolve().parents[1]
CLI = [sys.executable, str(ROOT / "scripts" / "diff_summary.py")]


def test_parse_text_files():
    output = "12\t3\tsrc/auth.py\n25\t0\ttests/test_auth.py\n"
    result = parse_numstat(output)
    assert result["files_touched"] == ["src/auth.py", "tests/test_auth.py"]
    assert result["net_lines"] == (12 - 3) + (25 - 0)
    assert "src/auth.py: +12/-3" in result["diff_summary"]
    assert "tests/test_auth.py: +25/-0" in result["diff_summary"]


def test_parse_binary_file():
    output = "-\t-\tbin/image.png\n"
    result = parse_numstat(output)
    assert result["files_touched"] == ["bin/image.png"]
    # Binary files contribute 0 to net_lines
    assert result["net_lines"] == 0
    assert "bin/image.png: (binary)" in result["diff_summary"]


def test_parse_empty_diff():
    result = parse_numstat("")
    assert result == {"files_touched": [], "net_lines": 0, "diff_summary": ""}


def test_summarize_diff_in_real_repo(tmp_path: Path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "a.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "first"], cwd=tmp_path, check=True)
    (tmp_path / "a.py").write_text("x = 1\ny = 2\nz = 3\n")
    (tmp_path / "b.py").write_text("new = True\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "second"], cwd=tmp_path, check=True)

    result = summarize_diff(tmp_path, base="HEAD~1", head="HEAD")
    assert "a.py" in result["files_touched"]
    assert "b.py" in result["files_touched"]
    assert result["net_lines"] == 2 + 1  # a.py: +2, b.py: +1


def test_summarize_diff_on_first_commit(tmp_path: Path):
    """No HEAD~1 — summarize against empty tree so first iteration works."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "a.py").write_text("x = 1\ny = 2\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "first"], cwd=tmp_path, check=True)
    result = summarize_diff(tmp_path)
    assert "a.py" in result["files_touched"]
    assert result["net_lines"] == 2


def test_cli_outputs_json(tmp_path: Path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "a.py").write_text("hello\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "first"], cwd=tmp_path, check=True)
    result = subprocess.run(
        CLI + ["--project", str(tmp_path)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert "files_touched" in data
    assert "net_lines" in data
    assert "diff_summary" in data


def test_summarize_diff_in_non_git_project(tmp_path: Path):
    """A non-git project should produce the same 'git not available' sentinel
    as a missing git binary — lets the loop skill uniformly omit the
    changes field."""
    # tmp_path is not a git repo
    result = summarize_diff(tmp_path)
    assert result["files_touched"] == []
    assert result["net_lines"] == 0
    assert result["diff_summary"] == "git not available"
