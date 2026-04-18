"""Integration test: two git_iter_commit processes running concurrently on
the same repo must produce commits whose file contents are disjoint — no
cross-chunk contamination (F26)."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMITTER = ROOT / "scripts" / "git_iter_commit.py"


def _init(project: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(["git", "-C", str(project), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(project), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(project), "commit", "--allow-empty", "-qm", "init"], check=True)


def test_parallel_wave_commits_are_disjoint(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    _init(project)

    # Two chunks' worth of files in the working tree
    (project / "a.py").write_text("x = 1\n")
    (project / "b.py").write_text("y = 2\n")
    iters = project / ".skillgoid" / "iterations"
    iters.mkdir(parents=True)

    # Iteration files for both chunks
    a_iter = iters / "chunk_a-001.json"
    b_iter = iters / "chunk_b-001.json"
    for chunk, iter_file in (("chunk_a", a_iter), ("chunk_b", b_iter)):
        iter_file.write_text(json.dumps({
            "iteration": 1, "chunk_id": chunk,
            "gate_report": {"passed": True, "results": []},
            "exit_reason": "success",
        }))

    chunks_file = project / ".skillgoid" / "chunks.yaml"
    chunks_file.write_text(
        "chunks:\n"
        "  - id: chunk_a\n"
        "    description: a\n"
        "    gate_ids: [g]\n"
        "    paths: [a.py]\n"
        "  - id: chunk_b\n"
        "    description: b\n"
        "    gate_ids: [g]\n"
        "    paths: [b.py]\n"
    )

    # Launch both commit processes concurrently
    a_proc = subprocess.Popen(
        [sys.executable, str(COMMITTER),
         "--project", str(project),
         "--iteration", str(a_iter),
         "--chunks-file", str(chunks_file)],
        stderr=subprocess.PIPE, stdout=subprocess.PIPE,
    )
    b_proc = subprocess.Popen(
        [sys.executable, str(COMMITTER),
         "--project", str(project),
         "--iteration", str(b_iter),
         "--chunks-file", str(chunks_file)],
        stderr=subprocess.PIPE, stdout=subprocess.PIPE,
    )
    a_rc = a_proc.wait(timeout=30)
    b_rc = b_proc.wait(timeout=30)
    # Git's index lock may cause one of the commits to transiently fail; retry
    # if so (this is the documented-reality of parallel git writes).
    if a_rc != 0:
        subprocess.run(
            [sys.executable, str(COMMITTER),
             "--project", str(project),
             "--iteration", str(a_iter),
             "--chunks-file", str(chunks_file)],
            check=True, capture_output=True,
        )
    if b_rc != 0:
        subprocess.run(
            [sys.executable, str(COMMITTER),
             "--project", str(project),
             "--iteration", str(b_iter),
             "--chunks-file", str(chunks_file)],
            check=True, capture_output=True,
        )

    # Inspect each commit's files
    log = subprocess.run(
        ["git", "-C", str(project), "log", "--pretty=%H %s"],
        capture_output=True, text=True, check=True,
    ).stdout.strip().split("\n")

    def files_of(sha: str) -> set[str]:
        out = subprocess.run(
            ["git", "-C", str(project), "show", "--name-only", "--format=", sha],
            capture_output=True, text=True, check=True,
        ).stdout.strip().split("\n")
        return {f for f in out if f}

    # Find the two chunk commits
    a_sha = next(line.split()[0] for line in log if "chunk_a" in line)
    b_sha = next(line.split()[0] for line in log if "chunk_b" in line)
    a_files = files_of(a_sha)
    b_files = files_of(b_sha)

    # chunk_a's commit: a.py + its iteration. NOT b.py, NOT b's iteration.
    assert "a.py" in a_files
    assert ".skillgoid/iterations/chunk_a-001.json" in a_files
    assert "b.py" not in a_files
    assert ".skillgoid/iterations/chunk_b-001.json" not in a_files

    assert "b.py" in b_files
    assert ".skillgoid/iterations/chunk_b-001.json" in b_files
    assert "a.py" not in b_files
    assert ".skillgoid/iterations/chunk_a-001.json" not in b_files
