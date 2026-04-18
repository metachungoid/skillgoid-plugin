"""End-to-end integration test exercising all v0.8 items together.

Synthetic 3-chunk project with:
  - chunk A owning src/shared.py + tests/test_a.py
  - chunk B owning src/shared.py + src/b.py + tests/test_b.py (deliberate overlap with A)
  - chunk C owning src/c.py + tests/test_c.py (no overlap)

Asserts:
  1. chunk_topo.plan_waves splits overlapping A+B into separate waves.
  2. blueprint_slice returns A's section + architecture overview + cross-chunk types;
     does NOT include B's or C's sections.
  3. git_iter_commit rejects a schema-invalid iteration JSON with exit 2.
  4. gate_overrides merging produces the expected narrowed args.
"""
import json
import subprocess
import sys
from pathlib import Path

from scripts.blueprint_slice import slice_blueprint
from scripts.chunk_topo import plan_waves
from scripts.validate_iteration import validate_iteration


INTEGRATION_BLUEPRINT = """\
# Blueprint — integration fixture

## Architecture overview

Three-chunk synthetic project for v0.8 integration testing.

## Cross-chunk types

- `Shared` — defined in `src/shared.py`. Import, do not re-define.

## chunk-a

Chunk A owns src/shared.py.

## chunk-b

Chunk B owns src/shared.py AND src/b.py (deliberate overlap with A).

## chunk-c

Chunk C owns src/c.py (no overlap).
"""

INTEGRATION_CHUNKS = [
    {"id": "chunk-a", "paths": ["src/shared.py", "tests/test_a.py"]},
    {"id": "chunk-b", "paths": ["src/shared.py", "src/b.py", "tests/test_b.py"]},
    {"id": "chunk-c", "paths": ["src/c.py", "tests/test_c.py"]},
]


def test_path_overlap_splits_wave():
    """Item 2 (F8): A and B overlap on shared.py; must be in different waves."""
    waves = plan_waves(INTEGRATION_CHUNKS)
    a_wave = next(i for i, w in enumerate(waves) if "chunk-a" in w)
    b_wave = next(i for i, w in enumerate(waves) if "chunk-b" in w)
    assert a_wave != b_wave, "A and B must be in different waves"


def test_blueprint_slice_extracts_chunk_context():
    """Item 4 (F7): slicer returns arch overview + cross-chunk types + chunk's own section."""
    result = slice_blueprint(INTEGRATION_BLUEPRINT, "chunk-a")
    assert "## Architecture overview" in result
    assert "## Cross-chunk types" in result
    assert "## chunk-a" in result
    assert "Chunk A owns src/shared.py." in result
    assert "## chunk-b" not in result
    assert "## chunk-c" not in result
    assert "Chunk B owns" not in result
    assert "Chunk C owns" not in result


def test_schema_validation_rejects_bad_iteration():
    """Item 1 (F5+F9): a record missing gate_report fails validation."""
    bad = {"iteration": 1, "chunk_id": "x"}
    errors = validate_iteration(bad)
    assert errors
    assert any("gate_report" in e for e in errors)


def test_git_iter_commit_refuses_invalid_iteration(tmp_path: Path):
    """Item 1 end-to-end: git_iter_commit exits 2 on bad iteration JSON."""
    project = tmp_path / "proj"
    project.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(["git", "-C", str(project), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(project), "config", "user.name", "t"], check=True)
    subprocess.run(
        ["git", "-C", str(project), "commit", "--allow-empty", "-qm", "init"],
        check=True,
    )
    iters = project / ".skillgoid" / "iterations"
    iters.mkdir(parents=True)
    bad = iters / "chunk-a-001.json"
    bad.write_text(json.dumps({"iteration": 1, "chunk_id": "chunk-a"}))
    (project / ".skillgoid" / "chunks.yaml").write_text(
        "chunks:\n  - id: chunk-a\n    description: x\n    gate_ids: [g]\n"
    )
    result = subprocess.run(
        [
            sys.executable,
            "scripts/git_iter_commit.py",
            "--project", str(project),
            "--iteration", str(bad),
            "--chunks-file", str(project / ".skillgoid" / "chunks.yaml"),
        ],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2
    assert "validation" in result.stderr.lower() or "gate_report" in result.stderr


def test_gate_overrides_merge():
    """Item 3 (F3+F12): gate_overrides narrow args; other fields preserved."""
    chunk = {
        "id": "chunk-a",
        "gate_overrides": {
            "pytest_chunk": {"args": ["tests/test_a.py"]},
        },
    }
    gates = [
        {"id": "pytest_chunk", "type": "pytest", "args": ["tests/"], "env": {"PYTHONPATH": "src"}},
        {"id": "lint", "type": "ruff", "args": ["check", "."]},
    ]
    overrides = chunk.get("gate_overrides") or {}
    merged = []
    for g in gates:
        gate = dict(g)
        ov = overrides.get(gate["id"])
        if ov and "args" in ov:
            gate["args"] = list(ov["args"])
        merged.append(gate)
    assert merged[0]["args"] == ["tests/test_a.py"]
    assert merged[0]["env"] == {"PYTHONPATH": "src"}
    assert merged[1]["args"] == ["check", "."]
