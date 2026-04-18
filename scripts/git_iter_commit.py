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


def commit_iteration(
    project: Path,
    record: dict,
    iteration_path: Path | None = None,
    chunks_file: Path | None = None,
) -> bool:
    """Commit the iteration's changes to git. Returns True if a commit was
    made (or attempted), False if noop (non-git project) or on error.

    When `chunks_file` is provided AND the chunk referenced by record.chunk_id
    has a `paths:` list, stage only those paths + the iteration file. Otherwise
    fall back to `git add -A` with a stderr warning.
    """
    if not is_git_repo(project):
        return False

    message = _build_message(record)
    chunk_id = record.get("chunk_id", "")
    scoped_paths = _resolve_scoped_paths(project, chunk_id, chunks_file, iteration_path)

    try:
        if scoped_paths is not None:
            subprocess.run(
                ["git", "add", "--", *scoped_paths],
                cwd=project, check=True, capture_output=True,
            )
        else:
            sys.stderr.write(
                f"git_iter_commit: chunk {chunk_id!r} has no paths: declared, "
                f"falling back to 'git add -A' — consider adding paths: for "
                f"safer parallel waves\n"
            )
            subprocess.run(
                ["git", "add", "-A"],
                cwd=project, check=True, capture_output=True,
            )
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", message],
            cwd=project, check=True, capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        sys.stderr.write(f"git_iter_commit: {stderr}")
        return False
    return True


def _resolve_scoped_paths(
    project: Path,
    chunk_id: str,
    chunks_file: Path | None,
    iteration_path: Path | None,
) -> list[str] | None:
    """Return a list of paths (relative to project) to stage for this chunk's
    commit, or None if no scoping info is available (caller falls back to
    git add -A).
    """
    if chunks_file is None or not chunks_file.exists():
        return None
    try:
        import yaml
        data = yaml.safe_load(chunks_file.read_text()) or {}
    except Exception:
        return None
    chunks = data.get("chunks") or []
    match = next((c for c in chunks if c.get("id") == chunk_id), None)
    if not match:
        return None
    paths = match.get("paths")
    if not paths:
        return None
    result = list(paths)
    # Always include the iteration file itself (project-relative)
    if iteration_path is not None:
        try:
            rel = iteration_path.relative_to(project)
            result.append(str(rel))
        except ValueError:
            pass  # iteration not under project — shouldn't happen post-resolve
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Skillgoid git-per-iteration commit helper")
    ap.add_argument("--project", required=True, type=Path)
    ap.add_argument("--iteration", required=True, type=Path)
    ap.add_argument(
        "--chunks-file",
        type=Path,
        default=None,
        help="Path to chunks.yaml (usually <project>/.skillgoid/chunks.yaml). "
             "Used to look up the chunk's paths: for scoped git add. "
             "If absent, falls back to 'git add -A' with a warning.",
    )
    args = ap.parse_args(argv)

    project = args.project.resolve()

    # Resolve --iteration against --project if relative (F25).
    iteration_path = args.iteration
    if not iteration_path.is_absolute():
        iteration_path = (project / iteration_path).resolve()

    # Hard-fail on unreadable iteration (replaces v0.6's silent soft-fail).
    try:
        record = json.loads(iteration_path.read_text())
    except Exception as exc:
        sys.stderr.write(f"git_iter_commit: cannot read iteration at {iteration_path}: {exc}\n")
        return 2

    # Resolve --chunks-file against --project if relative.
    chunks_file = args.chunks_file
    if chunks_file is not None and not chunks_file.is_absolute():
        chunks_file = (project / chunks_file).resolve()

    if not is_git_repo(project):
        # Non-git project: noop is success
        return 0

    success = commit_iteration(project, record, iteration_path=iteration_path, chunks_file=chunks_file)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
