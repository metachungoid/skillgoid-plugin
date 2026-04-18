"""Tests for scripts/metrics_append.py — appends cross-project run stats to
~/.claude/skillgoid/metrics.jsonl on retrospect.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.metrics_append import build_metrics_line, append_metrics

ROOT = Path(__file__).resolve().parents[1]
CLI = [sys.executable, str(ROOT / "scripts" / "metrics_append.py")]


def _write_iter(sg: Path, n: int, chunk_id: str, exit_reason: str,
                started: str = "2026-04-17T12:00:00Z",
                ended: str = "2026-04-17T12:05:00Z") -> None:
    iters = sg / "iterations"
    iters.mkdir(exist_ok=True)
    (iters / f"{n:03d}.json").write_text(json.dumps({
        "iteration": n,
        "chunk_id": chunk_id,
        "started_at": started,
        "ended_at": ended,
        "gate_report": {"passed": exit_reason == "success", "results": []},
        "exit_reason": exit_reason,
    }))


def _write_integ(sg: Path, attempt: int, passed: bool) -> None:
    integ = sg / "integration"
    integ.mkdir(exist_ok=True)
    (integ / f"{attempt:03d}.json").write_text(json.dumps({
        "iteration": attempt,
        "chunk_id": "__integration__",
        "gate_report": {"passed": passed, "results": []},
    }))


def test_build_metrics_line_from_iterations(tmp_path: Path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    (sg / "goal.md").write_text("# Goal\n\nBuild a CLI.\n")
    (sg / "criteria.yaml").write_text("language: python\ngates: []\n")
    (sg / "chunks.yaml").write_text(
        "chunks:\n"
        "  - id: scaffold\n    description: scaffold\n    gate_ids: [ruff]\n"
        "  - id: core\n    description: core\n    gate_ids: [pytest]\n"
    )
    _write_iter(sg, 1, "scaffold", "success")
    _write_iter(sg, 2, "core", "success",
                started="2026-04-17T12:05:00Z", ended="2026-04-17T12:30:00Z")
    line = build_metrics_line(sg, project_slug="demo")
    assert line["slug"] == "demo"
    assert line["language"] == "python"
    assert line["outcome"] == "success"
    assert line["chunks"] == 2
    assert line["total_iterations"] == 2
    assert line["stall_count"] == 0
    assert line["budget_exhausted_count"] == 0
    assert line["integration_retries_used"] == 0
    assert line["elapsed_seconds"] == 30 * 60


def test_build_metrics_line_counts_stalls_and_budget_exhaustion(tmp_path: Path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    (sg / "criteria.yaml").write_text("language: python\ngates: []\n")
    (sg / "chunks.yaml").write_text("chunks:\n  - id: a\n    description: x\n    gate_ids: [pytest]\n")
    _write_iter(sg, 1, "a", "stalled")
    _write_iter(sg, 2, "a", "budget_exhausted")
    line = build_metrics_line(sg, project_slug="rough")
    assert line["outcome"] == "partial"
    assert line["stall_count"] == 1
    assert line["budget_exhausted_count"] == 1


def test_build_metrics_line_counts_integration_retries(tmp_path: Path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    (sg / "criteria.yaml").write_text("language: python\ngates: []\n")
    (sg / "chunks.yaml").write_text("chunks:\n  - id: a\n    description: x\n    gate_ids: [pytest]\n")
    _write_iter(sg, 1, "a", "success")
    _write_integ(sg, 1, passed=False)
    _write_integ(sg, 2, passed=False)
    _write_integ(sg, 3, passed=True)
    line = build_metrics_line(sg, project_slug="integ")
    assert line["integration_retries_used"] == 2  # 3 attempts = 2 retries after the initial


def test_append_metrics_writes_to_jsonl(tmp_path: Path, monkeypatch):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    (sg / "criteria.yaml").write_text("language: python\ngates: []\n")
    (sg / "chunks.yaml").write_text("chunks:\n  - id: a\n    description: x\n    gate_ids: [pytest]\n")
    _write_iter(sg, 1, "a", "success")

    home = tmp_path / "fake-home"
    monkeypatch.setenv("HOME", str(home))
    result = append_metrics(sg, project_slug="demo")
    assert result is True

    metrics_path = home / ".claude" / "skillgoid" / "metrics.jsonl"
    assert metrics_path.exists()
    lines = metrics_path.read_text().strip().split("\n")
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["slug"] == "demo"
    assert parsed["outcome"] == "success"


def test_cli_works(tmp_path: Path):
    sg = tmp_path / ".skillgoid"
    sg.mkdir()
    (sg / "criteria.yaml").write_text("language: python\ngates: []\n")
    (sg / "chunks.yaml").write_text("chunks:\n  - id: a\n    description: x\n    gate_ids: [pytest]\n")
    _write_iter(sg, 1, "a", "success")

    home = tmp_path / "fake-home"
    env = {**os.environ, "HOME": str(home)}
    result = subprocess.run(
        CLI + ["--skillgoid-dir", str(sg), "--slug", "cli-demo"],
        env=env, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    metrics_path = home / ".claude" / "skillgoid" / "metrics.jsonl"
    assert metrics_path.exists()
