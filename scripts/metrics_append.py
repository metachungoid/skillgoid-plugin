#!/usr/bin/env python3
"""Metrics append helper.

Invoked by the `retrospect` skill after writing a project's
retrospective.md. Appends one JSON line to
~/.claude/skillgoid/metrics.jsonl summarizing the project run.

Contract:
    build_metrics_line(sg: Path, project_slug: str) -> dict
    append_metrics(sg: Path, project_slug: str) -> bool

CLI:
    python scripts/metrics_append.py --skillgoid-dir <path> --slug <slug>

No data leaves the user's machine. No external transmission.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from pathlib import Path

import yaml


def _load_iterations(sg: Path) -> list[dict]:
    iters_dir = sg / "iterations"
    if not iters_dir.is_dir():
        return []
    records: list[dict] = []
    for path in sorted(iters_dir.glob("*.json")):
        try:
            records.append(json.loads(path.read_text()))
        except Exception:
            continue
    return records


def _load_integration(sg: Path) -> list[dict]:
    integ_dir = sg / "integration"
    if not integ_dir.is_dir():
        return []
    records: list[dict] = []
    for path in sorted(integ_dir.glob("*.json")):
        try:
            records.append(json.loads(path.read_text()))
        except Exception:
            continue
    return records


def _count_chunks(sg: Path) -> int:
    chunks_file = sg / "chunks.yaml"
    if not chunks_file.exists():
        return 0
    try:
        data = yaml.safe_load(chunks_file.read_text()) or {}
        chunks = data.get("chunks") or []
        return len(chunks) if isinstance(chunks, list) else 0
    except Exception:
        return 0


def _language(sg: Path) -> str | None:
    crit_file = sg / "criteria.yaml"
    if not crit_file.exists():
        return None
    try:
        data = yaml.safe_load(crit_file.read_text()) or {}
        return data.get("language")
    except Exception:
        return None


def _parse_ts(ts: str | None) -> _dt.datetime | None:
    if not ts:
        return None
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return _dt.datetime.fromisoformat(ts)
    except Exception:
        return None


def _elapsed_seconds(iters: list[dict]) -> int | None:
    starts = [_parse_ts(r.get("started_at")) for r in iters]
    ends = [_parse_ts(r.get("ended_at")) for r in iters]
    starts = [s for s in starts if s]
    ends = [e for e in ends if e]
    if not starts or not ends:
        return None
    return int((max(ends) - min(starts)).total_seconds())


def _outcome(iters: list[dict]) -> str:
    if not iters:
        return "abandoned"
    latest_per_chunk: dict[str, dict] = {}
    for r in iters:
        cid = r.get("chunk_id", "?")
        if cid == "?":
            continue
        n = r.get("iteration", 0)
        if cid not in latest_per_chunk or n > latest_per_chunk[cid].get("iteration", 0):
            latest_per_chunk[cid] = r
    exit_reasons = {r.get("exit_reason", "in_progress") for r in latest_per_chunk.values()}
    if exit_reasons == {"success"}:
        return "success"
    if "stalled" in exit_reasons or "budget_exhausted" in exit_reasons:
        return "partial"
    return "partial"


def build_metrics_line(sg: Path, project_slug: str) -> dict:
    iters = _load_iterations(sg)
    integ = _load_integration(sg)
    stall_count = sum(1 for r in iters if r.get("exit_reason") == "stalled")
    budget_count = sum(1 for r in iters if r.get("exit_reason") == "budget_exhausted")
    integration_retries = max(len(integ) - 1, 0)
    return {
        "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "slug": project_slug,
        "language": _language(sg),
        "outcome": _outcome(iters),
        "chunks": _count_chunks(sg),
        "total_iterations": len(iters),
        "stall_count": stall_count,
        "budget_exhausted_count": budget_count,
        "integration_retries_used": integration_retries,
        "elapsed_seconds": _elapsed_seconds(iters),
    }


def _metrics_file() -> Path:
    home = Path(os.environ.get("HOME") or Path.home())
    return home / ".claude" / "skillgoid" / "metrics.jsonl"


def append_metrics(sg: Path, project_slug: str) -> bool:
    line = build_metrics_line(sg, project_slug)
    path = _metrics_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")
    except Exception as exc:
        sys.stderr.write(f"metrics_append: {exc}\n")
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Skillgoid metrics append helper")
    ap.add_argument("--skillgoid-dir", required=True, type=Path)
    ap.add_argument("--slug", required=True)
    args = ap.parse_args(argv)
    append_metrics(args.skillgoid_dir.resolve(), args.slug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
