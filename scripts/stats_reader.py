#!/usr/bin/env python3
"""Skillgoid metrics.jsonl reader and summarizer.

Reads ~/.claude/skillgoid/metrics.jsonl (or --metrics-file override) and
produces a markdown summary. Used by the `stats` skill. Never modifies
the metrics file.

Contract:
    summarize(path: Path, limit: int) -> dict
    format_report(summary: dict, limit: int) -> str

CLI:
    python scripts/stats_reader.py [--metrics-file PATH] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path


def _default_metrics_path() -> Path:
    home = Path(os.environ.get("HOME") or Path.home())
    return home / ".claude" / "skillgoid" / "metrics.jsonl"


def _load_lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    lines: list[dict] = []
    for raw in path.read_text().splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            lines.append(json.loads(raw))
        except Exception:
            continue
    return lines


def summarize(path: Path, limit: int = 20) -> dict:
    lines = _load_lines(path)
    count = len(lines)
    if count == 0:
        return {
            "count": 0,
            "success_rate": None,
            "stall_rate": None,
            "budget_rate": None,
            "integration_retry_rate": None,
            "avg_iterations_per_chunk": None,
            "languages": {},
            "recent": [],
        }

    success = sum(1 for line in lines if line.get("outcome") == "success")
    stalls = sum(1 for line in lines if line.get("stall_count", 0) > 0)
    budget = sum(1 for line in lines if line.get("budget_exhausted_count", 0) > 0)
    integ_retries = sum(1 for line in lines if line.get("integration_retries_used", 0) > 0)

    total_chunks = sum(max(line.get("chunks", 0), 0) for line in lines) or 1
    total_iters = sum(max(line.get("total_iterations", 0), 0) for line in lines)

    languages = Counter(line.get("language") or "unknown" for line in lines)

    # Recent N, newest first
    recent = sorted(
        lines,
        key=lambda line: line.get("timestamp", ""),
        reverse=True,
    )[:limit]

    return {
        "count": count,
        "success_rate": success / count,
        "stall_rate": stalls / count,
        "budget_rate": budget / count,
        "integration_retry_rate": integ_retries / count,
        "avg_iterations_per_chunk": total_iters / total_chunks,
        "languages": dict(languages),
        "recent": recent,
    }


def _pct(f: float | None) -> str:
    return "—" if f is None else f"{f * 100:.1f}%"


def format_report(summary: dict, limit: int = 20) -> str:
    lines = ["# Skillgoid stats", ""]
    if summary["count"] == 0:
        lines.append("_No metrics recorded yet. Run a Skillgoid project through retrospect to populate `~/.claude/skillgoid/metrics.jsonl`._")
        return "\n".join(lines)

    lines.append(f"**{summary['count']} projects tracked**")
    lines.append("")
    lines.append("## Rollups")
    lines.append("")
    lines.append(f"- Success rate: {_pct(summary['success_rate'])}")
    lines.append(f"- Stall rate: {_pct(summary['stall_rate'])}")
    lines.append(f"- Budget-exhaustion rate: {_pct(summary['budget_rate'])}")
    lines.append(f"- Integration-retry rate: {_pct(summary['integration_retry_rate'])}")
    avg = summary["avg_iterations_per_chunk"]
    lines.append(f"- Avg iterations per chunk: {'—' if avg is None else f'{avg:.2f}'}")
    lines.append("")
    lines.append("## Languages")
    lines.append("")
    for lang, n in sorted(summary["languages"].items(), key=lambda kv: -kv[1]):
        lines.append(f"- {lang}: {n}")
    lines.append("")

    lines.append(f"## Last {min(limit, summary['count'])} projects")
    lines.append("")
    lines.append("| date | slug | lang | outcome | chunks | iters | stalls | retries | elapsed |")
    lines.append("|---|---|---|---|---:|---:|---:|---:|---:|")
    for line in summary["recent"]:
        date = (line.get("timestamp") or "")[:10]
        slug = line.get("slug") or "—"
        lang = line.get("language") or "—"
        outcome = line.get("outcome") or "—"
        chunks = line.get("chunks", "—")
        iters = line.get("total_iterations", "—")
        stalls = line.get("stall_count", 0)
        retries = line.get("integration_retries_used", 0)
        elapsed = line.get("elapsed_seconds")
        elapsed_str = "—" if elapsed is None else f"{elapsed}s"
        lines.append(f"| {date} | {slug} | {lang} | {outcome} | {chunks} | {iters} | {stalls} | {retries} | {elapsed_str} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Skillgoid metrics.jsonl reader")
    ap.add_argument("--metrics-file", type=Path, default=_default_metrics_path())
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args(argv)

    summary = summarize(args.metrics_file, limit=args.limit)
    sys.stdout.write(format_report(summary, limit=args.limit) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
