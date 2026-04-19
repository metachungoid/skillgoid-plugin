"""Bundle test for v0.12 auto-partial-retrospective.

Two layers:
  1. Grep-verify that skills/build/SKILL.md documents the auto-retrospect
     trigger and the three skip conditions. build orchestration is prose, so
     prose verification IS the contract.
  2. Lock in _outcome() classification in scripts/metrics_append.py for the
     two scenarios v0.10 H9 did NOT cover:
        - All-success → outcome='success'
        - Empty iterations → outcome='abandoned'
     (Partial from budget_exhausted already locked in by v0.10 H9.)

If the prose grep ever fails, the auto-retrospect trigger has regressed.
If the classification tests ever fail, retrospect output would mislead
users about run outcomes.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD_SKILL = ROOT / "skills" / "build" / "SKILL.md"
METRICS_CLI = [sys.executable, str(ROOT / "scripts" / "metrics_append.py")]


def test_build_skill_documents_auto_retrospect_trigger():
    """The step 9 auto-retrospect section must be present verbatim."""
    text = BUILD_SKILL.read_text()
    assert "Auto-retrospect trigger" in text, \
        "skills/build/SKILL.md missing 'Auto-retrospect trigger' heading"
    assert "stalled` / `budget_exhausted" in text or "stalled / budget_exhausted" in text, \
        "auto-retrospect step must mention stalled/budget_exhausted terminal states"


def test_build_skill_documents_all_three_skip_conditions():
    """All three skip conditions must be documented."""
    text = BUILD_SKILL.read_text()
    assert "retrospect-only" in text and "already invokes retrospect" in text, \
        "retrospect-only skip condition missing"
    assert "build status" in text and "no loop ran" in text, \
        "build status skip condition missing"
    assert "iterations/` is absent or empty" in text \
        or "iterations/ is absent or empty" in text, \
        "empty-iterations skip condition missing"


def test_build_skill_documents_slug_source():
    """The slug passed to metrics_append.py must be documented as cwd basename."""
    text = BUILD_SKILL.read_text()
    assert "basename" in text and "pwd" in text, \
        "slug source (basename of cwd) not documented in auto-retrospect step"


def _write_iter(iters_dir: Path, filename: str, *, chunk_id: str, iteration: int,
                exit_reason: str) -> None:
    iters_dir.mkdir(parents=True, exist_ok=True)
    (iters_dir / filename).write_text(json.dumps({
        "iteration": iteration,
        "chunk_id": chunk_id,
        "started_at": "2026-04-18T12:00:00Z",
        "ended_at": "2026-04-18T12:05:00Z",
        "gate_report": {"passed": exit_reason == "success", "results": []},
        "exit_reason": exit_reason,
        "failure_signature": "0" * 16,
    }))


def _write_minimal_criteria_and_chunks(sg: Path, chunk_ids: list[str]) -> None:
    chunks_yaml = "chunks:\n" + "".join(
        f"  - id: {cid}\n    paths: [src/{cid}.py]\n" for cid in chunk_ids
    )
    (sg / "chunks.yaml").write_text(chunks_yaml)
    (sg / "criteria.yaml").write_text(
        "language: python\n"
        "gates:\n"
        "  - id: pytest_unit\n    type: pytest\n    args: []\n"
    )


def test_outcome_success_when_all_chunks_succeed(tmp_path, monkeypatch):
    """Auto-retrospect on happy path → metrics line records outcome=success."""
    monkeypatch.setenv("HOME", str(tmp_path))
    sg = tmp_path / "project" / ".skillgoid"
    iters = sg / "iterations"
    iters.mkdir(parents=True)
    _write_minimal_criteria_and_chunks(sg, ["a", "b"])
    _write_iter(iters, "a-001.json", chunk_id="a", iteration=1, exit_reason="success")
    _write_iter(iters, "b-001.json", chunk_id="b", iteration=1, exit_reason="success")

    result = subprocess.run(
        METRICS_CLI + ["--skillgoid-dir", str(sg), "--slug", "happy-slug"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr

    metrics_path = tmp_path / ".claude" / "skillgoid" / "metrics.jsonl"
    assert metrics_path.exists()
    entry = json.loads(metrics_path.read_text().strip().splitlines()[-1])
    assert entry["outcome"] == "success", \
        f"expected outcome=success, got {entry['outcome']!r}"
    assert entry["slug"] == "happy-slug"


def test_outcome_partial_when_a_chunk_stalls(tmp_path, monkeypatch):
    """Auto-retrospect on stall path → metrics line records outcome=partial.

    Mirrors v0.10 H9 (which covered budget_exhausted); this case covers stalled.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    sg = tmp_path / "project" / ".skillgoid"
    iters = sg / "iterations"
    iters.mkdir(parents=True)
    _write_minimal_criteria_and_chunks(sg, ["a", "b"])
    _write_iter(iters, "a-001.json", chunk_id="a", iteration=1, exit_reason="success")
    _write_iter(iters, "b-001.json", chunk_id="b", iteration=1, exit_reason="in_progress")
    _write_iter(iters, "b-002.json", chunk_id="b", iteration=2, exit_reason="in_progress")
    _write_iter(iters, "b-003.json", chunk_id="b", iteration=3, exit_reason="stalled")

    result = subprocess.run(
        METRICS_CLI + ["--skillgoid-dir", str(sg), "--slug", "stall-slug"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr

    metrics_path = tmp_path / ".claude" / "skillgoid" / "metrics.jsonl"
    entry = json.loads(metrics_path.read_text().strip().splitlines()[-1])
    assert entry["outcome"] == "partial", \
        f"expected outcome=partial for stall, got {entry['outcome']!r}"
    assert entry["stall_count"] == 1
    assert entry["slug"] == "stall-slug"


def test_outcome_abandoned_on_empty_iterations(tmp_path, monkeypatch):
    """Empty-iterations skip condition: metrics_append still runs cleanly but
    records outcome=abandoned. (The build orchestrator SHOULD skip auto-invoke,
    but if it were ever invoked with empty state, the classification must not
    mis-label the run as 'success'.)"""
    monkeypatch.setenv("HOME", str(tmp_path))
    sg = tmp_path / "project" / ".skillgoid"
    (sg / "iterations").mkdir(parents=True)
    _write_minimal_criteria_and_chunks(sg, ["a"])

    result = subprocess.run(
        METRICS_CLI + ["--skillgoid-dir", str(sg), "--slug", "empty-slug"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr

    metrics_path = tmp_path / ".claude" / "skillgoid" / "metrics.jsonl"
    entry = json.loads(metrics_path.read_text().strip().splitlines()[-1])
    assert entry["outcome"] == "abandoned", \
        f"expected outcome=abandoned for empty iterations, got {entry['outcome']!r}"
    assert entry["total_iterations"] == 0
    assert entry["slug"] == "empty-slug"
