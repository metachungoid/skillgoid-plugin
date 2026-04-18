#!/usr/bin/env python3
"""Deterministic stall-detection signature helper.

Loops need a reliable way to detect "same failure, same root cause" across
iterations so they can exit on stall rather than burn the whole loop budget
on an unsolvable problem. Claude-judged comparisons are fragile; a hash
is not.

Signature contract:
    sha256 of  f"{sorted_failing_gate_ids}::{concatenated_stderr_prefixes}"
    truncated to 16 hex chars.

Only failing gates contribute. Only the first 200 chars of each failing
gate's stderr contribute. Timestamps, absolute paths beyond 200 chars, and
any other noise are excluded — same root cause -> same signature.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


STDERR_PREFIX_BYTES = 200
SIGNATURE_LEN = 16


def signature(record: dict) -> str:
    """Compute the deterministic stall signature for an iteration record."""
    report = record.get("gate_report") or {}
    results = report.get("results") or []
    failing = [r for r in results if not r.get("passed")]

    failing_ids = sorted(r.get("gate_id", "") for r in failing)
    stderr_blob = "".join(
        (r.get("stderr") or "")[:STDERR_PREFIX_BYTES] for r in failing
    )
    payload = f"{failing_ids}::{stderr_blob}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:SIGNATURE_LEN]


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 1:
        sys.stderr.write("usage: stall_check.py <iteration.json>\n")
        return 2
    path = Path(argv[0])
    try:
        record = json.loads(path.read_text())
    except Exception as exc:
        sys.stderr.write(f"stall_check: {exc}\n")
        return 2
    sys.stdout.write(signature(record) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
