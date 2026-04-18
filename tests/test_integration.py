"""End-to-end integration test for the measure → iteration JSON → gate-guard pipeline.

Covers the core invariant: a failing gate report, written as an iteration record,
causes the gate-guard hook to block the Stop event.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "scripts" / "measure_python.py"
GUARD = ROOT / "hooks" / "gate-guard.sh"
FAILING_PROJECT = ROOT / "tests" / "fixtures" / "failing-project"


def test_failing_gate_triggers_gate_guard_block(tmp_path: Path):
    """Simulate: run adapter against failing fixture → write report as iteration → invoke guard."""
    # Arrange — create a Skillgoid project layout in tmp_path.
    project = tmp_path / "myproj"
    project.mkdir()
    sg = project / ".skillgoid"
    sg.mkdir()
    (sg / "criteria.yaml").write_text("loop:\n  max_attempts: 5\ngates: []\n")
    iters = sg / "iterations"
    iters.mkdir()

    # Act 1 — run the adapter against the failing fixture.
    # We invoke the adapter with the failing-project fixture, asking it to run pytest.
    criteria = "gates:\n  - id: pytest\n    type: pytest\n    args: ['-q']\n"
    result = subprocess.run(
        [sys.executable, str(ADAPTER), "--project", str(FAILING_PROJECT), "--criteria-stdin"],
        input=criteria,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, f"adapter should return 1 for failing gates: {result.stderr}"
    report = json.loads(result.stdout)
    assert report["passed"] is False

    # Act 2 — persist the report as an iteration record.
    iter_record = {
        "iteration": 1,
        "chunk_id": "demo",
        "exit_reason": "in_progress",
        "gate_report": report,
    }
    (iters / "001.json").write_text(json.dumps(iter_record))

    # Act 3 — invoke the gate-guard hook with the project as CLAUDE_PROJECT_DIR.
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project)}
    guard_result = subprocess.run(
        ["bash", str(GUARD)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    # Assert — the guard should block.
    assert guard_result.returncode == 0, f"guard exited {guard_result.returncode}: {guard_result.stderr}"
    guard_out = guard_result.stdout.strip()
    assert guard_out, "guard should emit JSON"
    decision = json.loads(guard_out)
    assert decision.get("decision") == "block", f"unexpected decision: {decision}"
    assert "gates still failing" in decision.get("reason", "").lower()
