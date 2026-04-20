

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


def _paths_overlap(a: list[str], b: list[str]) -> bool:
    """Exact-string match on any path element between two chunks' paths lists.
    v0.8 uses exact matching; glob-aware matching is deferred to v0.9 if
    evidence shows users want it."""
    if not a or not b:
        return False
    return bool(set(a) & set(b))


def _split_wave_on_overlap(wave: list[str], chunks_by_id: dict[str, dict]) -> list[list[str]]:
    """Split a wave into consecutive sub-waves when chunks' paths: overlap.
    Greedy, alphabetical-order placement for determinism.
    Returns [wave] unchanged when no overlap exists."""
    if len(wave) <= 1:
        return [wave]
    sorted_chunks = sorted(wave)
    sub_waves: list[list[str]] = []
    for chunk_id in sorted_chunks:
        paths = chunks_by_id[chunk_id].get("paths") or []
        placed = False
        for sw in sub_waves:
            if all(
                not _paths_overlap(paths, chunks_by_id[cid].get("paths") or [])
                for cid in sw
            ):
                sw.append(chunk_id)
                placed = True
                break
        if not placed:
            sub_waves.append([chunk_id])
    if len(sub_waves) > 1:
        sys.stderr.write(
            f"chunk_topo: wave {sorted_chunks!r} split into {len(sub_waves)} "
            f"sub-waves due to overlapping paths: {sub_waves!r}\n"
        )
    return sub_waves


def plan_waves(chunks: list[dict]) -> list[list[str]]:
    """Group chunks into execution waves by topological sort of depends_on.

    Each wave is returned as a sorted list of chunk ids for determinism.
    Chunks whose paths: overlap are split into consecutive sub-waves (F8 fix).
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

    initial_waves: list[list[str]] = []
    remaining = set(ids)
    satisfied: set[str] = set()

    while remaining:
        # A chunk can run now iff all its deps are satisfied
        wave = sorted(cid for cid in remaining if all(d in satisfied for d in deps[cid]))
        if not wave:
            unresolved = sorted(remaining)
            raise CycleError(f"cycle detected among chunks: {unresolved}")
        initial_waves.append(wave)
        satisfied.update(wave)
        remaining.difference_update(wave)

    # Post-pass: split waves where chunk paths: overlap (F8 fix)
    chunks_by_id = {c["id"]: c for c in chunks}
    result: list[list[str]] = []
    for wave in initial_waves:
        for sub in _split_wave_on_overlap(wave, chunks_by_id):
            result.append(sub)
    return result


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
