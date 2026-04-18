"""v0.7 back-compat: iterations dirs containing both v0.6 (NNN.json) and
v0.7 (<chunk_id>-NNN.json) filenames must still be read correctly by all
consumers (metrics_append, retrospect-era readers)."""
import json
from pathlib import Path

from scripts.metrics_append import build_metrics_line


def _make_iter(path: Path, chunk_id: str, iteration: int, passed: bool):
    path.write_text(json.dumps({
        "iteration": iteration,
        "chunk_id": chunk_id,
        "gate_report": {"passed": passed, "results": []},
        "exit_reason": "success" if passed else "in_progress",
        "started_at": "2026-04-18T00:00:00+00:00",
        "ended_at": "2026-04-18T00:00:01+00:00",
    }))


def test_mixed_filename_conventions_readable(tmp_path):
    sg = tmp_path / ".skillgoid"
    iters = sg / "iterations"
    iters.mkdir(parents=True)
    (sg / "chunks.yaml").write_text(
        "chunks:\n"
        "  - id: old_chunk\n    description: x\n    gate_ids: [g]\n"
        "  - id: new_chunk\n    description: y\n    gate_ids: [g]\n"
    )
    (sg / "criteria.yaml").write_text("language: python\ngates:\n  - id: g\n    type: ruff\n")

    # v0.6-style filename
    _make_iter(iters / "001.json", "old_chunk", 1, True)
    # v0.7-style filename
    _make_iter(iters / "new_chunk-001.json", "new_chunk", 1, True)

    line = build_metrics_line(sg, "mixed-test")
    assert line["total_iterations"] == 2
    assert line["chunks"] == 2
    assert line["outcome"] == "success"


def test_v07_only_filenames_readable(tmp_path):
    sg = tmp_path / ".skillgoid"
    iters = sg / "iterations"
    iters.mkdir(parents=True)
    (sg / "chunks.yaml").write_text(
        "chunks:\n"
        "  - id: a\n    description: x\n    gate_ids: [g]\n"
        "  - id: b\n    description: y\n    gate_ids: [g]\n"
    )
    (sg / "criteria.yaml").write_text("language: python\ngates:\n  - id: g\n    type: ruff\n")

    _make_iter(iters / "a-001.json", "a", 1, True)
    _make_iter(iters / "a-002.json", "a", 2, True)
    _make_iter(iters / "b-001.json", "b", 1, True)

    line = build_metrics_line(sg, "v07-only")
    assert line["total_iterations"] == 3
    assert line["chunks"] == 2
    assert line["outcome"] == "success"
