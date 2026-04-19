#!/usr/bin/env python3
"""Skillgoid status reader.

Reads `.skillgoid/chunks.yaml`, `.skillgoid/iterations/*.json`, and optionally
`.skillgoid/integration/*.json` in the current working directory. Emits a
markdown snapshot of the project's in-flight state.

Read-only. Never modifies any file.

Contract:
    render_status(sg: Path, project_label: str) -> str

CLI:
    python scripts/status_reader.py [--skillgoid-dir .skillgoid]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

# Allow cross-script import when invoked directly as python scripts/status_reader.py
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.chunk_topo import plan_waves  # noqa: E402


def _load_chunks(sg: Path) -> list[dict]:
    chunks_file = sg / "chunks.yaml"
    if not chunks_file.exists():
        return []
    data = yaml.safe_load(chunks_file.read_text()) or {}
    chunks = data.get("chunks") or []
    return chunks if isinstance(chunks, list) else []


def _latest_iteration_for_chunk(sg: Path, chunk_id: str) -> dict | None:
    iters_dir = sg / "iterations"
    if not iters_dir.is_dir():
        return None
    candidates = list(iters_dir.glob(f"{chunk_id}-*.json"))
    if not candidates:
        return None
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    try:
        return json.loads(latest.read_text())
    except Exception:
        return None


def _latest_integration(sg: Path) -> tuple[int, dict] | None:
    integ_dir = sg / "integration"
    if not integ_dir.is_dir():
        return None
    candidates = [p for p in integ_dir.glob("*.json")]
    if not candidates:
        return None
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    try:
        record = json.loads(latest.read_text())
    except Exception:
        return None
    try:
        attempt = int(latest.stem)
    except ValueError:
        attempt = record.get("iteration", 0)
    return attempt, record


def _wave_for_chunk(waves: list[list[str]], chunk_id: str) -> int | None:
    for idx, wave in enumerate(waves, start=1):
        if chunk_id in wave:
            return idx
    return None


def _gate_state_summary(record: dict | None) -> str:
    if record is None:
        return "—"
    gate_report = record.get("gate_report") or {}
    results = gate_report.get("results") if isinstance(gate_report, dict) else gate_report
    if not results:
        return "—"
    parts: list[str] = []
    for r in results[:3]:
        gid = r.get("gate_id", "?")
        passed = r.get("passed", False)
        parts.append(f"{gid} {'pass' if passed else 'FAIL'}")
    summary = ", ".join(parts)
    remainder = len(results) - 3
    if remainder > 0:
        summary += f" (+{remainder} more)"
    return summary


def _files_touched_summary(record: dict | None) -> str:
    if record is None:
        return "—"
    changes = record.get("changes") or {}
    files = changes.get("files_touched") or []
    if not files:
        return "—"
    shown = files[:2]
    summary = ", ".join(shown)
    remainder = len(files) - 2
    if remainder > 0:
        summary += f" (+{remainder} more)"
    return summary


def _truncate_stderr(text: str, limit: int = 120) -> str:
    if not text:
        return ""
    first_line = text.splitlines()[0] if text else ""
    if len(first_line) > limit:
        return first_line[:limit] + "..."
    return first_line


def render_status(sg: Path, project_label: str) -> str:
    chunks = _load_chunks(sg)
    try:
        waves = plan_waves(chunks) if chunks else []
    except Exception:
        waves = []

    lines: list[str] = []
    lines.append(f"# Skillgoid status — {project_label}")
    lines.append("")

    wave_count = len(waves)
    if wave_count:
        lines.append(f"**Phase:** {wave_count} wave(s) planned")
    else:
        lines.append("**Phase:** no chunks planned")
    lines.append("")

    lines.append("## Chunks")
    lines.append("| chunk_id | wave | state | iter | latest gate state | files touched |")
    lines.append("|----------|------|-------|------|-------------------|---------------|")

    for chunk in chunks:
        cid = chunk.get("id", "?")
        wave = _wave_for_chunk(waves, cid)
        wave_cell = str(wave) if wave is not None else "—"
        record = _latest_iteration_for_chunk(sg, cid)
        if record is None:
            state = "pending"
            iter_num = "—"
        else:
            state = record.get("exit_reason", "in_progress")
            iter_num = str(record.get("iteration", "?"))
        gate = _gate_state_summary(record)
        files = _files_touched_summary(record)
        lines.append(
            f"| {cid} | {wave_cell} | {state} | {iter_num} | {gate} | {files} |"
        )

    integ = _latest_integration(sg)
    if integ is not None:
        attempt, record = integ
        lines.append("")
        lines.append("## Latest integration attempt")
        gate_report = record.get("gate_report") or {}
        passed = gate_report.get("passed", False)
        status = "PASSED" if passed else "FAILED"
        ts = record.get("started_at", "")
        lines.append(f"- Attempt {attempt} ({ts}) — {status}")
        results = gate_report.get("results") or []
        for r in results:
            if r.get("passed"):
                continue
            gid = r.get("gate_id", "?")
            stderr = _truncate_stderr(r.get("stderr", ""))
            if stderr:
                lines.append(f"  - Gate `{gid}` stderr: `{stderr}`")

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Skillgoid project status reader")
    ap.add_argument("--skillgoid-dir", type=Path, default=Path(".skillgoid"))
    args = ap.parse_args(argv)

    sg = args.skillgoid_dir.resolve()
    if not sg.is_dir():
        sys.stderr.write("not a Skillgoid project: .skillgoid/ not found\n")
        return 1

    project_label = sg.parent.name or "unknown"
    sys.stdout.write(render_status(sg, project_label))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
