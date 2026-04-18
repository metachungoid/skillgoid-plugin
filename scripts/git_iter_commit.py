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
import contextlib
import fcntl
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


@contextlib.contextmanager
def _commit_lock(project: Path):
    """Hold an exclusive flock on .git/skillgoid-commit.lock for the duration
    of the add+commit sequence. Serializes concurrent git_iter_commit
    invocations so parallel-wave subagents can't race on git's index. Posix
    fcntl-based; on non-posix platforms the lock degrades to a no-op (the
    file is still created, but flock() raises and we fall back to no
    serialization). Block until the lock is acquired."""
    lock_path = project / ".git" / "skillgoid-commit.lock"
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        yield
        return
    try:
        fd = open(lock_path, "w")
    except OSError:
        yield
        return
    try:
        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_EX)
        except (OSError, AttributeError):
            # Non-posix or unsupported: degrade to no serialization.
            pass
        yield
    finally:
        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
        except (OSError, AttributeError):
            pass
        fd.close()


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

    Acquires an exclusive flock on .git/skillgoid-commit.lock for the entire
    add+commit sequence so concurrent invocations from parallel-wave
    subagents serialize cleanly (without it, two processes' `git add` calls
    interleave on the shared git index and produce cross-contaminated
    commits).
    """
    if not is_git_repo(project):
        return False

    message = _build_message(record)
    chunk_id = record.get("chunk_id", "")
    scoped_paths = _resolve_scoped_paths(project, chunk_id, chunks_file, iteration_path)

    with _commit_lock(project):
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

    # v0.8: schema validation before commit (F5, F9).
    try:
        from scripts.validate_iteration import validate_iteration
    except ImportError:
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location(
            "validate_iteration",
            Path(__file__).resolve().parent / "validate_iteration.py",
        )
        _mod = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
        _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
        validate_iteration = _mod.validate_iteration
    errors = validate_iteration(record)
    if errors:
        sys.stderr.write(
            f"git_iter_commit: iteration at {iteration_path} failed schema validation:\n"
        )
        for err in errors:
            sys.stderr.write(f"  - {err}\n")
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
