"""End-to-end tests for v0.10 iteration contract bundle.

Locks in the v0.10 contract:
  - stall_check.signature() works with canonical object-form gate_report
  - metrics_append classifies budget_exhausted chunks as 'partial' outcome

These are lock-in tests. The behavior they assert shipped in v0.9; v0.10's
contribution is making the contract authoritative in skills/loop/SKILL.md prose.
If either test ever fails, the v0.10 contract has been broken.
"""
import json
import subprocess
import sys
from pathlib import Path

from scripts.stall_check import signature

ROOT = Path(__file__).resolve().parents[1]
METRICS_CLI = [sys.executable, str(ROOT / "scripts" / "metrics_append.py")]


def test_stall_signature_object_form_contract():
    """Test B: canonical object-form gate_report produces stable, discriminating signatures.

    Object form is {"passed": bool, "results": [...]} — the shape measure_python.py
    emits and the shape the v0.10 SKILL.md template documents. Same failing stderr
    across iterations must yield the same 16-char hex signature; different stderr
    must yield a different signature.
    """
    record = {
        "chunk_id": "parser",
        "iteration": 2,
        "gate_report": {
            "passed": False,
            "results": [
                {
                    "gate_id": "pytest_unit",
                    "passed": False,
                    "stderr": "FAILED tests/test_parser.py::test_dst - AssertionError",
                },
            ],
        },
        "failure_signature": "",
    }

    sig = signature(record)
    assert len(sig) == 16
    assert all(c in "0123456789abcdef" for c in sig), \
        f"signature must be lowercase hex: {sig!r}"

    # Same failure on a later iteration → same signature (stall detection).
    sig_next = signature({**record, "iteration": 3})
    assert sig == sig_next, "identical failing gate_report must produce identical signature"

    # Different failure → different signature.
    different = {
        **record,
        "gate_report": {
            "passed": False,
            "results": [
                {
                    "gate_id": "pytest_unit",
                    "passed": False,
                    "stderr": "FAILED tests/test_parser.py::test_leap - OverflowError",
                },
            ],
        },
    }
    assert signature(different) != sig, \
        "different failing stderr must produce different signature"


def _write_iter(iters_dir: Path, filename: str, *, chunk_id: str, iteration: int,
                exit_reason: str) -> None:
    """Write a synthetic iteration record. Mirrors the shape metrics_append reads."""
    (iters_dir / filename).write_text(json.dumps({
        "iteration": iteration,
        "chunk_id": chunk_id,
        "started_at": "2026-04-17T12:00:00Z",
        "ended_at": "2026-04-17T12:05:00Z",
        "gate_report": {"passed": exit_reason == "success", "results": []},
        "exit_reason": exit_reason,
        "failure_signature": "0" * 16,
    }))


def test_h9_retrospect_only_partial_outcome(tmp_path, monkeypatch):
    """Test A: metrics_append classifies budget_exhausted chunks as 'partial' outcome.

    Synthetic 3-chunk project:
      - chunk-a: success (1 iteration)
      - chunk-b: terminal budget_exhausted (iteration 2 after in_progress iteration 1)
      - chunk-c: no iterations (never ran)

    Assertions:
      - CLI exit 0
      - metrics.jsonl appended with outcome="partial" (not "success")
      - budget_exhausted_count == 1 (only terminal iteration)
      - stall_count == 0
    """
    # Redirect HOME so metrics.jsonl writes to tmp_path, not the user's real ~/.claude.
    monkeypatch.setenv("HOME", str(tmp_path))

    sg = tmp_path / "project" / ".skillgoid"
    iters_dir = sg / "iterations"
    iters_dir.mkdir(parents=True)

    (sg / "chunks.yaml").write_text(
        "chunks:\n"
        "  - id: chunk-a\n    paths: [src/a.py]\n"
        "  - id: chunk-b\n    paths: [src/b.py]\n"
        "  - id: chunk-c\n    paths: [src/c.py]\n"
    )
    (sg / "criteria.yaml").write_text(
        "language: python\n"
        "gates:\n"
        "  - id: pytest_unit\n    type: pytest\n    args: []\n"
    )

    _write_iter(iters_dir, "chunk-a-001.json",
                chunk_id="chunk-a", iteration=1, exit_reason="success")
    _write_iter(iters_dir, "chunk-b-001.json",
                chunk_id="chunk-b", iteration=1, exit_reason="in_progress")
    _write_iter(iters_dir, "chunk-b-002.json",
                chunk_id="chunk-b", iteration=2, exit_reason="budget_exhausted")

    result = subprocess.run(
        METRICS_CLI + ["--skillgoid-dir", str(sg), "--slug", "test-partial"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, \
        f"metrics_append exited {result.returncode}: {result.stderr}"

    metrics_path = tmp_path / ".claude" / "skillgoid" / "metrics.jsonl"
    assert metrics_path.exists(), "metrics.jsonl was not created"

    lines = metrics_path.read_text().strip().splitlines()
    assert len(lines) == 1, f"expected 1 metrics line, got {len(lines)}"
    entry = json.loads(lines[0])

    assert entry["slug"] == "test-partial"
    assert entry["outcome"] == "partial", \
        f"expected outcome=partial for budget_exhausted chunk, got {entry['outcome']!r}"
    assert entry["budget_exhausted_count"] == 1, \
        f"expected 1 terminal budget_exhausted iteration, got {entry['budget_exhausted_count']}"
    assert entry["stall_count"] == 0
    assert entry["chunks"] == 3
