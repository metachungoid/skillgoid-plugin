import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "detect-resume.sh"


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


def test_no_skillgoid_dir_emits_nothing(tmp_path: Path):
    out = _run(tmp_path)
    assert out == {} or out.get("continue", True) is True


def test_active_project_emits_resume_context(tmp_path: Path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    (sg / "chunks.yaml").write_text("chunks:\n  - id: a\n    description: first\n    gate_ids: [pytest]\n")
    iters = sg / "iterations"
    iters.mkdir()
    (iters / "001.json").write_text(json.dumps({
        "iteration": 1, "chunk_id": "a", "exit_reason": "in_progress",
        "gate_report": {"passed": False, "results": [{"gate_id": "pytest", "passed": False}]}
    }))
    out = _run(tmp_path)
    assert "hookSpecificOutput" in out
    blob = json.dumps(out)
    assert "skillgoid" in blob.lower()
    assert "chunk" in blob.lower() or "iteration" in blob.lower()
