#!/usr/bin/env python3
"""Identify the suspect chunk from a failed integration gate report.

Called by the build orchestrator (build/SKILL.md step 4g) when integration
gates fail and one chunk needs to be re-dispatched for auto-repair.

Scoring algorithm (deterministic):
1. For each chunk, collect its paths[] entries.
2. For each failing gate result, concatenate stdout + "\\n" + stderr.
3. Count how many of the chunk's paths appear as substrings in that output.
4. Rank by: (a) total matches desc, (b) latest failing-gate index desc,
   (c) alphabetical chunk_id asc.
5. Zero matches across all chunks → suspect_chunk_id: null.

CLI:
    python scripts/integration_suspect.py \\
        --gate-report .skillgoid/integration/1.json \\
        --chunks     .skillgoid/chunks.yaml
    Always exits 0 (result in JSON). Internal errors exit 2.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml


def _get_failing_results(gate_report: dict | list) -> list[dict]:
    if isinstance(gate_report, list):
        results = gate_report
    elif isinstance(gate_report, dict):
        results = gate_report.get("results") or []
    else:
        raise TypeError(
            f"gate_report must be a dict or list, got {type(gate_report).__name__!r}"
        )
    return [r for r in results if not r.get("passed")]


def identify_suspect(gate_report_path: Path, chunks_path: Path) -> dict:
    """Return suspect identification dict. Raises on malformed input."""
    attempt = json.loads(gate_report_path.read_text())
    gate_report = attempt.get("gate_report", attempt)

    failing = _get_failing_results(gate_report)
    if not failing:
        return {
            "suspect_chunk_id": None,
            "confidence": None,
            "evidence": "no failing gates in the report",
        }

    data = yaml.safe_load(chunks_path.read_text())
    chunks = (data or {}).get("chunks", [])

    # scores[chunk_id] = (total_matches, latest_gate_index)
    scores: dict[str, tuple[int, int]] = {}
    evidence_map: dict[str, str] = {}

    for chunk in chunks:
        chunk_id = chunk.get("id", "")
        paths = chunk.get("paths") or []
        if not chunk_id or not paths:
            continue

        total = 0
        latest_idx = -1
        best_evidence = ""

        for gate_idx, gate in enumerate(failing):
            combined = (gate.get("stdout") or "") + "\n" + (gate.get("stderr") or "")
            for p in paths:
                if p in combined:
                    total += 1
                    if gate_idx > latest_idx:
                        latest_idx = gate_idx
                        gate_id = gate.get("gate_id", "unknown")
                        best_evidence = (
                            f"chunk {chunk_id!r} path {p!r} matched gate {gate_id!r} output"
                        )

        if total > 0:
            scores[chunk_id] = (total, latest_idx)
            evidence_map[chunk_id] = best_evidence

    if not scores:
        return {
            "suspect_chunk_id": None,
            "confidence": None,
            "evidence": "no chunk path appeared in any failed gate's stdout/stderr",
        }

    ranked = sorted(
        scores,
        key=lambda cid: (-scores[cid][0], -scores[cid][1], cid),
    )
    winner = ranked[0]
    return {
        "suspect_chunk_id": winner,
        "confidence": "filename-match",
        "evidence": evidence_map[winner],
    }


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    ap = argparse.ArgumentParser(
        description="Identify suspect chunk from failed integration gate report"
    )
    ap.add_argument("--gate-report", required=True,
                    help="Path to .skillgoid/integration/<attempt>.json")
    ap.add_argument("--chunks", required=True,
                    help="Path to .skillgoid/chunks.yaml")
    args = ap.parse_args(argv)

    try:
        result = identify_suspect(Path(args.gate_report), Path(args.chunks))
    except Exception as exc:
        sys.stderr.write(f"integration_suspect: {exc}\n")
        return 2

    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
