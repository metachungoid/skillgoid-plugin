#!/usr/bin/env python3
"""Skillgoid chunk explain.

Reads all `.skillgoid/iterations/<chunk_id>-*.json` files in order and emits a
markdown timeline + stall-signal section + verbatim reflections. Read-only.

Contract:
    render_explain(sg: Path, chunk_id: str) -> str

CLI:
    python scripts/explain_chunk.py --chunk-id <id> [--skillgoid-dir .skillgoid]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


_ITER_RE = re.compile(r"-(\d+)\.json$")


def _iteration_number(path: Path) -> int:
    m = _ITER_RE.search(path.name)
    return int(m.group(1)) if m else 0


def _load_iterations(sg: Path, chunk_id: str) -> list[dict]:
    iters_dir = sg / "iterations"
    if not iters_dir.is_dir():
        return []
    paths = sorted(iters_dir.glob(f"{chunk_id}-*.json"), key=_iteration_number)
    records: list[dict] = []
    for p in paths:
        try:
            records.append(json.loads(p.read_text()))
        except Exception:
            continue
    return records


def _first_stderr_or_hint(record: dict) -> str:
    gate_report = record.get("gate_report") or {}
    results = gate_report.get("results") if isinstance(gate_report, dict) else gate_report
    if not results:
        return ""
    for r in results:
        if r.get("passed"):
            continue
        stderr = (r.get("stderr") or "").strip()
        if stderr:
            first = stderr.splitlines()[0]
            return first[:80]
        hint = (r.get("hint") or "").strip()
        if hint:
            return hint[:80]
    return ""


def _gate_state_summary(record: dict) -> str:
    gate_report = record.get("gate_report") or {}
    results = gate_report.get("results") if isinstance(gate_report, dict) else gate_report
    if not results:
        return "—"
    parts = []
    for r in results[:3]:
        gid = r.get("gate_id", "?")
        parts.append(f"{gid} {'pass' if r.get('passed') else 'FAIL'}")
    summary = ", ".join(parts)
    if len(results) > 3:
        summary += f" (+{len(results) - 3} more)"
    return summary


def _files_touched_summary(record: dict) -> str:
    changes = record.get("changes") or {}
    files = changes.get("files_touched") or []
    if not files:
        return "—"
    shown = files[:2]
    summary = ", ".join(shown)
    if len(files) > 2:
        summary += f" (+{len(files) - 2} more)"
    return summary


def _signature_short(record: dict) -> str:
    sig = record.get("failure_signature")
    if not sig:
        return "—"
    return sig[:8]


def _detect_stall(records: list[dict]) -> tuple[str, int, int] | None:
    """Return (short_signature, repeat_count, stall_iteration) if any two
    consecutive iterations share a failure_signature, else None.

    repeat_count is the total number of records sharing that signature.
    stall_iteration is the iteration number of the LAST record sharing
    the signature — the closest to terminal, matching spec example.
    """
    if len(records) < 2:
        return None
    for i in range(1, len(records)):
        sig_prev = records[i - 1].get("failure_signature")
        sig_curr = records[i].get("failure_signature")
        if sig_prev and sig_curr and sig_prev == sig_curr:
            matching = [
                r for r in records if r.get("failure_signature") == sig_curr
            ]
            count = len(matching)
            stall_iter = matching[-1].get("iteration", len(matching))
            return sig_curr[:8], count, stall_iter
    return None


def render_explain(sg: Path, chunk_id: str) -> str:
    records = _load_iterations(sg, chunk_id)
    if not records:
        raise FileNotFoundError(f"no iteration files for chunk {chunk_id!r}")

    n = len(records)
    lines: list[str] = []
    lines.append(f"# Chunk `{chunk_id}` — {n} iteration{'s' if n != 1 else ''}")
    lines.append("")
    lines.append("## Timeline")
    lines.append("| iter | gate state | files touched | first stderr / hint | exit_reason | sig |")
    lines.append("|------|------------|---------------|---------------------|-------------|-----|")

    prev_first = None
    for r in records:
        iter_num = r.get("iteration", "?")
        gate = _gate_state_summary(r)
        files = _files_touched_summary(r)
        first = _first_stderr_or_hint(r)
        annotated = first
        if prev_first is not None and first and first == prev_first:
            annotated = f"{first} (same)"
        prev_first = first if first else prev_first
        exit_reason = r.get("exit_reason", "in_progress")
        sig = _signature_short(r)
        lines.append(
            f"| {iter_num} | {gate} | {files} | {annotated} | {exit_reason} | {sig} |"
        )

    stall = _detect_stall(records)
    if stall is not None:
        sig, count, stall_iter = stall
        lines.append("")
        lines.append("## Stall signal")
        lines.append(
            f"Signature `{sig}` repeated {count} times — loop detected no-progress "
            f"at iteration {stall_iter}."
        )

    reflections = [(r.get("iteration", "?"), r.get("reflection")) for r in records
                   if r.get("reflection")]
    if reflections:
        lines.append("")
        lines.append("## Reflections")
        for iter_num, text in reflections:
            lines.append(f"### Iteration {iter_num}")
            lines.append(text)
            lines.append("")

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Skillgoid chunk iteration explainer")
    ap.add_argument("--chunk-id", required=True)
    ap.add_argument("--skillgoid-dir", type=Path, default=Path(".skillgoid"))
    args = ap.parse_args(argv)

    sg = args.skillgoid_dir.resolve()
    try:
        out = render_explain(sg, chunk_id=args.chunk_id)
    except FileNotFoundError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 1
    sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
