#!/usr/bin/env python3
"""Vault lesson filter.

Parses a `<language>-lessons.md` file into lessons, reads each lesson's
optional `Status: resolved in vX.Y` line, and filters them by the
current Skillgoid plugin version.

Contract:
    parse_version(text: str) -> tuple[int, ...] | None
    parse_lessons(md: str) -> list[dict]
    filter_lessons(lessons, current_version) -> tuple[list, list]
        returns (active_lessons, resolved_lessons)

CLI:
    python scripts/vault_filter.py \\
        --lessons-file ~/.claude/skillgoid/vault/python-lessons.md \\
        --plugin-json .claude-plugin/plugin.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)(?:\.(\d+))?$")
_STATUS_RE = re.compile(r"(?mi)^Status:\s*resolved\s+in\s+(\S+)")


def parse_version(text: str) -> tuple[int, ...] | None:
    """Parse '0.4' or 'v0.4' or '0.4.2' into a tuple of ints, else None."""
    if not text:
        return None
    m = _VERSION_RE.match(text.strip())
    if not m:
        return None
    return tuple(int(g) for g in m.groups() if g is not None)


def parse_lessons(md: str) -> list[dict]:
    """Split a vault markdown file into lesson dicts.

    Each lesson dict has: title (str), body (str), resolved_in (tuple | None).
    The H1 title + any preamble before the first H2 is not a lesson.
    """
    lessons: list[dict] = []
    # Split on H2 headings (lines starting with "## ")
    sections = re.split(r"(?m)^##\s+(.+)$", md)
    # sections[0] is preamble (before first ## ); then pairs of (title, body)
    i = 1
    while i < len(sections):
        title = sections[i].strip()
        body = sections[i + 1] if i + 1 < len(sections) else ""
        status_match = _STATUS_RE.search(body)
        resolved_in = parse_version(status_match.group(1)) if status_match else None
        lessons.append({"title": title, "body": body, "resolved_in": resolved_in})
        i += 2
    return lessons


def filter_lessons(
    lessons: list[dict],
    current_version: tuple[int, ...] | None,
) -> tuple[list[dict], list[dict]]:
    """Split lessons into (active, resolved) based on current_version.

    A lesson is 'resolved' if it has a `resolved_in` tuple AND
    current_version is not None AND current_version >= resolved_in.
    If current_version is None, fail-open and treat everything as active.
    """
    if current_version is None:
        return lessons, []
    active: list[dict] = []
    resolved: list[dict] = []
    for lesson in lessons:
        rv = lesson.get("resolved_in")
        if rv is not None and current_version >= rv:
            resolved.append(lesson)
        else:
            active.append(lesson)
    return active, resolved


def _read_plugin_version(plugin_json: Path) -> tuple[int, ...] | None:
    try:
        data = json.loads(plugin_json.read_text())
    except Exception:
        return None
    return parse_version(data.get("version") or "")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Skillgoid vault lesson filter")
    ap.add_argument("--lessons-file", required=True, type=Path)
    ap.add_argument("--plugin-json", required=True, type=Path)
    args = ap.parse_args(argv)

    if not args.lessons_file.exists():
        sys.stdout.write(json.dumps({"active": [], "resolved": []}) + "\n")
        return 0

    md = args.lessons_file.read_text()
    lessons = parse_lessons(md)
    version = _read_plugin_version(args.plugin_json)
    active, resolved = filter_lessons(lessons, version)
    sys.stdout.write(json.dumps({
        "active": [line["title"] for line in active],
        "resolved": [line["title"] for line in resolved],
    }) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
