#!/usr/bin/env python3
"""Git diff summary helper.

Parses `git diff --numstat` output into a structured dict for inclusion
in iteration records. Used by the loop skill after each per-iteration
git commit.

Contract:
    summarize_diff(project: Path, base: str = "HEAD~1", head: str = "HEAD") -> dict
    parse_numstat(output: str) -> dict

Both return: {"files_touched": [...], "net_lines": int, "diff_summary": str}

On first commit (no HEAD~1), falls back to diffing against the empty tree.
Binary files appear in files_touched but contribute 0 to net_lines.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


# git's empty-tree hash — safe to diff against for the "no previous commit" case
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def parse_numstat(output: str) -> dict:
    files_touched: list[str] = []
    net_lines = 0
    summary_parts: list[str] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        added_raw, deleted_raw, path = parts[0], parts[1], "\t".join(parts[2:])
        files_touched.append(path)
        if added_raw == "-" or deleted_raw == "-":
            summary_parts.append(f"{path}: (binary)")
            continue
        try:
            added = int(added_raw)
            deleted = int(deleted_raw)
        except ValueError:
            continue
        net_lines += added - deleted
        summary_parts.append(f"{path}: +{added}/-{deleted}")
    return {
        "files_touched": files_touched,
        "net_lines": net_lines,
        "diff_summary": ", ".join(summary_parts),
    }


def _has_parent_commit(project: Path) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD~1"],
        cwd=project, capture_output=True, text=True, check=False,
    )
    return result.returncode == 0


def summarize_diff(project: Path, base: str | None = None, head: str = "HEAD") -> dict:
    """Return the parsed diff between base..head in the given project.
    If base is None, defaults to HEAD~1 (or empty tree on first commit)."""
    if base is None:
        base = "HEAD~1" if _has_parent_commit(project) else EMPTY_TREE
    try:
        proc = subprocess.run(
            ["git", "diff", "--numstat", f"{base}..{head}"],
            cwd=project,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return {"files_touched": [], "net_lines": 0, "diff_summary": "git not available"}
    if proc.returncode != 0:
        return {"files_touched": [], "net_lines": 0, "diff_summary": f"git diff failed: {proc.stderr.strip()[:200]}"}
    return parse_numstat(proc.stdout)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Skillgoid git-diff summary helper")
    ap.add_argument("--project", required=True, type=Path)
    ap.add_argument("--base", default=None)
    ap.add_argument("--head", default="HEAD")
    args = ap.parse_args(argv)
    result = summarize_diff(args.project.resolve(), base=args.base, head=args.head)
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
