"""Tests for scripts/stats_reader.py — reads metrics.jsonl and summarizes."""
import json
import subprocess
import sys
from pathlib import Path

from scripts.stats_reader import summarize, format_report

ROOT = Path(__file__).resolve().parents[1]
CLI = [sys.executable, str(ROOT / "scripts" / "stats_reader.py")]


def _write_metrics(path: Path, lines: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n")


def _sample(**overrides) -> dict:
    base = {
        "timestamp": "2026-04-17T12:00:00+00:00",
        "slug": "proj",
        "language": "python",
        "outcome": "success",
        "chunks": 3,
        "total_iterations": 4,
        "stall_count": 0,
        "budget_exhausted_count": 0,
        "integration_retries_used": 0,
        "elapsed_seconds": 120,
    }
    base.update(overrides)
    return base


def test_summarize_empty_file(tmp_path: Path):
    path = tmp_path / "metrics.jsonl"
    path.write_text("")
    s = summarize(path, limit=20)
    assert s["count"] == 0
    assert s["success_rate"] is None


def test_summarize_single_line(tmp_path: Path):
    path = tmp_path / "metrics.jsonl"
    _write_metrics(path, [_sample()])
    s = summarize(path, limit=20)
    assert s["count"] == 1
    assert s["success_rate"] == 1.0
    assert s["avg_iterations_per_chunk"] == 4 / 3
    assert s["languages"] == {"python": 1}


def test_summarize_mixed_outcomes(tmp_path: Path):
    path = tmp_path / "metrics.jsonl"
    _write_metrics(path, [
        _sample(slug="a", outcome="success", stall_count=0),
        _sample(slug="b", outcome="partial", stall_count=1),
        _sample(slug="c", outcome="success", integration_retries_used=2),
    ])
    s = summarize(path, limit=20)
    assert s["count"] == 3
    assert s["success_rate"] == 2 / 3
    assert s["stall_rate"] == 1 / 3
    assert s["integration_retry_rate"] == 1 / 3


def test_format_report_produces_markdown(tmp_path: Path):
    path = tmp_path / "metrics.jsonl"
    _write_metrics(path, [_sample(slug="one"), _sample(slug="two", outcome="partial")])
    s = summarize(path, limit=20)
    md = format_report(s, limit=20)
    assert "# Skillgoid stats" in md
    assert "one" in md
    assert "two" in md
    assert "Success rate" in md


def test_summarize_skips_malformed_lines(tmp_path: Path):
    path = tmp_path / "metrics.jsonl"
    path.write_text('{"slug": "good", "outcome": "success", "chunks": 1, "total_iterations": 1, "stall_count": 0, "budget_exhausted_count": 0, "integration_retries_used": 0}\n{this is broken json\n')
    s = summarize(path, limit=20)
    assert s["count"] == 1  # only the good line


def test_cli_on_missing_file(tmp_path: Path):
    path = tmp_path / "nonexistent.jsonl"
    result = subprocess.run(
        CLI + ["--metrics-file", str(path)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0  # handled gracefully
    assert "no metrics" in result.stdout.lower() or "empty" in result.stdout.lower()
