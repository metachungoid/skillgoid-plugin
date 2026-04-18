#!/usr/bin/env python3
"""Topological wave planner for chunk dispatch.

Reads a chunks list (same shape as chunks.yaml's `chunks[]`) and groups
chunks into execution "waves": each wave is a set of chunks that can
dispatch concurrently because none of them depend on another in the
same wave.

Contract:
    plan_waves(chunks: list[dict]) -> list[list[str]]

Raises:
    DependencyError — duplicate chunk ids, or depends_on references
                      a chunk that doesn't exist.
    CycleError     — the depends_on graph contains a cycle.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


class DependencyError(ValueError):
    """Raised for duplicate chunk ids or unresolvable depends_on references."""


class CycleError(ValueError):
    """Raised when the depends_on graph contains a cycle."""


def plan_waves(chunks: list[dict]) -> list[list[str]]:
    """Group chunks into execution waves by topological sort of depends_on.

    Each wave is returned as a sorted list of chunk ids for determinism.
    """
    if not chunks:
        return []

    ids = [c["id"] for c in chunks]
    if len(ids) != len(set(ids)):
        seen: set[str] = set()
        dupes = []
        for i in ids:
            if i in seen:
                dupes.append(i)
            seen.add(i)
        raise DependencyError(f"duplicate chunk ids: {sorted(set(dupes))}")

    id_set = set(ids)
    deps = {c["id"]: list(c.get("depends_on") or []) for c in chunks}

    # Validate that every depends_on references a real chunk
    for chunk_id, chunk_deps in deps.items():
        for dep in chunk_deps:
            if dep not in id_set:
                raise DependencyError(
                    f"chunk '{chunk_id}' depends_on '{dep}' which is not a known chunk"
                )

    waves: list[list[str]] = []
    remaining = set(ids)
    satisfied: set[str] = set()

    while remaining:
        # A chunk can run now iff all its deps are satisfied
        wave = sorted(cid for cid in remaining if all(d in satisfied for d in deps[cid]))
        if not wave:
            unresolved = sorted(remaining)
            raise CycleError(f"cycle detected among chunks: {unresolved}")
        waves.append(wave)
        satisfied.update(wave)
        remaining.difference_update(wave)

    return waves


def _load_chunks_yaml(path: Path) -> list[dict]:
    import yaml

    data = yaml.safe_load(path.read_text()) or {}
    chunks = data.get("chunks") or []
    if not isinstance(chunks, list):
        raise DependencyError("chunks.yaml must contain a `chunks:` list")
    return chunks


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Skillgoid chunks.yaml wave planner")
    ap.add_argument("--chunks-file", required=True, type=Path)
    args = ap.parse_args(argv)
    chunks = _load_chunks_yaml(args.chunks_file)
    waves = plan_waves(chunks)
    sys.stdout.write(json.dumps({"waves": waves}) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
