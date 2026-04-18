import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "gate-guard.sh"


def _run(cwd: Path) -> dict:
    env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(ROOT), "CLAUDE_PROJECT_DIR": str(cwd)}
    proc = subprocess.run(
        ["bash", str(HOOK)],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if not proc.stdout.strip():
        return {}
    return json.loads(proc.stdout)


def test_no_skillgoid_dir_does_not_block(tmp_path: Path):
    out = _run(tmp_path)
    assert out == {} or out.get("decision") != "block"


def test_failing_gates_with_budget_blocks_stop(tmp_path: Path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    (sg / "criteria.yaml").write_text("loop:\n  max_attempts: 5\ngates: []\n")
    (sg / "chunks.yaml").write_text("chunks:\n  - id: a\n    description: x\n    gate_ids: [pytest]\n")
    iters = sg / "iterations"
    iters.mkdir()
    (iters / "001.json").write_text(json.dumps({
        "iteration": 1, "chunk_id": "a",
        "gate_report": {"passed": False, "results": [{"gate_id": "pytest", "passed": False}]},
        "exit_reason": "in_progress"
    }))
    out = _run(tmp_path)
    assert out.get("decision") == "block"
    assert "gates still failing" in out.get("reason", "").lower()


def test_all_gates_pass_allows_stop(tmp_path: Path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    (sg / "chunks.yaml").write_text("chunks:\n  - id: a\n    description: x\n    gate_ids: [pytest]\n")
    iters = sg / "iterations"
    iters.mkdir()
    (iters / "001.json").write_text(json.dumps({
        "iteration": 1, "chunk_id": "a",
        "gate_report": {"passed": True, "results": [{"gate_id": "pytest", "passed": True}]},
        "exit_reason": "success"
    }))
    out = _run(tmp_path)
    assert out.get("decision") != "block"


def test_budget_exhausted_allows_stop(tmp_path: Path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    (sg / "criteria.yaml").write_text("loop:\n  max_attempts: 2\ngates: []\n")
    iters = sg / "iterations"
    iters.mkdir()
    (iters / "002.json").write_text(json.dumps({
        "iteration": 2, "chunk_id": "a",
        "gate_report": {"passed": False, "results": [{"gate_id": "pytest", "passed": False}]},
        "exit_reason": "budget_exhausted"
    }))
    out = _run(tmp_path)
    assert out.get("decision") != "block"
