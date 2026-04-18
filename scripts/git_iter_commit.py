#!/usr/bin/env python3
"""Git-per-iteration commit helper.

Called by the `loop` skill after writing each iteration record. Makes a
structured git commit of any pending changes so users get free rollback
targets per iteration and a clean audit trail of loop work.

Contract:
- On non-git projects: noop (return False, exit 0).
- On git projects: stage all changes and commit with a structured message
  (uses --allow-empty so zero-diff iterations still produce a commit).
- On any git error: log to stderr and return False — never crash the loop.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def is_git_repo(project: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=project,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


def _build_message(record: dict) -> str:
    chunk_id = record.get("chunk_id", "?")
    iteration = record.get("iteration", "?")
    signature = record.get("failure_signature", "unknown")
    report = record.get("gate_report") or {}
    passed = report.get("passed")
    status = "passed" if passed else ("failing" if passed is False else "in-progress")
    exit_reason = record.get("exit_reason", "in_progress")

    gate_summary_parts = []
    for r in (report.get("results") or []):
        gid = r.get("gate_id", "?")
        ok = "pass" if r.get("passed") else "fail"
        gate_summary_parts.append(f"{gid} ({ok})")
    gate_line = ", ".join(gate_summary_parts) if gate_summary_parts else "no gates"

    return (
        f"skillgoid: iter {iteration} of chunk {chunk_id} ({status})\n\n"
        f"Gates: {gate_line}\n"
        f"Signature: {signature}\n"
        f"Exit: {exit_reason}"
    )


def commit_iteration(project: Path, record: dict) -> bool:
    """Commit the iteration's changes to git. Returns True if a commit was
    made (or attempted), False if noop (non-git project) or on error."""
    if not is_git_repo(project):
        return False

    message = _build_message(record)

    try:
        subprocess.run(["git", "add", "-A"], cwd=project, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", message],
            cwd=project,
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        sys.stderr.write(f"git_iter_commit: {stderr}")
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Skillgoid git-per-iteration commit helper")
    ap.add_argument("--project", required=True, type=Path)
    ap.add_argument("--iteration", required=True, type=Path)
    args = ap.parse_args(argv)

    try:
        record = json.loads(args.iteration.read_text())
    except Exception as exc:
        sys.stderr.write(f"git_iter_commit: cannot read iteration file: {exc}\n")
        return 0  # soft-fail: never block the loop

    commit_iteration(args.project.resolve(), record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
