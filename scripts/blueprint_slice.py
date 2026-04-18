#!/usr/bin/env python3
"""Blueprint slicer: extract the relevant section(s) for a specific chunk.

Given a `blueprint.md` file with `## <chunk-id>` H2 headings (one per chunk),
produce a sliced view containing:
  1. `## Architecture overview` (always, when present)
  2. `## Cross-chunk types` (always, when present; warning logged if absent)
  3. `## <chunk_id>` (raises ValueError if not present)

Legacy behavior: if the blueprint has no H2 headings at all, returns the full
blueprint content with a warning. This supports projects that haven't adopted
the v0.2 heading discipline.

Public surface:
    slice_blueprint(md: str, chunk_id: str) -> str

CLI:
    python scripts/blueprint_slice.py --blueprint <path> --chunk-id <id>
    Prints sliced content to stdout; errors to stderr; exit 2 on failure.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


_H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def _parse_sections(md: str) -> dict[str, str]:
    """Return dict mapping H2 heading → section body (heading included).
    Body runs from the heading to (but not including) the next H2 or EOF."""
    sections: dict[str, str] = {}
    matches = list(_H2_RE.finditer(md))
    if not matches:
        return sections
    for i, m in enumerate(matches):
        heading = m.group(1).strip()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md)
        sections[heading] = md[start:end].rstrip() + "\n"
    return sections


def slice_blueprint(md: str, chunk_id: str) -> str:
    """Return the sliced blueprint for a given chunk_id.

    Raises ValueError if no `## <chunk_id>` section exists.
    Warns to stderr if `## Cross-chunk types` is absent (still proceeds).
    Returns full content if blueprint has no H2 headings at all.
    """
    sections = _parse_sections(md)
    if not sections:
        sys.stderr.write(
            "blueprint_slice: no H2 headings found in blueprint; "
            "returning full content\n"
        )
        return md

    parts: list[str] = []
    if "Architecture overview" in sections:
        parts.append(sections["Architecture overview"])
    if "Cross-chunk types" in sections:
        parts.append(sections["Cross-chunk types"])
    else:
        sys.stderr.write(
            "blueprint_slice: no `## Cross-chunk types` section declared "
            "— consider adding one for multi-chunk type contracts (F6)\n"
        )

    if chunk_id not in sections:
        raise ValueError(
            f"blueprint_slice: no `## {chunk_id}` section in blueprint. "
            f"Available H2 sections: {sorted(sections)}"
        )
    parts.append(sections[chunk_id])
    return "\n".join(parts).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Slice blueprint for a specific chunk")
    ap.add_argument("--blueprint", required=True, type=Path)
    ap.add_argument("--chunk-id", required=True)
    args = ap.parse_args(argv)
    try:
        md = args.blueprint.read_text()
    except Exception as exc:
        sys.stderr.write(f"blueprint_slice: cannot read {args.blueprint}: {exc}\n")
        return 2
    try:
        sys.stdout.write(slice_blueprint(md, args.chunk_id))
    except ValueError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
